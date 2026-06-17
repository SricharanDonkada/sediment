import pytest
from unittest.mock import patch


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
