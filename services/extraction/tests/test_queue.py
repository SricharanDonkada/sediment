import pytest
import redis as redis_lib

from app import queue
from app.config import settings
from sediment_schemas import TranscriptionMessage


def _raw_client() -> redis_lib.Redis:
    return redis_lib.Redis.from_url(settings.redis_url)


def _clean():
    r = _raw_client()
    r.delete(
        settings.extraction_queue,
        settings.extraction_processing_queue,
        settings.extraction_dead_queue,
    )


@pytest.mark.integration
def test_claim_moves_message_to_processing_list():
    _clean()
    r = _raw_client()
    msg = TranscriptionMessage(object_key="job.txt", bucket="transcripts")
    r.lpush(settings.extraction_queue, msg.model_dump_json())

    raw = queue.claim(timeout=2)

    assert raw is not None
    assert TranscriptionMessage.model_validate_json(raw) == msg
    assert r.lrange(settings.extraction_processing_queue, 0, -1) == [raw]
    assert r.llen(settings.extraction_queue) == 0


@pytest.mark.integration
def test_claim_returns_none_on_timeout():
    _clean()
    assert queue.claim(timeout=1) is None


@pytest.mark.integration
def test_ack_removes_from_processing():
    _clean()
    r = _raw_client()
    r.lpush(settings.extraction_queue, b"payload")
    raw = queue.claim(timeout=2)

    queue.ack(raw)

    assert r.llen(settings.extraction_processing_queue) == 0


@pytest.mark.integration
def test_dead_letter_moves_to_dead_queue():
    _clean()
    r = _raw_client()
    r.lpush(settings.extraction_queue, b"payload")
    raw = queue.claim(timeout=2)

    queue.dead_letter(raw)

    assert r.llen(settings.extraction_processing_queue) == 0
    assert r.lrange(settings.extraction_dead_queue, 0, -1) == [raw]
