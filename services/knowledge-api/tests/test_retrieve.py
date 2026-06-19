from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app import retrieve as r
from app.models import FactResult
from app.planner import EMPTY_PLAN

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
    "source": "vector",
}


def test_merge_deduplicates_keeping_higher_score():
    low = FactResult(**{**SAMPLE_ROW, "score": 0.7})
    high = FactResult(**{**SAMPLE_ROW, "score": 0.92})
    result = r._merge([low], [high], top_k=10, min_score=0.0)
    assert len(result) == 1
    assert result[0].score == 0.92


def test_merge_filters_below_min_score():
    low = FactResult(**{**SAMPLE_ROW, "id": "low", "score": 0.3})
    high = FactResult(**{**SAMPLE_ROW, "id": "high", "score": 0.8})
    result = r._merge([low, high], [], top_k=10, min_score=0.5)
    assert len(result) == 1
    assert result[0].id == "high"


def test_merge_respects_top_k():
    rows = [FactResult(**{**SAMPLE_ROW, "id": str(i), "score": i / 10.0}) for i in range(10)]
    result = r._merge(rows, [], top_k=3, min_score=0.0)
    assert len(result) == 3


def test_merge_sorts_by_score_descending():
    rows = [
        FactResult(**{**SAMPLE_ROW, "id": "a", "score": 0.6}),
        FactResult(**{**SAMPLE_ROW, "id": "b", "score": 0.9}),
        FactResult(**{**SAMPLE_ROW, "id": "c", "score": 0.75}),
    ]
    result = r._merge(rows, [], top_k=10, min_score=0.0)
    scores = [row.score for row in result]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_returns_fact_results():
    sample = FactResult(**SAMPLE_ROW)
    with patch("app.retrieve.embed.embed_query", return_value=[0.1] * 768), \
         patch("app.retrieve._vector_retrieve", return_value=[sample]), \
         patch("app.retrieve.planner.plan", return_value=EMPTY_PLAN):
        results = r.retrieve("trap depth", top_k=10, min_score=0.5, category=None)

    assert len(results) == 1
    assert isinstance(results[0], FactResult)
    assert results[0].score == 0.87


def test_retrieve_skips_graph_when_plan_has_no_entity():
    from app.planner import GraphPlan
    with patch("app.retrieve.planner.plan", return_value=GraphPlan(entity=None, operations=[])), \
         patch("app.retrieve.embed.embed_query", return_value=[0.1] * 768), \
         patch("app.retrieve._vector_retrieve", return_value=[]), \
         patch("app.retrieve.graph.execute_operations") as mock_graph:
        r.retrieve("how do I install a TXV?", top_k=5, min_score=0.5, category=None)

    mock_graph.assert_not_called()


def test_retrieve_skips_graph_when_entity_resolution_fails():
    from app.planner import GraphPlan
    with patch("app.retrieve.planner.plan", return_value=GraphPlan(entity="TXV", operations=["get_compatible"])), \
         patch("app.retrieve.entity_resolve.resolve", return_value=None), \
         patch("app.retrieve.embed.embed_query", return_value=[0.1] * 768), \
         patch("app.retrieve._vector_retrieve", return_value=[]), \
         patch("app.retrieve.graph.execute_operations") as mock_graph:
        r.retrieve("what works with a TXV?", top_k=5, min_score=0.5, category=None)

    mock_graph.assert_not_called()


def test_retrieve_calls_graph_when_entity_resolves():
    from app.planner import GraphPlan
    graph_result = FactResult(
        id="g1", transcript_id=None, fact=None, category="compatible_with",
        entities=["TXV", "R-410A"], source_quote=None, interpretation_confidence=0.9,
        created_at=None, score=0.9, source="graph", subject="TXV",
        predicate="compatible_with", object="R-410A",
    )
    with patch("app.retrieve.planner.plan", return_value=GraphPlan(entity="TXV", operations=["get_compatible"])), \
         patch("app.retrieve.entity_resolve.resolve", return_value="TXV"), \
         patch("app.retrieve.graph.execute_operations", return_value=[graph_result]) as mock_graph, \
         patch("app.retrieve.embed.embed_query", return_value=[0.1] * 768), \
         patch("app.retrieve._vector_retrieve", return_value=[]):
        results = r.retrieve("what's compatible with a TXV?", top_k=5, min_score=0.0, category=None)

    mock_graph.assert_called_once_with("TXV", ["get_compatible"])
    assert len(results) == 1
    assert results[0].source == "graph"


def test_retrieve_vector_always_runs_regardless_of_plan():
    from app.planner import GraphPlan
    with patch("app.retrieve.planner.plan", return_value=EMPTY_PLAN), \
         patch("app.retrieve.embed.embed_query", return_value=[0.1] * 768), \
         patch("app.retrieve._vector_retrieve", return_value=[]) as mock_vec:
        r.retrieve("general question", top_k=5, min_score=0.5, category=None)

    mock_vec.assert_called_once()


def test_vector_retrieve_injects_source_vector():
    with patch("app.db.search_facts", return_value=[{
        "id": "x", "transcript_id": "t1", "fact": "a fact", "category": "c",
        "entities": [], "source_quote": None, "interpretation_confidence": 0.8,
        "created_at": None, "score": 0.75,
    }]):
        from app.retrieve import _vector_retrieve
        results = _vector_retrieve([0.1] * 768, top_k=5, category=None, min_score=0.0)

    assert len(results) == 1
    assert results[0].source == "vector"
    assert isinstance(results[0], FactResult)


def test_merge_mixed_vector_and_graph_results():
    from app.models import FactResult
    vector_fact = FactResult(**{**SAMPLE_ROW, "id": "v1", "score": 0.8, "source": "vector"})
    graph_fact = FactResult(**{
        **SAMPLE_ROW,
        "id": "g1",
        "score": 0.75,
        "source": "graph",
        "subject": "partA",
        "predicate": "compatible_with",
        "object": "partB",
        "fact": None,
        "transcript_id": None,
        "created_at": None,
    })
    result = r._merge([vector_fact], [graph_fact], top_k=10, min_score=0.5)
    ids = [row.id for row in result]
    assert "v1" in ids
    assert "g1" in ids
    assert result[0].score >= result[1].score  # sorted descending
