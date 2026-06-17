from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app import retrieve as r
from app.models import FactResult

SAMPLE_ROW = {
    "id": "00000000-0000-0000-0000-000000000001",
    "transcript_id": "t1",
    "fact": "Pre-made condensate traps are too shallow for units over 5 tons.",
    "category": "sizing_rule",
    "entities": ["condensate trap"],
    "source_quote": "the traps are too shallow",
    "interpretation_confidence": 0.9,
    "created_at": datetime(2026, 6, 17, tzinfo=timezone.utc),
    "score": 0.87,
}


def test_graph_retrieve_always_returns_empty():
    assert r._graph_retrieve([0.1] * 768, None) == []
    assert r._graph_retrieve([0.1] * 768, "compatibility") == []


def test_merge_deduplicates_keeping_higher_score():
    low = {**SAMPLE_ROW, "score": 0.7}
    high = {**SAMPLE_ROW, "score": 0.92}
    result = r._merge([low], [high], top_k=10, min_score=0.0)
    assert len(result) == 1
    assert result[0]["score"] == 0.92


def test_merge_filters_below_min_score():
    low = {**SAMPLE_ROW, "id": "low", "score": 0.3}
    high = {**SAMPLE_ROW, "id": "high", "score": 0.8}
    result = r._merge([low, high], [], top_k=10, min_score=0.5)
    assert len(result) == 1
    assert result[0]["id"] == "high"


def test_merge_respects_top_k():
    rows = [{**SAMPLE_ROW, "id": str(i), "score": i / 10.0} for i in range(10)]
    result = r._merge(rows, [], top_k=3, min_score=0.0)
    assert len(result) == 3


def test_merge_sorts_by_score_descending():
    rows = [
        {**SAMPLE_ROW, "id": "a", "score": 0.6},
        {**SAMPLE_ROW, "id": "b", "score": 0.9},
        {**SAMPLE_ROW, "id": "c", "score": 0.75},
    ]
    result = r._merge(rows, [], top_k=10, min_score=0.0)
    scores = [r["score"] for r in result]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_calls_graph_for_graph_category():
    with patch("app.retrieve.embed.embed_query", return_value=[0.1] * 768), \
         patch("app.retrieve._vector_retrieve", return_value=[]), \
         patch("app.retrieve._graph_retrieve", return_value=[]) as mock_graph:
        r.retrieve("test", top_k=5, min_score=0.5, category="compatibility")
        mock_graph.assert_called_once()


def test_retrieve_skips_graph_for_non_graph_category():
    with patch("app.retrieve.embed.embed_query", return_value=[0.1] * 768), \
         patch("app.retrieve._vector_retrieve", return_value=[]), \
         patch("app.retrieve._graph_retrieve", return_value=[]) as mock_graph:
        r.retrieve("test", top_k=5, min_score=0.5, category="sizing_rule")
        mock_graph.assert_not_called()


def test_retrieve_returns_fact_results():
    with patch("app.retrieve.embed.embed_query", return_value=[0.1] * 768), \
         patch("app.retrieve._vector_retrieve", return_value=[SAMPLE_ROW]):
        results = r.retrieve("trap depth", top_k=10, min_score=0.5, category=None)

    assert len(results) == 1
    assert isinstance(results[0], FactResult)
    assert results[0].score == 0.87


def test_retrieve_calls_graph_when_no_category_filter():
    with patch("app.retrieve.embed.embed_query", return_value=[0.1] * 768), \
         patch("app.retrieve._vector_retrieve", return_value=[]), \
         patch("app.retrieve._graph_retrieve", return_value=[]) as mock_graph:
        r.retrieve("test", top_k=5, min_score=0.5, category=None)
        mock_graph.assert_called_once()
