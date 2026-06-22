import logging

from neo4j import GraphDatabase

from app.config import settings
from app.graph_models import CanonicalizedEntity, ExtractedRelationship, RelationshipType

log = logging.getLogger("extraction.graph_db")

_driver = None

_SYMMETRIC_PREDICATES = {
    RelationshipType.compatible_with,
    RelationshipType.incompatible_with,
    RelationshipType.commonly_ordered_with,
}

_REL_TYPE_MAP: dict[str, str] = {
    "compatible_with":       "COMPATIBLE_WITH",
    "incompatible_with":     "INCOMPATIBLE_WITH",
    "replaces":              "REPLACES",
    "supersedes":            "SUPERSEDES",
    "requires":              "REQUIRES",
    "part_of":               "PART_OF",
    "commonly_ordered_with": "COMMONLY_ORDERED_WITH",
    "symptom_indicates":     "SYMPTOM_INDICATES",
    "fixes":                 "FIXES",
    "manufactured_by":       "MANUFACTURED_BY",
    "supplied_by":           "SUPPLIED_BY",
    "other":                 "OTHER",
}


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


def ensure_schema() -> None:
    driver = _get_driver()
    with driver.session() as session:
        session.run(
            "CREATE CONSTRAINT entity_name IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE e.canonical_name IS UNIQUE"
        )
        session.run(
            "CREATE INDEX entity_type IF NOT EXISTS "
            "FOR (e:Entity) ON (e.type)"
        )
    log.info("Neo4j schema ensured")


def update_entity_aliases(alias_updates: dict[str, list[str]]) -> None:
    if not alias_updates:
        return
    driver = _get_driver()
    with driver.session() as session:
        for canonical_name, merged_aliases in alias_updates.items():
            session.run(
                "MATCH (e:Entity {canonical_name: $name}) "
                "SET e.aliases = $aliases, e.updated_at = datetime()",
                name=canonical_name,
                aliases=merged_aliases,
            )


def write_graph_results(
    transcript_id: str,
    new_entities: list[CanonicalizedEntity],
    relationships: list[ExtractedRelationship],
) -> None:
    driver = _get_driver()
    with driver.session() as session:
        for entity in new_entities:
            aliases = list(set(entity.aliases))
            session.run(
                """
                MERGE (e:Entity {canonical_name: $canonical_name})
                ON CREATE SET
                  e.type        = $type,
                  e.aliases     = $aliases,
                  e.part_number = $part_number,
                  e.created_at  = datetime(),
                  e.updated_at  = datetime()
                ON MATCH SET
                  e.updated_at = datetime(),
                  e.aliases    = $aliases
                """,
                canonical_name=entity.canonical_name,
                type=entity.entity_type.value,
                aliases=aliases,
                part_number=entity.part_number,
            )
            if entity.brand:
                session.run(
                    """
                    MERGE (b:Entity {canonical_name: $brand_name})
                    ON CREATE SET
                      b.type       = 'brand',
                      b.aliases    = [],
                      b.created_at = datetime(),
                      b.updated_at = datetime()
                    ON MATCH SET b.updated_at = datetime()
                    WITH b
                    MATCH (e:Entity {canonical_name: $entity_name})
                    MERGE (e)-[r:MANUFACTURED_BY]->(b)
                    ON CREATE SET
                      r.confidence = 0.95,
                      r.source_ids = [$transcript_id],
                      r.frequency  = 1,
                      r.created_at = datetime(),
                      r.updated_at = datetime()
                    ON MATCH SET
                      r.confidence = CASE WHEN NOT $transcript_id IN r.source_ids
                                          THEN (r.confidence * r.frequency + 0.95) / (r.frequency + 1)
                                          ELSE r.confidence END,
                      r.frequency  = CASE WHEN NOT $transcript_id IN r.source_ids THEN r.frequency + 1 ELSE r.frequency END,
                      r.source_ids = CASE WHEN NOT $transcript_id IN r.source_ids THEN r.source_ids + [$transcript_id] ELSE r.source_ids END,
                      r.updated_at = datetime()
                    """,
                    brand_name=entity.brand,
                    entity_name=entity.canonical_name,
                    transcript_id=transcript_id,
                )

        for rel in relationships:
            rel_type_str = _REL_TYPE_MAP[rel.predicate.value]
            _upsert_edge(session, rel, rel_type_str, transcript_id)
            if rel.predicate in _SYMMETRIC_PREDICATES:
                reversed_rel = rel.model_copy(update={
                    "subject_canonical": rel.object_canonical,
                    "object_canonical": rel.subject_canonical,
                })
                _upsert_edge(session, reversed_rel, rel_type_str, transcript_id)


def _upsert_edge(session, rel: ExtractedRelationship, rel_type_str: str, transcript_id: str) -> None:
    cypher = f"""
    MATCH (a:Entity {{canonical_name: $subject}})
    MATCH (b:Entity {{canonical_name: $object}})
    MERGE (a)-[r:{rel_type_str}]->(b)
    ON CREATE SET
      r.confidence            = $confidence,
      r.source_ids            = [$transcript_id],
      r.evidence              = $evidence,
      r.frequency             = 1,
      r.predicate_description = $predicate_description,
      r.created_at            = datetime(),
      r.updated_at            = datetime()
    ON MATCH SET
      r.confidence  = CASE WHEN NOT $transcript_id IN r.source_ids
                           THEN (r.confidence * r.frequency + $confidence) / (r.frequency + 1)
                           ELSE r.confidence END,
      r.frequency   = CASE WHEN NOT $transcript_id IN r.source_ids THEN r.frequency + 1 ELSE r.frequency END,
      r.source_ids  = CASE WHEN NOT $transcript_id IN r.source_ids THEN r.source_ids + [$transcript_id] ELSE r.source_ids END,
      r.evidence    = $evidence,
      r.updated_at  = datetime()
    """
    session.run(
        cypher,
        subject=rel.subject_canonical,
        object=rel.object_canonical,
        confidence=rel.confidence,
        transcript_id=transcript_id,
        evidence=rel.evidence_quote,
        predicate_description=rel.predicate_description,
    )
