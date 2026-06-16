import pytest
from pydantic import ValidationError
from app.models import ExtractedFact, VALID_CATEGORIES


def test_valid_fact():
    f = ExtractedFact(
        fact="Pre-made condensate traps are too shallow for units over 5 tons.",
        category="sizing_rule",
        entities=["condensate trap"],
        source_quote="the pre-made traps are too shallow",
        interpretation_confidence=0.9,
    )
    assert f.category == "sizing_rule"
    assert f.entities == ["condensate trap"]


def test_entities_defaults_to_empty_list():
    f = ExtractedFact(
        fact="Some fact.",
        category="specification",
        entities=[],
        source_quote="speaker said this",
        interpretation_confidence=0.8,
    )
    assert f.entities == []


def test_valid_categories_contains_all_16():
    assert len(VALID_CATEGORIES) == 16
    assert "compatibility" in VALID_CATEGORIES
    assert "application_condition" in VALID_CATEGORIES


def test_missing_required_field_raises():
    with pytest.raises(ValidationError):
        ExtractedFact(
            category="specification",
            entities=[],
            source_quote="quote",
            interpretation_confidence=0.8,
            # 'fact' missing
        )
