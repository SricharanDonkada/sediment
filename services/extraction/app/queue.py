import redis

from app.config import settings

_redis: redis.Redis | None = None


def _client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.redis_url, socket_timeout=None)
    return _redis


def claim(timeout: int = 5) -> bytes | None:
    return _client().blmove(
        settings.extraction_queue,
        settings.extraction_processing_queue,
        "RIGHT",
        "LEFT",
        timeout=timeout,
    )


def ack(raw: bytes) -> None:
    _client().lrem(settings.extraction_processing_queue, 1, raw)


def dead_letter(raw: bytes) -> None:
    client = _client()
    client.lpush(settings.extraction_dead_queue, raw)
    client.lrem(settings.extraction_processing_queue, 1, raw)
