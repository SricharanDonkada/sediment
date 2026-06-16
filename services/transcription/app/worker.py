import logging
import os

from app import pipeline, queue, storage
from app.config import settings
from sediment_schemas import IngestionMessage, TranscriptionMessage

log = logging.getLogger("transcription")


def process_one(raw: bytes) -> None:
    """Transcribe one claimed job: download → pipeline → store → enqueue.

    Raises on any failure (the caller dead-letters). Always deletes the
    temp audio file.
    """
    msg = IngestionMessage.model_validate_json(raw)
    # get_audio owns cleanup if the download fails; audio_path is only bound
    # on success, so the finally below never unlinks a nonexistent path.
    audio_path = storage.get_audio(msg.bucket, msg.object_key)
    try:
        script = pipeline.run(audio_path)
    finally:
        os.unlink(audio_path)

    stem = msg.object_key.rsplit(".", 1)[0]
    transcript_key = f"{stem}.txt"
    storage.put_transcript(transcript_key, script)
    queue.enqueue(
        TranscriptionMessage(
            object_key=transcript_key, bucket=settings.transcripts_bucket
        )
    )


def run_forever() -> None:
    """Claim jobs forever; ack on success, dead-letter on failure."""
    storage.ensure_bucket()
    log.info("transcription worker started")
    while True:
        raw = queue.claim()
        if raw is None:
            continue
        try:
            process_one(raw)
            queue.ack(raw)
        except Exception:  # noqa: BLE001 — any failure routes to dead-letter
            log.exception("transcription job failed; dead-lettering | raw=%r", raw[:200])
            queue.dead_letter(raw)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
