# services/extraction/app/db.py
import logging

import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import Json, execute_batch

from app.config import settings
from app.graph_models import CanonicalizedEntity

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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
                canonical_name TEXT        NOT NULL UNIQUE,
                entity_type    TEXT        NOT NULL,
                aliases        TEXT[]      NOT NULL DEFAULT '{}',
                part_number    TEXT,
                embedding      vector(768) NOT NULL,
                created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS entities_embedding_hnsw
                ON entities USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
        """)
    conn.commit()
    # register_vector after the extension is guaranteed to exist
    register_vector(conn)


def get_all_entities() -> list[dict]:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT canonical_name, aliases FROM entities")
        return [
            {"canonical_name": row[0], "aliases": row[1]}
            for row in cur.fetchall()
        ]


def write_entities(entities: list[CanonicalizedEntity]) -> None:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            for e in entities:
                cur.execute(
                    """
                    INSERT INTO entities
                        (canonical_name, entity_type, aliases, part_number, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    ON CONFLICT (canonical_name) DO UPDATE SET
                        aliases    = EXCLUDED.aliases,
                        updated_at = now()
                    """,
                    (
                        e.canonical_name,
                        e.entity_type.value,
                        e.aliases,
                        e.part_number,
                        e.embedding,
                    ),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def update_entity_aliases(alias_updates: dict[str, list[str]]) -> None:
    if not alias_updates:
        return
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            for canonical_name, merged_aliases in alias_updates.items():
                cur.execute(
                    "UPDATE entities SET aliases = %s, updated_at = now() "
                    "WHERE canonical_name = %s",
                    (merged_aliases, canonical_name),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


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


def find_closest_entity(embedding: list[float], threshold: float) -> dict | None:
    conn = _get_conn()
    register_vector(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT canonical_name, aliases,
                   1 - (embedding <=> %s::vector) AS sim
            FROM entities
            ORDER BY embedding <=> %s::vector
            LIMIT 1
            """,
            (embedding, embedding),
        )
        row = cur.fetchone()
        if row is None or row[2] < threshold:
            return None
        return {"canonical_name": row[0], "aliases": row[1]}
