import logging
import pytest
from app import graph_pipeline
from app.models import ExtractedFact
from app.graph_models import (
    CanonicalizedEntityResponse,
    DomainEntityType,
    EntityCluster,
    ExtractedRelationship,
    MatchedEntity,
    RelationshipType,
)


def _make_fact(entities: list[str], source_quote: str = "some quote") -> ExtractedFact:
    return ExtractedFact(
        fact="Some fact.",
        category="specification",
        entities=entities,
        source_quote=source_quote,
        interpretation_confidence=0.9,
    )


def _make_entity_response(name: str) -> CanonicalizedEntityResponse:
    return CanonicalizedEntityResponse(
        canonical_name=name,
        entity_type=DomainEntityType.component,
        aliases=[name],
    )


def _make_cluster(name: str) -> EntityCluster:
    return EntityCluster(mentions=[name], candidate_canonical=name, source_quotes=["q"])


def test_run_short_circuits_when_no_entity_mentions(monkeypatch):
    get_all_called = []
    monkeypatch.setattr(graph_pipeline.graph_db, "get_all_entities",
                        lambda: get_all_called.append(1) or [])

    graph_pipeline.run("t1.txt", "transcript", [_make_fact([])])

    assert get_all_called == []


def test_run_matched_entities_do_not_go_through_mini_pass(monkeypatch):
    mini_pass_called = []

    monkeypatch.setattr(graph_pipeline.graph_db, "get_all_entities", lambda: [
        {"canonical_name": "Existing TXV", "aliases": [], "embedding": []}
    ])
    monkeypatch.setattr(graph_pipeline.graph_resolve, "resolve", lambda mi, ex: (
        [],
        [MatchedEntity(canonical_name="Existing TXV", new_aliases=["the TXV"])],
    ))
    monkeypatch.setattr(graph_pipeline.graph_db, "update_entity_aliases", lambda u: None)
    monkeypatch.setattr(graph_pipeline.graph_extract, "run_mini_pass",
                        lambda clusters: mini_pass_called.append(clusters) or [])
    monkeypatch.setattr(graph_pipeline.graph_extract, "run_pass2", lambda t, n: [])
    monkeypatch.setattr(graph_pipeline.graph_db, "write_graph_results", lambda *a: None)

    graph_pipeline.run("t1.txt", "transcript", [_make_fact(["TXV"])])

    assert mini_pass_called == []


def test_run_update_entity_aliases_called_only_when_new_aliases(monkeypatch):
    alias_calls = []

    monkeypatch.setattr(graph_pipeline.graph_db, "get_all_entities", lambda: [
        {"canonical_name": "TXV", "aliases": ["the TXV"], "embedding": []}
    ])
    monkeypatch.setattr(graph_pipeline.graph_resolve, "resolve", lambda mi, ex: (
        [],
        [MatchedEntity(canonical_name="TXV", new_aliases=[])],  # no new aliases
    ))
    monkeypatch.setattr(graph_pipeline.graph_db, "update_entity_aliases",
                        lambda u: alias_calls.append(u))
    monkeypatch.setattr(graph_pipeline.graph_extract, "run_mini_pass", lambda c: [])
    monkeypatch.setattr(graph_pipeline.graph_extract, "run_pass2", lambda t, n: [])
    monkeypatch.setattr(graph_pipeline.graph_db, "write_graph_results", lambda *a: None)

    graph_pipeline.run("t1.txt", "transcript", [_make_fact(["TXV"])])

    assert alias_calls == []


def test_run_pass2_receives_both_new_and_matched_canonical_names(monkeypatch):
    pass2_names = []

    monkeypatch.setattr(graph_pipeline.graph_db, "get_all_entities", lambda: [
        {"canonical_name": "Existing Entity", "aliases": [], "embedding": []}
    ])
    monkeypatch.setattr(graph_pipeline.graph_resolve, "resolve", lambda mi, ex: (
        [_make_cluster("New Entity")],
        [MatchedEntity(canonical_name="Existing Entity", new_aliases=[])],
    ))
    monkeypatch.setattr(graph_pipeline.graph_db, "update_entity_aliases", lambda u: None)
    monkeypatch.setattr(graph_pipeline.graph_extract, "run_mini_pass",
                        lambda c: [_make_entity_response("New Entity")])
    monkeypatch.setattr(graph_pipeline.embed, "embed_document", lambda t: [0.1] * 768)

    def capture_pass2(transcript, names):
        pass2_names.extend(names)
        return []

    monkeypatch.setattr(graph_pipeline.graph_extract, "run_pass2", capture_pass2)
    monkeypatch.setattr(graph_pipeline.graph_db, "write_graph_results", lambda *a: None)

    graph_pipeline.run("t1.txt", "transcript", [_make_fact(["New Entity", "Existing Entity"])])

    assert "New Entity" in pass2_names
    assert "Existing Entity" in pass2_names


def test_run_invalid_relationships_skipped_and_logged(monkeypatch, caplog):
    monkeypatch.setattr(graph_pipeline.graph_db, "get_all_entities", lambda: [])
    monkeypatch.setattr(graph_pipeline.graph_resolve, "resolve", lambda mi, ex: (
        [_make_cluster("Part A")],
        [],
    ))
    monkeypatch.setattr(graph_pipeline.graph_extract, "run_mini_pass",
                        lambda c: [_make_entity_response("Part A")])
    monkeypatch.setattr(graph_pipeline.embed, "embed_document", lambda t: [0.1] * 768)
    monkeypatch.setattr(graph_pipeline.graph_extract, "run_pass2",
                        lambda t, n: [
                            ExtractedRelationship(
                                subject_canonical="Part A",
                                predicate=RelationshipType.replaces,
                                object_canonical="Ghost Entity",
                                confidence=0.9,
                            )
                        ])

    written = {}
    monkeypatch.setattr(graph_pipeline.graph_db, "write_graph_results",
                        lambda tid, entities, rels: written.update({"rels": rels}))

    with caplog.at_level(logging.WARNING, logger="extraction.graph_pipeline"):
        graph_pipeline.run("t1.txt", "transcript", [_make_fact(["Part A"])])

    assert written["rels"] == []
    assert "skipped" in caplog.text.lower()


def test_run_valid_relationships_are_written(monkeypatch):
    monkeypatch.setattr(graph_pipeline.graph_db, "get_all_entities", lambda: [])
    monkeypatch.setattr(graph_pipeline.graph_resolve, "resolve", lambda mi, ex: (
        [_make_cluster("Part A"), _make_cluster("Part B")],
        [],
    ))
    monkeypatch.setattr(graph_pipeline.graph_extract, "run_mini_pass",
                        lambda c: [_make_entity_response("Part A"), _make_entity_response("Part B")])
    monkeypatch.setattr(graph_pipeline.embed, "embed_document", lambda t: [0.1] * 768)
    monkeypatch.setattr(graph_pipeline.graph_extract, "run_pass2",
                        lambda t, n: [
                            ExtractedRelationship(
                                subject_canonical="Part A",
                                predicate=RelationshipType.compatible_with,
                                object_canonical="Part B",
                                confidence=0.9,
                            )
                        ])

    written = {}
    monkeypatch.setattr(graph_pipeline.graph_db, "write_graph_results",
                        lambda tid, entities, rels: written.update({"rels": rels}))

    graph_pipeline.run("t1.txt", "transcript", [_make_fact(["Part A", "Part B"])])

    assert len(written["rels"]) == 1
    assert written["rels"][0].subject_canonical == "Part A"
