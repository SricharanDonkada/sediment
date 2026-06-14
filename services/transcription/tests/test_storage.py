import io
import os
import uuid

from app import storage
from app.config import settings


def test_ensure_bucket_then_put_transcript_and_read_back():
    storage.ensure_bucket()
    key = f"test-{uuid.uuid4()}.txt"
    text = "SPEAKER_A: hello\n\nSPEAKER_B: hi there\n"

    storage.put_transcript(key, text)

    client = storage._client()
    try:
        with client.get_object(settings.transcripts_bucket, key) as obj:
            assert obj.read().decode("utf-8") == text
    finally:
        client.remove_object(settings.transcripts_bucket, key)


def test_get_audio_downloads_to_path():
    client = storage._client()
    if not client.bucket_exists("audio"):
        client.make_bucket("audio")
    key = f"test-{uuid.uuid4()}.wav"
    payload = b"RIFFfake-wav-bytes"
    client.put_object("audio", key, io.BytesIO(payload), length=len(payload))

    path = storage.get_audio("audio", key)
    try:
        with open(path, "rb") as f:
            assert f.read() == payload
    finally:
        os.unlink(path)
        client.remove_object("audio", key)
