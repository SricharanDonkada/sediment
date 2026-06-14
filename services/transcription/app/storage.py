import io
import os
import tempfile

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
    """Create the transcripts bucket if it does not already exist."""
    client = _client()
    if not client.bucket_exists(settings.transcripts_bucket):
        client.make_bucket(settings.transcripts_bucket)


def get_audio(bucket: str, key: str) -> str:
    """Download the audio object to a temp .wav file and return its path.

    The caller owns the file and must delete it. If the download fails, the
    temp file is removed before the error propagates.
    """
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        _client().fget_object(bucket, key, path)
    except Exception:
        os.unlink(path)
        raise
    return path


def put_transcript(key: str, text: str) -> None:
    """Store the transcript text as a UTF-8 .txt object in the transcripts bucket."""
    data = text.encode("utf-8")
    _client().put_object(
        settings.transcripts_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type="text/plain; charset=utf-8",
    )
