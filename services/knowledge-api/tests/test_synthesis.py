from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.models import FactResult

SAMPLE_FACT = FactResult(
    id="abc-123",
    transcript_id="t1",
    fact="Pre-made condensate traps are too shallow for units over 5 tons.",
    category="sizing_rule",
    entities=["condensate trap"],
    source_quote="the traps are too shallow",
    interpretation_confidence=0.9,
    created_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
    score=0.87,
    source="vector",
)


def test_synthesize_returns_none_for_empty_facts():
    from app.synthesis import synthesize
    assert synthesize("test query", []) is None


def test_synthesize_calls_gemini_and_returns_text(monkeypatch):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(
        text="Use 6-inch traps for units over 5 tons."
    )
    monkeypatch.setattr("app.synthesis._client", mock_client)

    from app.synthesis import synthesize
    result = synthesize("How deep should traps be?", [SAMPLE_FACT])

    assert result == "Use 6-inch traps for units over 5 tons."
    mock_client.models.generate_content.assert_called_once()


def test_synthesize_includes_fact_id_and_text_in_prompt(monkeypatch):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(text="answer")
    monkeypatch.setattr("app.synthesis._client", mock_client)

    from app.synthesis import synthesize
    synthesize("How deep should traps be?", [SAMPLE_FACT])

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    prompt = call_kwargs.get("contents", "")
    assert SAMPLE_FACT.id in prompt
    assert SAMPLE_FACT.fact in prompt
