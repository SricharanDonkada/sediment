import json
import pytest
from pydantic import ValidationError
from app import graph_extract
from app.graph_models import (
    DomainEntityType,
    EntityCluster,
    RelationshipType,
)


def _make_cluster(candidate: str = "Some Entity") -> EntityCluster:
    return EntityCluster(
        mentions=[candidate],
        candidate_canonical=candidate,
        source_quotes=["some context quote"],
    )


def _make_llm_client(response_text: str):
    class FakeResponse:
        text = response_text

    class FakeModels:
        def generate_content(self, model, contents, config):
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    return FakeClient()


# ── mini-pass ─────────────────────────────────────────────────────────────────

def test_run_mini_pass_returns_canonicalized_entities(monkeypatch):
    payload = json.dumps({
        "entities": [{
            "canonical_name": "Taco 007 Circulator",
            "entity_type": "component",
            "aliases": ["007", "the pump"],
            "brand": "Taco",
            "part_number": None,
        }]
    })
    monkeypatch.setattr(graph_extract, "_get_client", lambda: _make_llm_client(payload))

    result = graph_extract.run_mini_pass([_make_cluster("Taco 007")])

    assert len(result) == 1
    assert result[0].canonical_name == "Taco 007 Circulator"
    assert result[0].entity_type == DomainEntityType.component
    assert result[0].brand == "Taco"
    assert not hasattr(result[0], "embedding") or "embedding" not in result[0].model_fields


def test_run_mini_pass_returns_empty_for_no_clusters(monkeypatch):
    client_calls = []
    monkeypatch.setattr(graph_extract, "_get_client", lambda: client_calls.append(1) or object())

    result = graph_extract.run_mini_pass([])

    assert result == []
    assert client_calls == []


def test_run_mini_pass_retries_on_invalid_json(monkeypatch):
    call_count = [0]
    valid = json.dumps({"entities": [{"canonical_name": "X", "entity_type": "brand", "aliases": []}]})

    class FakeModels:
        def generate_content(self, model, contents, config):
            call_count[0] += 1

            class R:
                text = "not json" if call_count[0] == 1 else valid

            return R()

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(graph_extract, "_get_client", lambda: FakeClient())

    result = graph_extract.run_mini_pass([_make_cluster("X")])

    assert len(result) == 1
    assert call_count[0] == 2


def test_run_mini_pass_raises_after_max_retries(monkeypatch):
    monkeypatch.setattr(graph_extract, "_get_client", lambda: _make_llm_client("not json at all"))

    with pytest.raises(json.JSONDecodeError):
        graph_extract.run_mini_pass([_make_cluster("X")])


# ── Pass 2 ────────────────────────────────────────────────────────────────────

def test_run_pass2_returns_relationships(monkeypatch):
    payload = json.dumps({
        "relationships": [{
            "subject_canonical": "TXV",
            "predicate": "fixes",
            "object_canonical": "High superheat",
            "confidence": 0.9,
            "evidence_quote": "the TXV should fix that",
            "predicate_description": None,
        }]
    })
    monkeypatch.setattr(graph_extract, "_get_client", lambda: _make_llm_client(payload))

    result = graph_extract.run_pass2("transcript text", ["TXV", "High superheat"])

    assert len(result) == 1
    assert result[0].subject_canonical == "TXV"
    assert result[0].predicate == RelationshipType.fixes
    assert result[0].confidence == pytest.approx(0.9)


def test_run_pass2_drops_low_confidence_relationships(monkeypatch):
    payload = json.dumps({
        "relationships": [
            {
                "subject_canonical": "TXV",
                "predicate": "fixes",
                "object_canonical": "High superheat",
                "confidence": 0.9,
            },
            {
                "subject_canonical": "TXV",
                "predicate": "compatible_with",
                "object_canonical": "Distributor",
                "confidence": 0.3,
            },
        ]
    })
    monkeypatch.setattr(graph_extract, "_get_client", lambda: _make_llm_client(payload))

    result = graph_extract.run_pass2("transcript", ["TXV", "High superheat", "Distributor"])

    assert len(result) == 1
    assert result[0].predicate == RelationshipType.fixes


def test_run_pass2_drops_exactly_at_threshold(monkeypatch):
    payload = json.dumps({
        "relationships": [{
            "subject_canonical": "A",
            "predicate": "replaces",
            "object_canonical": "B",
            "confidence": 0.5,
        }]
    })
    monkeypatch.setattr(graph_extract, "_get_client", lambda: _make_llm_client(payload))

    result = graph_extract.run_pass2("transcript", ["A", "B"])
    assert len(result) == 1  # 0.5 is kept (filter is < 0.5, not <=)


def test_run_pass2_returns_empty_for_no_relationships(monkeypatch):
    payload = json.dumps({"relationships": []})
    monkeypatch.setattr(graph_extract, "_get_client", lambda: _make_llm_client(payload))

    result = graph_extract.run_pass2("transcript", ["Entity A"])
    assert result == []


def test_run_pass2_retries_on_validation_error(monkeypatch):
    call_count = [0]
    bad = json.dumps({"relationships": [{"subject_canonical": "A", "predicate": "INVALID_PREDICATE", "object_canonical": "B", "confidence": 0.9}]})
    good = json.dumps({"relationships": []})

    class FakeModels:
        def generate_content(self, model, contents, config):
            call_count[0] += 1

            class R:
                text = bad if call_count[0] == 1 else good

            return R()

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(graph_extract, "_get_client", lambda: FakeClient())

    result = graph_extract.run_pass2("t", ["A", "B"])
    assert result == []
    assert call_count[0] == 2
