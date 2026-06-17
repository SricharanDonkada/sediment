# services/extraction/tests/test_storage.py
from app import storage


def test_get_transcript_returns_decoded_text(monkeypatch):
    class FakeResponse:
        def read(self):
            return b"SPEAKER_A: hello\nSPEAKER_B: world\n"
        def close(self): pass
        def release_conn(self): pass

    class FakeMinioClient:
        def get_object(self, bucket, key):
            assert bucket == "transcripts"
            assert key == "abc-123.txt"
            return FakeResponse()

    monkeypatch.setattr(storage, "_client", lambda: FakeMinioClient())
    result = storage.get_transcript("transcripts", "abc-123.txt")
    assert result == "SPEAKER_A: hello\nSPEAKER_B: world\n"


def test_get_transcript_releases_conn_on_error(monkeypatch):
    closed = []

    class FakeResponse:
        def read(self):
            raise RuntimeError("read failed")
        def close(self):
            closed.append("closed")
        def release_conn(self):
            closed.append("released")

    class FakeMinioClient:
        def get_object(self, bucket, key):
            return FakeResponse()

    monkeypatch.setattr(storage, "_client", lambda: FakeMinioClient())
    try:
        storage.get_transcript("transcripts", "abc-123.txt")
    except RuntimeError:
        pass

    assert "closed" in closed
    assert "released" in closed
