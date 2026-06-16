# services/extraction/app/storage.py
from minio import Minio

from app.config import settings

_minio: Minio | None = None


def _client() -> Minio:
    global _minio
    if _minio is None:
        _minio = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=settings.minio_secure,
        )
    return _minio


def get_transcript(bucket: str, key: str) -> str:
    response = _client().get_object(bucket, key)
    try:
        return response.read().decode("utf-8")
    finally:
        response.close()
        response.release_conn()
