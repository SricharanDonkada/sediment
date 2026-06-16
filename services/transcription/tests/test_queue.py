import redis

from app import queue
from app.config import settings
from sediment_schemas import IngestionMessage, TranscriptionMessage


def _raw() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url)


def _clean():
    r = _raw()
    r.delete(
        settings.ingestion_queue,
        settings.transcription_processing_queue,
        settings.transcription_queue,
        settings.transcription_dead_queue,
    )


def test_claim_moves_message_to_processing_list():
    _clean()
    r = _raw()
    msg = IngestionMessage(object_key="job.wav", bucket="audio")
    r.lpush(settings.ingestion_queue, msg.model_dump_json())

    raw = queue.claim(timeout=2)

    assert raw is not None
    assert IngestionMessage.model_validate_json(raw) == msg
    # The in-flight message now lives in the processing list.
    assert r.lrange(settings.transcription_processing_queue, 0, -1) == [raw]
    assert r.llen(settings.ingestion_queue) == 0


def test_claim_returns_none_on_timeout():
    _clean()
    assert queue.claim(timeout=1) is None


def test_ack_removes_from_processing():
    _clean()
    r = _raw()
    r.lpush(settings.ingestion_queue, b"payload")
    raw = queue.claim(timeout=2)

    queue.ack(raw)

    assert r.llen(settings.transcription_processing_queue) == 0


def test_dead_letter_moves_processing_to_dead():
    _clean()
    r = _raw()
    r.lpush(settings.ingestion_queue, b"payload")
    raw = queue.claim(timeout=2)

    queue.dead_letter(raw)

    assert r.llen(settings.transcription_processing_queue) == 0
    assert r.lrange(settings.transcription_dead_queue, 0, -1) == [raw]


def test_enqueue_pushes_parseable_envelope():
    _clean()
    r = _raw()
    msg = TranscriptionMessage(object_key="job.txt", bucket="transcripts")

    queue.enqueue(msg)

    out = r.rpop(settings.transcription_queue)
    assert TranscriptionMessage.model_validate_json(out) == msg
