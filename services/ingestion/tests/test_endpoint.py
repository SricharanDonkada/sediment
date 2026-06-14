import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(monkeypatch):
    # Neutralize external collaborators; record what the endpoint hands them.
    monkeypatch.setattr(main.storage, "ensure_bucket", lambda: None)
    monkeypatch.setattr(main.audio, "normalize", lambda src, suffix="": b"WAVDATA")

    put_calls = []
    monkeypatch.setattr(main.storage, "put", lambda key, data: put_calls.append((key, data)))

    enqueued = []
    monkeypatch.setattr(main.queue, "enqueue", lambda msg: enqueued.append(msg))

    c = TestClient(main.app)
    c.put_calls = put_calls
    c.enqueued = enqueued
    return c


def test_get_root_serves_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_rejects_when_neither_field_present(client):
    resp = client.post("/ingest")
    assert resp.status_code == 400


def test_rejects_when_both_fields_present(client):
    resp = client.post(
        "/ingest",
        data={"youtube_url": "https://youtu.be/abc"},
        files={"file": ("a.mp3", b"raw", "audio/mpeg")},
    )
    assert resp.status_code == 400


def test_upload_path_stores_and_enqueues(client):
    resp = client.post("/ingest", files={"file": ("a.mp3", b"raw-bytes", "audio/mpeg")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["object_key"].endswith(".wav")
    assert body["bucket"] == "audio"
    assert client.put_calls == [(body["object_key"], b"WAVDATA")]
    assert len(client.enqueued) == 1
    assert client.enqueued[0].object_key == body["object_key"]
    assert client.enqueued[0].bucket == "audio"


def test_upload_passes_extension_hint(client, monkeypatch):
    seen = {}

    def _capture(src, suffix=""):
        seen["suffix"] = suffix
        return b"WAVDATA"

    monkeypatch.setattr(main.audio, "normalize", _capture)
    resp = client.post("/ingest", files={"file": ("clip.mp3", b"raw", "audio/mpeg")})
    assert resp.status_code == 200
    assert seen["suffix"] == ".mp3"


def test_youtube_path_downloads_then_stores(client, monkeypatch, tmp_path):
    d = tmp_path / "ytdl-xyz"
    d.mkdir()
    f = d / "vid.m4a"
    f.write_bytes(b"audio")
    monkeypatch.setattr(main.youtube, "download", lambda url: str(f))
    resp = client.post("/ingest", data={"youtube_url": "https://youtu.be/abc"})
    assert resp.status_code == 200
    assert resp.json()["object_key"].endswith(".wav")
    assert len(client.enqueued) == 1
    assert not d.exists()  # the temp dir must be cleaned up after processing


def test_bad_audio_returns_422(client, monkeypatch):
    from app.audio import AudioProcessingError

    def _boom(src, suffix=""):
        raise AudioProcessingError("bad")

    monkeypatch.setattr(main.audio, "normalize", _boom)
    resp = client.post("/ingest", files={"file": ("a.mp3", b"raw", "audio/mpeg")})
    assert resp.status_code == 422


def test_bad_youtube_url_returns_422(client, monkeypatch):
    from app.youtube import YouTubeDownloadError

    def _boom(url):
        raise YouTubeDownloadError("unavailable")

    monkeypatch.setattr(main.youtube, "download", _boom)
    resp = client.post("/ingest", data={"youtube_url": "https://youtu.be/bad"})
    assert resp.status_code == 422
