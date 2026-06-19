from enum import Enum
from pydantic import BaseModel, Field


class EntityCluster(BaseModel):
    mentions: list[str]
    candidate_canonical: str
    source_quotes: list[str]


class MatchedEntity(BaseModel):
    canonical_name: str
    new_aliases: list[str]


class DomainEntityType(str, Enum):
    component = "component"
    system    = "system"
    condition = "condition"
    symptom   = "symptom"
    procedure = "procedure"
    brand     = "brand"
    supplier  = "supplier"


class CanonicalizedEntityResponse(BaseModel):
    """LLM output schema for the mini-pass. No embedding field."""
    canonical_name: str
    entity_type: DomainEntityType
    aliases: list[str]
    brand: str | None = None
    part_number: str | None = None


class EntityTypingOutput(BaseModel):
    entities: list[CanonicalizedEntityResponse]


class CanonicalizedEntity(CanonicalizedEntityResponse):
    """Full entity — adds embedding after LLM output is promoted in graph_pipeline."""
    embedding: list[float] = Field(default_factory=list)


class RelationshipType(str, Enum):
    compatible_with       = "compatible_with"
    incompatible_with     = "incompatible_with"
    replaces              = "replaces"
    supersedes            = "supersedes"
    requires              = "requires"
    part_of               = "part_of"
    commonly_ordered_with = "commonly_ordered_with"
    symptom_indicates     = "symptom_indicates"
    fixes                 = "fixes"
    manufactured_by       = "manufactured_by"
    supplied_by           = "supplied_by"
    other                 = "other"


class ExtractedRelationship(BaseModel):
    subject_canonical: str
    predicate: RelationshipType
    object_canonical: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quote: str | None = None
    predicate_description: str | None = None


class RelationshipExtractionOutput(BaseModel):
    relationships: list[ExtractedRelationship]
