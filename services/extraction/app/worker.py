# services/extraction/app/worker.py
import logging

from app import db, graph_db, pipeline, queue, storage
from sediment_schemas import TranscriptionMessage

log = logging.getLogger("extraction")


def process_one(raw: bytes) -> None:
    msg = TranscriptionMessage.model_validate_json(raw)
    text = storage.get_transcript(msg.bucket, msg.object_key)
    pipeline.run(transcript_id=msg.object_key, text=text)


def run_forever() -> None:
    db.ensure_schema()
    graph_db.ensure_schema()
    log.info("extraction worker started")
    while True:
        raw = queue.claim()
        if raw is None:
            continue
        try:
            process_one(raw)
            queue.ack(raw)
        except Exception:
            log.exception("extraction job failed; dead-lettering | raw=%r", raw[:200])
            queue.dead_letter(raw)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
