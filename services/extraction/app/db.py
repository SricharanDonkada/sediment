# services/extraction/app/db.py
import logging

import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import Json, execute_batch

from app.config import settings

log = logging.getLogger("extraction.db")

_conn: psycopg2.extensions.connection | None = None


def _get_conn() -> psycopg2.extensions.connection:
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(settings.postgres_dsn)
    return _conn


def ensure_schema() -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fact_chunks (
                id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                transcript_id             TEXT NOT NULL,
                fact                      TEXT NOT NULL,
                category                  TEXT NOT NULL,
                entities                  JSONB NOT NULL DEFAULT '[]',
                source_quote              TEXT,
                interpretation_confidence FLOAT NOT NULL,
                embedding_text            TEXT NOT NULL,
                embedding                 vector(768),
                created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_transcript_fact UNIQUE (transcript_id, fact)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS fact_chunks_embedding_idx
                ON fact_chunks USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS fact_chunks_transcript_idx "
            "ON fact_chunks (transcript_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS fact_chunks_category_idx "
            "ON fact_chunks (category)"
        )
    conn.commit()
    # register_vector after the extension is guaranteed to exist
    register_vector(conn)


def store_facts(transcript_id: str, rows: list[dict]) -> None:
    if not rows:
        return
    conn = _get_conn()
    register_vector(conn)  # idempotent; re-registers if conn was reset after ensure_schema
    data = [{**row, "entities": Json(row["entities"])} for row in rows]
    try:
        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO fact_chunks (
                    transcript_id, fact, category, entities, source_quote,
                    interpretation_confidence, embedding_text, embedding
                ) VALUES (
                    %(transcript_id)s, %(fact)s, %(category)s, %(entities)s,
                    %(source_quote)s, %(interpretation_confidence)s,
                    %(embedding_text)s, %(embedding)s
                )
                ON CONFLICT (transcript_id, fact) DO NOTHING
                """,
                data,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
