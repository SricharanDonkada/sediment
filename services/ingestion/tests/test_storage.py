import uuid

from app import storage
from app.config import settings


def test_ensure_bucket_then_put_and_read_back():
    storage.ensure_bucket()
    key = f"test-{uuid.uuid4()}.wav"
    payload = b"RIFFfake-wav-bytes"

    storage.put(key, payload)

    client = storage._client()
    obj = client.get_object(settings.ingestion_bucket, key)
    try:
        assert obj.read() == payload
    finally:
        obj.close()
        obj.release_conn()
        client.remove_object(settings.ingestion_bucket, key)
