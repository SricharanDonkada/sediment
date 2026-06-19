import pytest
from app import graph_resolve
from app.models import ExtractedFact
from app.graph_models import EntityCluster, MatchedEntity


def _make_fact(entities: list[str], source_quote: str = "some quote") -> ExtractedFact:
    return ExtractedFact(
        fact="Some fact.",
        category="specification",
        entities=entities,
        source_quote=source_quote,
        interpretation_confidence=0.9,
    )


# ── aggregate_mentions ────────────────────────────────────────────────────────

def test_aggregate_mentions_deduplicates_same_mention():
    facts = [
        _make_fact(["TXV", "filter dryer"], "txv and filter"),
        _make_fact(["TXV"], "txv again"),
    ]
    result = graph_resolve.aggregate_mentions(facts)
    assert set(result.keys()) == {"TXV", "filter dryer"}
    assert "txv and filter" in result["TXV"]
    assert "txv again" in result["TXV"]


def test_aggregate_mentions_builds_reverse_index():
    facts = [
        _make_fact(["TXV"], "txv quote one"),
        _make_fact(["TXV", "condenser"], "txv and condenser"),
    ]
    result = graph_resolve.aggregate_mentions(facts)
    assert "txv quote one" in result["TXV"]
    assert "txv and condenser" in result["TXV"]
    assert "txv and condenser" in result["condenser"]
    assert "txv quote one" not in result["condenser"]


def test_aggregate_mentions_empty_facts():
    assert graph_resolve.aggregate_mentions([]) == {}


def test_aggregate_mentions_facts_with_no_entities():
    facts = [_make_fact([])]
    assert graph_resolve.aggregate_mentions(facts) == {}


def test_aggregate_mentions_does_not_duplicate_source_quotes():
    facts = [
        _make_fact(["TXV"], "repeated quote"),
        _make_fact(["TXV"], "repeated quote"),
    ]
    result = graph_resolve.aggregate_mentions(facts)
    assert result["TXV"].count("repeated quote") == 1


# ── resolve: exact matches ────────────────────────────────────────────────────

def test_resolve_exact_canonical_name_match():
    mention_index = {"Taco 007 Circulator": ["the pump is great"]}
    existing = [{"canonical_name": "Taco 007 Circulator", "aliases": []}]
    new_clusters, matched = graph_resolve.resolve(mention_index, existing)
    assert new_clusters == []
    assert len(matched) == 1
    assert matched[0].canonical_name == "Taco 007 Circulator"


def test_resolve_exact_alias_match():
    mention_index = {"the 007": ["install the 007 pump"]}
    existing = [{"canonical_name": "Taco 007 Circulator", "aliases": ["the 007", "007 pump"]}]
    new_clusters, matched = graph_resolve.resolve(mention_index, existing)
    assert new_clusters == []
    assert len(matched) == 1
    assert matched[0].canonical_name == "Taco 007 Circulator"


def test_resolve_matched_entity_excludes_already_known_aliases():
    mention_index = {"the 007": ["quote"]}
    existing = [{"canonical_name": "Taco 007 Circulator", "aliases": ["the 007"]}]
    _, matched = graph_resolve.resolve(mention_index, existing)
    assert matched[0].new_aliases == []


def test_resolve_no_existing_entities_creates_new_cluster(monkeypatch):
    monkeypatch.setattr(graph_resolve.embed, "embed_entity", lambda name: [0.1] * 768)
    monkeypatch.setattr(
        graph_resolve.db, "find_closest_entity", lambda emb, threshold: None
    )
    mention_index = {"brand new part": ["some quote"]}
    new_clusters, matched = graph_resolve.resolve(mention_index, [])
    assert matched == []
    assert len(new_clusters) == 1
    assert "brand new part" in new_clusters[0].mentions


# ── resolve: pgvector step 3 ──────────────────────────────────────────────────

def test_resolve_step3_matches_when_find_closest_returns_entity(monkeypatch):
    monkeypatch.setattr(graph_resolve.embed, "embed_entity", lambda name: [0.9] * 768)
    monkeypatch.setattr(
        graph_resolve.db, "find_closest_entity",
        lambda emb, threshold: {"canonical_name": "Taco 007 Circulator", "aliases": []},
    )
    mention_index = {"Taco circulator": ["use the taco circulator"]}
    existing = [{"canonical_name": "Taco 007 Circulator", "aliases": []}]

    new_clusters, matched = graph_resolve.resolve(mention_index, existing)

    assert new_clusters == []
    assert len(matched) == 1
    assert matched[0].canonical_name == "Taco 007 Circulator"


def test_resolve_step3_creates_new_cluster_when_find_closest_returns_none(monkeypatch):
    monkeypatch.setattr(graph_resolve.embed, "embed_entity", lambda name: [0.1] * 768)
    monkeypatch.setattr(
        graph_resolve.db, "find_closest_entity",
        lambda emb, threshold: None,
    )
    mention_index = {"completely different": ["quote"]}
    existing = [{"canonical_name": "Taco 007 Circulator", "aliases": []}]

    new_clusters, matched = graph_resolve.resolve(mention_index, existing)

    assert len(new_clusters) == 1
    assert matched == []


# ── resolve: intra-transcript clustering ─────────────────────────────────────

def test_resolve_similar_unmatched_mentions_cluster_together(monkeypatch):
    monkeypatch.setattr(graph_resolve.embed, "embed_entity", lambda m: [1.0, 0.0])
    monkeypatch.setattr(
        graph_resolve.db, "find_closest_entity", lambda emb, threshold: None
    )
    mention_index = {
        "Taco 007": ["quote1"],
        "007 pump": ["quote2"],
        "the circulator": ["quote3"],
    }
    new_clusters, matched = graph_resolve.resolve(mention_index, [])

    assert matched == []
    assert len(new_clusters) == 1
    assert len(new_clusters[0].mentions) == 3


def test_resolve_dissimilar_unmatched_mentions_stay_separate(monkeypatch):
    embeddings = {"Part A": [1.0, 0.0], "Part B": [0.0, 1.0]}
    monkeypatch.setattr(
        graph_resolve.embed, "embed_entity", lambda m: embeddings.get(m, [0.5, 0.5])
    )
    monkeypatch.setattr(
        graph_resolve.db, "find_closest_entity", lambda emb, threshold: None
    )
    mention_index = {"Part A": ["quote a"], "Part B": ["quote b"]}
    new_clusters, matched = graph_resolve.resolve(mention_index, [])

    assert matched == []
    assert len(new_clusters) == 2


def test_resolve_cluster_candidate_canonical_is_longest_mention(monkeypatch):
    monkeypatch.setattr(graph_resolve.embed, "embed_entity", lambda m: [1.0, 0.0])
    monkeypatch.setattr(
        graph_resolve.db, "find_closest_entity", lambda emb, threshold: None
    )
    mention_index = {"TXV": ["q1"], "Thermostatic Expansion Valve": ["q2"]}
    new_clusters, _ = graph_resolve.resolve(mention_index, [])
    assert new_clusters[0].candidate_canonical == "Thermostatic Expansion Valve"


def test_resolve_cluster_source_quotes_union(monkeypatch):
    monkeypatch.setattr(graph_resolve.embed, "embed_entity", lambda m: [1.0, 0.0])
    monkeypatch.setattr(
        graph_resolve.db, "find_closest_entity", lambda emb, threshold: None
    )
    mention_index = {"TXV": ["quote one"], "the TXV": ["quote two"]}
    new_clusters, _ = graph_resolve.resolve(mention_index, [])
    assert "quote one" in new_clusters[0].source_quotes
    assert "quote two" in new_clusters[0].source_quotes
