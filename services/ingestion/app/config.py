from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Defaults match docker-compose.yml for local dev.

    Field names map case-insensitively to env vars (e.g. minio_endpoint
    ← MINIO_ENDPOINT).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "sediment"
    minio_root_password: str = "sediment-dev"
    minio_secure: bool = False
    ingestion_bucket: str = "audio"

    redis_url: str = "redis://localhost:6379/0"
    ingestion_queue: str = "audio-transcribe"


settings = Settings()
