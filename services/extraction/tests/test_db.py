# services/extraction/tests/test_db.py
import pytest

from app import db


# ── Unit tests ────────────────────────────────────────────────────────────────

def test_store_facts_no_op_for_empty_list(monkeypatch):
    """store_facts with an empty list must not touch the database."""
    conn_called = []
    monkeypatch.setattr(db, "_get_conn", lambda: conn_called.append(1))
    db.store_facts("t1", [])
    assert conn_called == []


def test_store_facts_calls_execute_batch(monkeypatch):
    """store_facts must call execute_batch with one row per fact."""
    batched = {}

    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass

    class FakeConn:
        def cursor(self): return FakeCursor()
        def commit(self): pass

    def fake_execute_batch(cur, sql, data):
        batched["data"] = data

    monkeypatch.setattr(db, "_get_conn", lambda: FakeConn())
    monkeypatch.setattr(db, "execute_batch", fake_execute_batch)
    monkeypatch.setattr(db, "register_vector", lambda conn: None)

    rows = [
        {
            "transcript_id": "abc.txt",
            "fact": "Traps over 5 tons need 4-inch depth.",
            "category": "sizing_rule",
            "entities": ["condensate trap"],
            "source_quote": "the trap depth should be at least 4 inches",
            "interpretation_confidence": 0.9,
            "embedding_text": "[sizing_rule] Traps over 5 tons need 4-inch depth.\nEntities: condensate trap",
            "embedding": [0.1] * 768,
        }
    ]
    db.store_facts("abc.txt", rows)

    assert len(batched["data"]) == 1
    row = batched["data"][0]
    assert row["transcript_id"] == "abc.txt"
    assert row["fact"] == "Traps over 5 tons need 4-inch depth."


def test_ensure_schema_executes_ddl(monkeypatch):
    """ensure_schema must execute CREATE EXTENSION and CREATE TABLE."""
    executed = []

    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql):
            executed.append(sql.strip())

    class FakeConn:
        def cursor(self): return FakeCursor()
        def commit(self): pass

    monkeypatch.setattr(db, "_get_conn", lambda: FakeConn())
    monkeypatch.setattr(db, "register_vector", lambda conn: None)
    db.ensure_schema()

    sql_blob = " ".join(executed)
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql_blob
    assert "CREATE TABLE IF NOT EXISTS fact_chunks" in sql_blob
    assert "hnsw" in sql_blob


# ── Integration tests (require live Postgres) ─────────────────────────────────

@pytest.mark.integration
def test_ensure_schema_is_idempotent():
    """Running ensure_schema twice must not raise."""
    db.ensure_schema()
    db.ensure_schema()


@pytest.mark.integration
def test_store_facts_inserts_and_deduplicates():
    """Re-running store_facts with same transcript_id+fact is a no-op."""
    db.ensure_schema()

    rows = [
        {
            "transcript_id": "test-dedup.txt",
            "fact": "Test fact for deduplication.",
            "category": "specification",
            "entities": ["part-A"],
            "source_quote": "speaker said this",
            "interpretation_confidence": 0.85,
            "embedding_text": "[specification] Test fact for deduplication.\nEntities: part-A",
            "embedding": [0.0] * 768,
        }
    ]
    db.store_facts("test-dedup.txt", rows)
    db.store_facts("test-dedup.txt", rows)  # second call must not raise

    conn = db._get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM fact_chunks WHERE transcript_id = %s",
            ("test-dedup.txt",),
        )
        count = cur.fetchone()[0]

    assert count == 1

    # cleanup
    with conn.cursor() as cur:
        cur.execute("DELETE FROM fact_chunks WHERE transcript_id = %s", ("test-dedup.txt",))
    conn.commit()
