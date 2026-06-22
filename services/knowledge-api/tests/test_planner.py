import json
from unittest.mock import MagicMock

from app.planner import EMPTY_PLAN, GraphPlan


def _mock_genai(monkeypatch, response_text: str):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(text=response_text)
    monkeypatch.setattr("app.planner._client", mock_client)
    return mock_client


def test_plan_returns_entity_and_operations_for_named_entity_query(monkeypatch):
    _mock_genai(monkeypatch, '{"entity": "TXV", "operations": ["get_compatible"]}')

    from app.planner import plan
    result = plan("what's compatible with a TXV?")

    assert result.entity == "TXV"
    assert result.operations == ["get_compatible"]


def test_plan_returns_empty_plan_for_situational_query(monkeypatch):
    _mock_genai(monkeypatch, '{"entity": null, "operations": []}')

    from app.planner import plan
    result = plan("how do I check superheat?")

    assert result == EMPTY_PLAN


def test_plan_filters_unknown_operations(monkeypatch):
    _mock_genai(
        monkeypatch,
        '{"entity": "filter dryer", "operations": ["get_compatible", "get_magic_thing"]}',
    )

    from app.planner import plan
    result = plan("what works with a filter dryer?")

    assert result.entity == "filter dryer"
    assert result.operations == ["get_compatible"]
    assert "get_magic_thing" not in result.operations


def test_plan_returns_empty_plan_on_json_parse_error(monkeypatch):
    _mock_genai(monkeypatch, "not valid json at all")

    from app.planner import plan
    result = plan("test query")

    assert result == EMPTY_PLAN


def test_plan_returns_empty_plan_on_gemini_api_error(monkeypatch):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("API down")
    monkeypatch.setattr("app.planner._client", mock_client)

    from app.planner import plan
    result = plan("test query")

    assert result == EMPTY_PLAN


def test_plan_multiple_valid_operations(monkeypatch):
    _mock_genai(
        monkeypatch,
        '{"entity": "Carrier 38HDC", "operations": ["get_compatible", "get_requires"]}',
    )

    from app.planner import plan
    result = plan("what does a Carrier 38HDC need and what works with it?")

    assert result.entity == "Carrier 38HDC"
    assert "get_compatible" in result.operations
    assert "get_requires" in result.operations
