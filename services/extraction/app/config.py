from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    extraction_queue: str = "extract"
    extraction_processing_queue: str = "extract:processing"
    extraction_dead_queue: str = "extract:dead"

    # MinIO (read-only — transcripts bucket created by transcription service)
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "sediment"
    minio_root_password: str = "sediment-dev"
    minio_secure: bool = False
    transcripts_bucket: str = "transcripts"

    # PostgreSQL
    postgres_dsn: str = "postgresql://sediment:sediment@localhost:5432/sediment"

    # Gemini
    gemini_api_key: str = ""
    gemini_extraction_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"


settings = Settings()
