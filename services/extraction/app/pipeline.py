# services/extraction/app/pipeline.py
import logging

from app import db, embed, extract

log = logging.getLogger("extraction.pipeline")


def run(transcript_id: str, text: str) -> None:
    facts = extract.run(text)
    if not facts:
        log.info("no facts extracted | transcript_id=%s", transcript_id)
        return

    rows = []
    for fact in facts:
        embedding_text = embed.build_embedding_text(fact)
        vector = embed.embed_document(embedding_text)
        rows.append({
            "transcript_id": transcript_id,
            "fact": fact.fact,
            "category": fact.category,
            "entities": fact.entities,
            "source_quote": fact.source_quote,
            "interpretation_confidence": fact.interpretation_confidence,
            "embedding_text": embedding_text,
            "embedding": vector,
        })

    db.store_facts(transcript_id, rows)
