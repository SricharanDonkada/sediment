import logging

import psycopg2
import psycopg2.pool
from pgvector.psycopg2 import register_vector
from psycopg2.extras import RealDictCursor

from app.config import settings

log = logging.getLogger("knowledge_api.db")

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    _pool = psycopg2.pool.ThreadedConnectionPool(
        settings.db_pool_min,
        settings.db_pool_max,
        settings.postgres_dsn,
    )
    conn = _pool.getconn()
    try:
        register_vector(conn)
    finally:
        _pool.putconn(conn)


def close_pool() -> None:
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


def _get_conn():
    return _pool.getconn()


def _put_conn(conn) -> None:
    _pool.putconn(conn)


def search_facts(
    embedding: list[float],
    top_k: int,
    category: str | None,
) -> list[dict]:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id::text, transcript_id, fact, category, entities,
                       source_quote, interpretation_confidence, created_at,
                       1 - (embedding <=> %s::vector) AS score
                FROM fact_chunks
                WHERE (%s IS NULL OR category = %s)
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (embedding, category, category, embedding, top_k),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        _put_conn(conn)


def get_fact_by_id(fact_id: str) -> dict | None:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id::text, transcript_id, fact, category, entities,
                       source_quote, interpretation_confidence, created_at
                FROM fact_chunks
                WHERE id = %s::uuid
                """,
                (fact_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        _put_conn(conn)


def list_facts(
    page: int,
    limit: int,
    category: str | None,
) -> tuple[list[dict], int]:
    offset = (page - 1) * limit
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id::text, transcript_id, fact, category, entities,
                       source_quote, interpretation_confidence, created_at
                FROM fact_chunks
                WHERE (%s IS NULL OR category = %s)
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (category, category, limit, offset),
            )
            rows = [dict(r) for r in cur.fetchall()]

            cur.execute(
                "SELECT COUNT(*) AS total FROM fact_chunks WHERE (%s IS NULL OR category = %s)",
                (category, category),
            )
            total = int(cur.fetchone()["total"])

            return rows, total
    finally:
        _put_conn(conn)


def get_stats() -> dict:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_facts,
                    COUNT(DISTINCT transcript_id) AS transcript_count,
                    COALESCE(AVG(interpretation_confidence), 0.0) AS avg_confidence
                FROM fact_chunks
                """
            )
            row = dict(cur.fetchone())

            cur.execute(
                """
                SELECT category, COUNT(*) AS cnt
                FROM fact_chunks
                GROUP BY category
                ORDER BY cnt DESC
                """
            )
            facts_by_category = {r["category"]: int(r["cnt"]) for r in cur.fetchall()}

            return {
                "total_facts": int(row["total_facts"]),
                "transcript_count": int(row["transcript_count"]),
                "avg_confidence": float(row["avg_confidence"]),
                "facts_by_category": facts_by_category,
            }
    finally:
        _put_conn(conn)
