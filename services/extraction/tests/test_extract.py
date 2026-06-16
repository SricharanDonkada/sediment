# services/extraction/tests/test_extract.py
import json
import pytest
from app import extract
from app.models import ExtractedFact


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client(response_text: str):
    """Return a fake genai.Client whose generate_content returns response_text."""
    class FakeResponse:
        text = response_text

    class FakeModels:
        def generate_content(self, model, contents, config):
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    return FakeClient()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_run_returns_list_of_extracted_facts(monkeypatch):
    payload = json.dumps([
        {
            "fact": "Pre-made condensate traps are too shallow for HVAC units over 5 tons.",
            "category": "sizing_rule",
            "entities": ["condensate trap"],
            "source_quote": "the pre-made traps are too shallow",
            "interpretation_confidence": 0.9,
        }
    ])
    monkeypatch.setattr(extract, "_get_client", lambda: _make_client(payload))

    facts = extract.run("SPEAKER_A: the pre-made traps are too shallow for big units")

    assert len(facts) == 1
    assert isinstance(facts[0], ExtractedFact)
    assert facts[0].category == "sizing_rule"


def test_run_filters_low_confidence_facts(monkeypatch):
    payload = json.dumps([
        {
            "fact": "High confidence fact.",
            "category": "specification",
            "entities": [],
            "source_quote": "speaker said this",
            "interpretation_confidence": 0.8,
        },
        {
            "fact": "Low confidence fact.",
            "category": "specification",
            "entities": [],
            "source_quote": "unclear mumbling",
            "interpretation_confidence": 0.3,
        },
    ])
    monkeypatch.setattr(extract, "_get_client", lambda: _make_client(payload))

    facts = extract.run("some transcript")

    assert len(facts) == 1
    assert facts[0].fact == "High confidence fact."


def test_run_normalises_unknown_category(monkeypatch):
    payload = json.dumps([
        {
            "fact": "Some fact.",
            "category": "totally_unknown_type",
            "entities": [],
            "source_quote": "speaker said something",
            "interpretation_confidence": 0.7,
        }
    ])
    monkeypatch.setattr(extract, "_get_client", lambda: _make_client(payload))

    facts = extract.run("some transcript")

    assert facts[0].category == "general"


def test_run_returns_empty_list_for_empty_llm_response(monkeypatch):
    monkeypatch.setattr(extract, "_get_client", lambda: _make_client("[]"))
    facts = extract.run("some transcript")
    assert facts == []


def test_run_raises_on_invalid_json(monkeypatch):
    monkeypatch.setattr(extract, "_get_client", lambda: _make_client("not json at all"))
    with pytest.raises(json.JSONDecodeError):
        extract.run("some transcript")
