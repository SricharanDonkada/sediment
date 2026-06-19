import pytest
from pydantic import ValidationError
from app.graph_models import (
    CanonicalizedEntity,
    CanonicalizedEntityResponse,
    DomainEntityType,
    ExtractedRelationship,
    RelationshipType,
)


def test_canonicalized_entity_response_has_no_embedding_field():
    assert "embedding" not in CanonicalizedEntityResponse.model_fields


def test_canonicalized_entity_has_embedding_field():
    assert "embedding" in CanonicalizedEntity.model_fields


def test_canonicalized_entity_embedding_defaults_to_empty_list():
    entity = CanonicalizedEntity(
        canonical_name="Taco 007 Circulator",
        entity_type=DomainEntityType.component,
        aliases=["007"],
    )
    assert entity.embedding == []


def test_canonicalized_entity_inherits_response_fields():
    entity = CanonicalizedEntity(
        canonical_name="Taco 007 Circulator",
        entity_type=DomainEntityType.component,
        aliases=["007"],
        brand="Taco",
        part_number="1400-50RP",
        embedding=[0.1, 0.2],
    )
    assert entity.canonical_name == "Taco 007 Circulator"
    assert entity.brand == "Taco"
    assert entity.part_number == "1400-50RP"
    assert entity.embedding == [0.1, 0.2]


def test_extracted_relationship_confidence_above_one_rejected():
    with pytest.raises(ValidationError):
        ExtractedRelationship(
            subject_canonical="A",
            predicate=RelationshipType.replaces,
            object_canonical="B",
            confidence=1.1,
        )


def test_extracted_relationship_confidence_below_zero_rejected():
    with pytest.raises(ValidationError):
        ExtractedRelationship(
            subject_canonical="A",
            predicate=RelationshipType.replaces,
            object_canonical="B",
            confidence=-0.1,
        )


def test_extracted_relationship_valid_at_bounds():
    low = ExtractedRelationship(
        subject_canonical="A", predicate=RelationshipType.fixes,
        object_canonical="B", confidence=0.0,
    )
    high = ExtractedRelationship(
        subject_canonical="A", predicate=RelationshipType.fixes,
        object_canonical="B", confidence=1.0,
    )
    assert low.confidence == 0.0
    assert high.confidence == 1.0


def test_all_domain_entity_types_present():
    expected = {"component", "system", "condition", "symptom", "procedure", "brand", "supplier"}
    assert {t.value for t in DomainEntityType} == expected


def test_all_relationship_types_present():
    expected = {
        "compatible_with", "incompatible_with", "replaces", "supersedes",
        "requires", "part_of", "commonly_ordered_with", "symptom_indicates",
        "fixes", "manufactured_by", "supplied_by", "other",
    }
    assert {t.value for t in RelationshipType} == expected
