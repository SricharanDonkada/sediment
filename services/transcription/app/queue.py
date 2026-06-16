import redis

from app.config import settings
from sediment_schemas import TranscriptionMessage

_redis: redis.Redis | None = None


def _client() -> redis.Redis:
    """Lazily build a singleton Redis client from settings."""
    global _redis
    if _redis is None:
        # socket_timeout=None: blocking commands (BRPOPLPUSH) own the wait;
        # a finite socket timeout races with the command timeout and raises
        # TimeoutError before the blocking call can return cleanly.
        _redis = redis.Redis.from_url(settings.redis_url, socket_timeout=None)
    return _redis


def claim(timeout: int = 5) -> bytes | None:
    """Atomically move the oldest job from the ingestion queue to the
    processing list and return its raw bytes. Returns None if no job
    arrives within `timeout` seconds.

    Ingestion LPUSHes to the head, so popping the tail (BRPOPLPUSH) is FIFO.
    The job parked in the processing list survives a worker crash.
    """
    return _client().brpoplpush(
        settings.ingestion_queue,
        settings.transcription_processing_queue,
        timeout=timeout,
    )


def ack(raw: bytes) -> None:
    """Remove a successfully processed job from the processing list."""
    _client().lrem(settings.transcription_processing_queue, 1, raw)


def dead_letter(raw: bytes) -> None:
    """Move a failed job from the processing list to the dead-letter list.

    The two writes are not atomic: push-to-dead happens before
    remove-from-processing, so a crash between them leaves the job in both
    lists. This is the safe direction (no loss) — expect possible duplicate
    entries across the two lists after a mid-failure crash.
    """
    client = _client()
    client.lpush(settings.transcription_dead_queue, raw)
    client.lrem(settings.transcription_processing_queue, 1, raw)


def enqueue(message: TranscriptionMessage) -> None:
    """LPUSH the JSON-serialized transcript envelope onto the transcription queue."""
    _client().lpush(settings.transcription_queue, message.model_dump_json())
