# services/extraction/tests/test_config.py
import pytest
from app.config import Settings


def test_default_queue_names():
    s = Settings()
    assert s.extraction_queue == "extract"
    assert s.extraction_processing_queue == "extract:processing"
    assert s.extraction_dead_queue == "extract:dead"


def test_default_minio():
    s = Settings()
    assert s.minio_endpoint == "localhost:9000"
    assert s.transcripts_bucket == "transcripts"


def test_default_gemini_models():
    s = Settings()
    assert s.gemini_extraction_model == "gemini-2.5-flash"
    assert s.gemini_embedding_model == "gemini-embedding-001"


def test_postgres_dsn_default():
    s = Settings()
    assert "localhost" in s.postgres_dsn
    assert "5432" in s.postgres_dsn
