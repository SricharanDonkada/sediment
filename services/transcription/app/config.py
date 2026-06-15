from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Defaults match docker-compose.yml for local dev.

    Field names map case-insensitively to env vars (e.g. whisper_device
    ← WHISPER_DEVICE).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "sediment"
    minio_root_password: str = "sediment-dev"
    minio_secure: bool = False
    transcripts_bucket: str = "transcripts"

    # Redis queues
    redis_url: str = "redis://localhost:6379/0"
    ingestion_queue: str = "audio-transcribe"
    transcription_processing_queue: str = "audio-transcribe:processing"
    transcription_queue: str = "extract"
    transcription_dead_queue: str = "audio-transcribe:dead"

    # Models
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    diarization_model: str = "pyannote/speaker-diarization-community-1"
    hf_token: str = ""


settings = Settings()
