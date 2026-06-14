import redis

from app.config import settings
from sediment_schemas import IngestionMessage

_redis: redis.Redis | None = None


def _client() -> redis.Redis:
    """Lazily build a singleton Redis client from settings."""
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.redis_url)
    return _redis


def enqueue(message: IngestionMessage) -> None:
    """LPUSH the JSON-serialized envelope onto the ingestion queue."""
    _client().lpush(settings.ingestion_queue, message.model_dump_json())
