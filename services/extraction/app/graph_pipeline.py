import logging

from app import db, embed, graph_db, graph_extract, graph_resolve
from app.graph_models import CanonicalizedEntity
from app.models import ExtractedFact

log = logging.getLogger("extraction.graph_pipeline")


def run(transcript_id: str, transcript: str, facts: list[ExtractedFact]) -> None:
    mention_index = graph_resolve.aggregate_mentions(facts)
    if not mention_index:
        log.info("no entity mentions | transcript_id=%s", transcript_id)
        return

    existing = db.get_all_entities()
    new_clusters, matched_entities = graph_resolve.resolve(mention_index, existing)

    existing_by_name = {e["canonical_name"]: e for e in existing}
    alias_updates: dict[str, list[str]] = {}
    for m in matched_entities:
        existing_aliases = set(existing_by_name[m.canonical_name].get("aliases") or [])
        merged = list(existing_aliases | set(m.new_aliases))
        if len(merged) > len(existing_aliases):
            alias_updates[m.canonical_name] = merged
    if alias_updates:
        graph_db.update_entity_aliases(alias_updates)
        db.update_entity_aliases(alias_updates)

    new_entity_responses = graph_extract.run_mini_pass(new_clusters) if new_clusters else []
    new_entities: list[CanonicalizedEntity] = []
    for resp in new_entity_responses:
        entity = CanonicalizedEntity(**resp.model_dump())
        entity.embedding = embed.embed_entity(entity.canonical_name)
        new_entities.append(entity)

    existing_names = {m.canonical_name for m in matched_entities}
    new_names = {e.canonical_name for e in new_entities}
    all_canonical_names = list(existing_names | new_names)

    if not all_canonical_names:
        log.info("no entities resolved | transcript_id=%s", transcript_id)
        return

    relationships = graph_extract.run_pass2(transcript, all_canonical_names)

    valid_names = existing_names | new_names
    validated, skipped = [], []
    for rel in relationships:
        if rel.subject_canonical in valid_names and rel.object_canonical in valid_names:
            validated.append(rel)
        else:
            skipped.append(rel)
    if skipped:
        log.warning(
            "skipped %d relationships with unresolved entity refs | transcript_id=%s",
            len(skipped), transcript_id,
        )
        for rel in skipped:
            log.debug("skipped relationship: %s", rel.model_dump())

    db.write_entities(new_entities)
    graph_db.write_graph_results(transcript_id, new_entities, validated)
    log.info(
        "graph pipeline complete | new_entities=%d matched=%d relationships=%d | transcript_id=%s",
        len(new_entities), len(matched_entities), len(validated), transcript_id,
    )
