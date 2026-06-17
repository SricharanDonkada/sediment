import pytest
from unittest.mock import patch
from datetime import datetime, timezone
from app.models import FactResult


def test_get_stats(client):
    with patch("app.db.get_stats", return_value={
        "total_facts": 42,
        "facts_by_category": {"sizing_rule": 12, "compatibility": 8},
        "transcript_count": 5,
        "avg_confidence": 0.87,
    }):
        resp = client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_facts"] == 42
    assert data["facts_by_category"]["sizing_rule"] == 12
    assert data["transcript_count"] == 5
    assert data["avg_confidence"] == pytest.approx(0.87)


SAMPLE_FACT = FactResult(
    id="00000000-0000-0000-0000-000000000001",
    transcript_id="t1",
    fact="Pre-made condensate traps are too shallow for units over 5 tons.",
    category="sizing_rule",
    entities=["condensate trap"],
    source_quote="the traps are too shallow",
    interpretation_confidence=0.9,
    created_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
    score=None,
)


def test_list_facts(client):
    row = SAMPLE_FACT.model_dump()
    with patch("app.db.list_facts", return_value=([row], 1)):
        resp = client.get("/facts?page=1&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["limit"] == 10
    assert len(data["facts"]) == 1
    assert data["facts"][0]["fact"] == SAMPLE_FACT.fact


def test_list_facts_passes_category_filter(client):
    with patch("app.db.list_facts", return_value=([], 0)) as mock_list:
        client.get("/facts?category=sizing_rule")
    mock_list.assert_called_once_with(1, 50, "sizing_rule")


def test_get_fact_by_id(client):
    row = SAMPLE_FACT.model_dump()
    with patch("app.db.get_fact_by_id", return_value=row):
        resp = client.get(f"/facts/{SAMPLE_FACT.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == SAMPLE_FACT.id


def test_get_fact_by_id_not_found(client):
    with patch("app.db.get_fact_by_id", return_value=None):
        resp = client.get("/facts/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


SAMPLE_FACT_WITH_SCORE = FactResult(
    id="abc-123",
    transcript_id="t1",
    fact="Pre-made condensate traps are too shallow for units over 5 tons.",
    category="sizing_rule",
    entities=["condensate trap"],
    source_quote="the traps are too shallow",
    interpretation_confidence=0.9,
    created_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
    score=0.87,
)


def test_post_query_returns_facts_and_synthesis(client):
    with patch("app.retrieve.retrieve", return_value=[SAMPLE_FACT_WITH_SCORE]), \
         patch("app.synthesis.synthesize", return_value="Use 6-inch traps."):
        resp = client.post("/query", json={
            "query": "How deep should condensate traps be?",
            "top_k": 5,
            "min_score": 0.5,
            "synthesize": True,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["facts"]) == 1
    assert data["facts"][0]["score"] == pytest.approx(0.87)
    assert data["synthesis"] == "Use 6-inch traps."
    assert data["query_used"] == "How deep should condensate traps be?"


def test_post_query_skips_synthesis_when_disabled(client):
    with patch("app.retrieve.retrieve", return_value=[SAMPLE_FACT_WITH_SCORE]), \
         patch("app.synthesis.synthesize") as mock_synth:
        resp = client.post("/query", json={"query": "test", "synthesize": False})
    assert resp.status_code == 200
    assert resp.json()["synthesis"] is None
    mock_synth.assert_not_called()


def test_post_query_passes_params_to_retrieve(client):
    with patch("app.retrieve.retrieve", return_value=[]) as mock_retrieve, \
         patch("app.synthesis.synthesize", return_value=None):
        client.post("/query", json={
            "query": "test query",
            "top_k": 3,
            "min_score": 0.7,
            "category": "sizing_rule",
        })
    mock_retrieve.assert_called_once_with("test query", 3, 0.7, "sizing_rule")


def test_post_query_returns_empty_synthesis_when_no_facts(client):
    with patch("app.retrieve.retrieve", return_value=[]), \
         patch("app.synthesis.synthesize", return_value=None):
        resp = client.post("/query", json={"query": "unknown topic", "synthesize": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["facts"] == []
    assert data["synthesis"] is None
