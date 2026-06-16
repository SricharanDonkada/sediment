from app.config import Settings


def test_defaults_match_compose():
    s = Settings()
    assert s.minio_endpoint == "localhost:9000"
    assert s.minio_root_user == "sediment"
    assert s.minio_root_password == "sediment-dev"
    assert s.minio_secure is False
    assert s.ingestion_bucket == "audio"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.ingestion_queue == "audio-transcribe"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("INGESTION_BUCKET", "other")
    assert Settings().ingestion_bucket == "other"
