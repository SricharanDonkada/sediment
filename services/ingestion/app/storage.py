import io

from minio import Minio

from app.config import settings

_minio: Minio | None = None


def _client() -> Minio:
    """Lazily build a singleton MinIO client from settings."""
    global _minio
    if _minio is None:
        _minio = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=settings.minio_secure,
        )
    return _minio


def ensure_bucket() -> None:
    """Create the ingestion bucket if it does not already exist."""
    client = _client()
    if not client.bucket_exists(settings.ingestion_bucket):
        client.make_bucket(settings.ingestion_bucket)


def put(key: str, data: bytes) -> None:
    """Store WAV bytes under `key` in the ingestion bucket."""
    _client().put_object(
        settings.ingestion_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type="audio/wav",
    )
