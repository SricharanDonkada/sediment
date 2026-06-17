# services/extraction/tests/test_pipeline.py
import pytest
from app import pipeline
from app.models import ExtractedFact


def _make_fact(**kwargs) -> ExtractedFact:
    defaults = dict(
        fact="Some fact.",
        category="specification",
        entities=["part-A"],
        source_quote="speaker said this",
        interpretation_confidence=0.9,
    )
    return ExtractedFact(**{**defaults, **kwargs})


def test_pipeline_run_calls_embed_and_store(monkeypatch):
    fact = _make_fact()
    calls = {}

    monkeypatch.setattr(pipeline.extract, "run", lambda text: [fact])
    monkeypatch.setattr(pipeline.embed, "build_embedding_text", lambda f: "[specification] Some fact.\nEntities: part-A")
    monkeypatch.setattr(pipeline.embed, "embed_document", lambda text: [0.1] * 768)

    def fake_store_facts(transcript_id, rows):
        calls["transcript_id"] = transcript_id
        calls["rows"] = rows

    monkeypatch.setattr(pipeline.db, "store_facts", fake_store_facts)

    pipeline.run("t1.txt", "SPEAKER_A: speaker said this")

    assert calls["transcript_id"] == "t1.txt"
    assert len(calls["rows"]) == 1
    row = calls["rows"][0]
    assert row["transcript_id"] == "t1.txt"
    assert row["fact"] == "Some fact."
    assert row["category"] == "specification"
    assert row["entities"] == ["part-A"]
    assert row["embedding"] == [0.1] * 768
    assert row["embedding_text"] == "[specification] Some fact.\nEntities: part-A"


def test_pipeline_run_skips_store_when_no_facts(monkeypatch):
    store_called = []

    monkeypatch.setattr(pipeline.extract, "run", lambda text: [])
    monkeypatch.setattr(pipeline.db, "store_facts", lambda *a, **kw: store_called.append(1))

    pipeline.run("t1.txt", "empty transcript")

    assert store_called == []


def test_pipeline_run_builds_correct_row_shape(monkeypatch):
    fact = _make_fact(
        fact="Specific fact with entities.",
        category="diagnostic_sign",
        entities=["air handler", "rust"],
        source_quote="rust at the bottom",
        interpretation_confidence=0.85,
    )
    captured = {}

    monkeypatch.setattr(pipeline.extract, "run", lambda text: [fact])
    monkeypatch.setattr(pipeline.embed, "build_embedding_text",
                        lambda f: "[diagnostic_sign] Specific fact with entities.\nEntities: air handler, rust")
    monkeypatch.setattr(pipeline.embed, "embed_document", lambda text: [0.5] * 768)
    monkeypatch.setattr(pipeline.db, "store_facts",
                        lambda transcript_id, rows: captured.update({"rows": rows}))

    pipeline.run("transcript.txt", "SPEAKER_A: rust at the bottom")

    row = captured["rows"][0]
    assert set(row.keys()) == {
        "transcript_id", "fact", "category", "entities",
        "source_quote", "interpretation_confidence",
        "embedding_text", "embedding",
    }
    assert row["interpretation_confidence"] == pytest.approx(0.85)
    assert len(row["embedding"]) == 768
