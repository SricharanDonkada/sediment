import redis

from app import queue
from app.config import settings
from sediment_schemas import IngestionMessage


def test_enqueue_pushes_parseable_envelope():
    r = redis.Redis.from_url(settings.redis_url)
    r.delete(settings.ingestion_queue)  # clean slate so RPOP returns our message
    msg = IngestionMessage(object_key="rt-test.wav", bucket=settings.ingestion_bucket)

    queue.enqueue(msg)

    raw = r.rpop(settings.ingestion_queue)  # FIFO: LPUSH + RPOP
    assert raw is not None
    assert IngestionMessage.model_validate_json(raw) == msg
