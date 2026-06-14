import uuid

from app import storage
from app.config import settings


def test_ensure_bucket_then_put_and_read_back():
    storage.ensure_bucket()
    key = f"test-{uuid.uuid4()}.wav"
    payload = b"RIFFfake-wav-bytes"

    storage.put(key, payload)

    client = storage._client()
    try:
        with client.get_object(settings.ingestion_bucket, key) as obj:
            assert obj.read() == payload
    finally:
        client.remove_object(settings.ingestion_bucket, key)
