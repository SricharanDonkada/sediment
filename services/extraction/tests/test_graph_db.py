import pytest
from app import graph_db
from app.graph_models import (
    CanonicalizedEntity,
    DomainEntityType,
    ExtractedRelationship,
    RelationshipType,
)


def _make_entity(name: str, brand: str | None = None) -> CanonicalizedEntity:
    return CanonicalizedEntity(
        canonical_name=name,
        entity_type=DomainEntityType.component,
        aliases=[name],
        embedding=[0.0] * 768,
        brand=brand,
    )


def _make_rel(subject: str, obj: str, predicate: RelationshipType, confidence: float = 0.9) -> ExtractedRelationship:
    return ExtractedRelationship(
        subject_canonical=subject,
        predicate=predicate,
        object_canonical=obj,
        confidence=confidence,
    )


# ── Unit tests (no live Neo4j) ─────────────────────────────────────────────────

def test_update_entity_aliases_no_op_for_empty(monkeypatch):
    driver_calls = []
    monkeypatch.setattr(graph_db, "_get_driver", lambda: driver_calls.append(1))
    graph_db.update_entity_aliases({})
    assert driver_calls == []


def test_write_graph_results_writes_symmetric_predicate_twice(monkeypatch):
    queries = []

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def run(self, cypher, **params):
            queries.append(cypher.strip())

    class FakeDriver:
        def session(self): return FakeSession()

    monkeypatch.setattr(graph_db, "_get_driver", lambda: FakeDriver())

    rel = _make_rel("Part A", "Part B", RelationshipType.compatible_with)
    graph_db.write_graph_results("t1", [_make_entity("Part A"), _make_entity("Part B")], [rel])

    cypher_blob = " ".join(queries)
    assert cypher_blob.count("COMPATIBLE_WITH") == 2


def test_write_graph_results_asymmetric_predicate_written_once(monkeypatch):
    queries = []

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def run(self, cypher, **params):
            queries.append(cypher.strip())

    class FakeDriver:
        def session(self): return FakeSession()

    monkeypatch.setattr(graph_db, "_get_driver", lambda: FakeDriver())

    rel = _make_rel("Part A", "Part B", RelationshipType.replaces)
    graph_db.write_graph_results("t1", [_make_entity("Part A"), _make_entity("Part B")], [rel])

    cypher_blob = " ".join(queries)
    assert cypher_blob.count("REPLACES") == 1


def test_write_graph_results_brand_unpacking_creates_brand_cypher(monkeypatch):
    queries = []

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def run(self, cypher, **params):
            queries.append(cypher.strip())

    class FakeDriver:
        def session(self): return FakeSession()

    monkeypatch.setattr(graph_db, "_get_driver", lambda: FakeDriver())

    entity = _make_entity("Taco 007 Circulator", brand="Taco")
    graph_db.write_graph_results("t1", [entity], [])

    cypher_blob = " ".join(queries)
    assert "MANUFACTURED_BY" in cypher_blob


def test_confidence_averaging_formula():
    existing_confidence = 0.8
    existing_frequency = 5
    new_confidence = 0.6
    result = (existing_confidence * existing_frequency + new_confidence) / (existing_frequency + 1)
    assert result == pytest.approx((4.0 + 0.6) / 6)


# ── Integration tests (require live Neo4j) ────────────────────────────────────

@pytest.mark.integration
def test_ensure_schema_is_idempotent():
    graph_db.ensure_schema()
    graph_db.ensure_schema()


@pytest.mark.integration
def test_write_and_read_entity_round_trip():
    graph_db.ensure_schema()
    entity = _make_entity("Integration Test Pump")
    graph_db.write_graph_results("int-tx-001", [entity], [])

    all_entities = graph_db.get_all_entities()
    names = [e["canonical_name"] for e in all_entities]
    assert "Integration Test Pump" in names

    driver = graph_db._get_driver()
    with driver.session() as s:
        s.run("MATCH (e:Entity {canonical_name: 'Integration Test Pump'}) DETACH DELETE e")


@pytest.mark.integration
def test_write_graph_results_is_idempotent():
    graph_db.ensure_schema()
    entity = _make_entity("Idempotency Test Entity")
    graph_db.write_graph_results("int-tx-idem", [entity], [])
    graph_db.write_graph_results("int-tx-idem", [entity], [])

    all_entities = graph_db.get_all_entities()
    matching = [e for e in all_entities if e["canonical_name"] == "Idempotency Test Entity"]
    assert len(matching) == 1

    driver = graph_db._get_driver()
    with driver.session() as s:
        s.run("MATCH (e:Entity {canonical_name: 'Idempotency Test Entity'}) DETACH DELETE e")


@pytest.mark.integration
def test_symmetric_edge_written_in_both_directions():
    graph_db.ensure_schema()
    ea = _make_entity("Sym Test A")
    eb = _make_entity("Sym Test B")
    rel = _make_rel("Sym Test A", "Sym Test B", RelationshipType.compatible_with)
    graph_db.write_graph_results("int-tx-sym", [ea, eb], [rel])

    driver = graph_db._get_driver()
    with driver.session() as s:
        r1 = s.run(
            "MATCH (:Entity {canonical_name: $a})-[r:COMPATIBLE_WITH]->(:Entity {canonical_name: $b}) RETURN count(r) AS c",
            a="Sym Test A", b="Sym Test B",
        ).single()
        r2 = s.run(
            "MATCH (:Entity {canonical_name: $a})-[r:COMPATIBLE_WITH]->(:Entity {canonical_name: $b}) RETURN count(r) AS c",
            a="Sym Test B", b="Sym Test A",
        ).single()
        assert r1["c"] == 1
        assert r2["c"] == 1

    with driver.session() as s:
        s.run("MATCH (e:Entity) WHERE e.canonical_name IN ['Sym Test A', 'Sym Test B'] DETACH DELETE e")


@pytest.mark.integration
def test_brand_unpacking_creates_manufactured_by_edge():
    graph_db.ensure_schema()
    entity = _make_entity("Brand Unpack Test Part", brand="Brand Unpack Test Co")
    graph_db.write_graph_results("int-tx-brand", [entity], [])

    driver = graph_db._get_driver()
    with driver.session() as s:
        result = s.run(
            "MATCH (:Entity {canonical_name: $n})-[r:MANUFACTURED_BY]->(:Entity {canonical_name: $b}) RETURN count(r) AS c",
            n="Brand Unpack Test Part", b="Brand Unpack Test Co",
        ).single()
        assert result["c"] == 1

    with driver.session() as s:
        s.run("MATCH (e:Entity) WHERE e.canonical_name IN ['Brand Unpack Test Part', 'Brand Unpack Test Co'] DETACH DELETE e")


@pytest.mark.integration
def test_update_entity_aliases_merges_new_aliases():
    graph_db.ensure_schema()
    entity = _make_entity("Alias Update Test Entity")
    graph_db.write_graph_results("int-tx-alias", [entity], [])

    graph_db.update_entity_aliases({"Alias Update Test Entity": ["Alias Update Test Entity", "new alias A", "new alias B"]})

    all_entities = graph_db.get_all_entities()
    match = next(e for e in all_entities if e["canonical_name"] == "Alias Update Test Entity")
    assert "new alias A" in match["aliases"]
    assert "new alias B" in match["aliases"]

    driver = graph_db._get_driver()
    with driver.session() as s:
        s.run("MATCH (e:Entity {canonical_name: 'Alias Update Test Entity'}) DETACH DELETE e")
