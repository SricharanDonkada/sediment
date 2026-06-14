from app.config import Settings


def test_defaults_match_compose():
    s = Settings()
    assert s.minio_endpoint == "localhost:9000"
    assert s.minio_root_user == "sediment"
    assert s.minio_root_password == "sediment-dev"
    assert s.minio_secure is False
    assert s.transcripts_bucket == "transcripts"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.ingestion_queue == "ingestion_queue"
    assert s.transcription_processing_queue == "transcription_processing"
    assert s.transcription_queue == "transcription_queue"
    assert s.transcription_dead_queue == "transcription_dead"
    assert s.whisper_model == "large-v3-turbo"
    assert s.whisper_device == "cpu"
    assert s.whisper_compute_type == "int8"
    assert s.diarization_model == "pyannote/speaker-diarization-community-1"
    assert s.hf_token == ""


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("WHISPER_DEVICE", "cuda")
    assert Settings().whisper_device == "cuda"
