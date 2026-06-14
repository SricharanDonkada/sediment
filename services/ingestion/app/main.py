import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from app import audio, queue, storage, youtube
from app.audio import AudioProcessingError
from app.config import settings
from app.youtube import YouTubeDownloadError
from sediment_schemas import IngestionMessage

_INDEX_HTML = (Path(__file__).parent / "templates" / "index.html").read_text(
    encoding="utf-8"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.ensure_bucket()
    yield


app = FastAPI(title="Sediment Ingestion", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX_HTML


@app.post("/ingest")
def ingest(
    file: UploadFile | None = File(default=None),
    youtube_url: str | None = Form(default=None),
) -> dict:
    has_file = file is not None
    has_url = bool(youtube_url and youtube_url.strip())
    if has_file == has_url:  # neither, or both
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of: an audio file or a YouTube URL.",
        )

    # 1. Get audio bytes (normalized to 16kHz mono WAV).
    try:
        if has_file:
            suffix = Path(file.filename or "").suffix
            wav = audio.normalize(file.file.read(), suffix=suffix)
        else:
            path = youtube.download(youtube_url.strip())
            try:
                wav = audio.normalize(path)
            finally:
                # download() places the file in a dedicated temp dir; remove it.
                shutil.rmtree(Path(path).parent, ignore_errors=True)
    except YouTubeDownloadError as exc:
        raise HTTPException(status_code=422, detail=f"YouTube download failed: {exc}")
    except AudioProcessingError:
        raise HTTPException(status_code=422, detail="Could not process audio.")

    # 2. Store, then enqueue (order matters: a stored-but-unqueued object is inert).
    object_key = f"{uuid.uuid4()}.wav"
    try:
        storage.put(object_key, wav)
    except Exception:  # noqa: BLE001 — MinIO unreachable / write failure
        raise HTTPException(status_code=503, detail="Storage unavailable.")

    try:
        queue.enqueue(
            IngestionMessage(object_key=object_key, bucket=settings.ingestion_bucket)
        )
    except Exception:  # noqa: BLE001 — Redis unreachable; stored object is harmless
        raise HTTPException(status_code=503, detail="Queue unavailable.")

    return {"object_key": object_key, "bucket": settings.ingestion_bucket}
