import logging
from typing import Callable
from uuid import uuid4

from neo4j import Driver, GraphDatabase

from app.models import FactResult

log = logging.getLogger("knowledge_api.graph")

_driver: Driver | None = None


def init(uri: str, user: str, password: str) -> None:
    global _driver
    _driver = GraphDatabase.driver(uri, auth=(user, password))


def close() -> None:
    if _driver:
        _driver.close()


def _session():
    if _driver is None:
        raise RuntimeError("graph driver not initialised")
    return _driver.session()


def _edge_to_result(
    subject: str,
    predicate: str,
    obj: str,
    confidence: float,
    evidence: str | None,
) -> FactResult:
    return FactResult(
        id=str(uuid4()),
        transcript_id=None,
        fact=None,
        category=predicate,
        entities=[subject, obj],
        source_quote=evidence,
        interpretation_confidence=confidence,
        created_at=None,
        score=confidence,
        source="graph",
        subject=subject,
        predicate=predicate,
        object=obj,
    )


def _get_compatible(canonical_name: str) -> list[FactResult]:
    with _session() as s:
        result = s.run(
            """
            MATCH (a:Entity {canonical_name: $name})-[r:COMPATIBLE_WITH]->(b:Entity)
            RETURN a.canonical_name AS subject, b.canonical_name AS object,
                   r.confidence AS confidence, r.evidence AS evidence
            """,
            name=canonical_name,
        )
        return [
            _edge_to_result(row["subject"], "compatible_with", row["object"],
                            row["confidence"], row["evidence"])
            for row in result
        ]


def _get_incompatible(canonical_name: str) -> list[FactResult]:
    with _session() as s:
        result = s.run(
            """
            MATCH (a:Entity {canonical_name: $name})-[r:INCOMPATIBLE_WITH]->(b:Entity)
            RETURN a.canonical_name AS subject, b.canonical_name AS object,
                   r.confidence AS confidence, r.evidence AS evidence
            """,
            name=canonical_name,
        )
        return [
            _edge_to_result(row["subject"], "incompatible_with", row["object"],
                            row["confidence"], row["evidence"])
            for row in result
        ]


def _get_substitutes(canonical_name: str) -> list[FactResult]:
    # Inbound direction: (sub)-[:REPLACES|SUPERSEDES]->(entity) means sub can replace entity
    with _session() as s:
        result = s.run(
            """
            MATCH (sub:Entity)-[r:REPLACES|SUPERSEDES]->(e:Entity {canonical_name: $name})
            RETURN sub.canonical_name AS subject, type(r) AS predicate,
                   e.canonical_name AS object, r.confidence AS confidence, r.evidence AS evidence
            """,
            name=canonical_name,
        )
        return [
            _edge_to_result(row["subject"], row["predicate"].lower(), row["object"],
                            row["confidence"], row["evidence"])
            for row in result
        ]


def _get_ordering_companions(canonical_name: str) -> list[FactResult]:
    with _session() as s:
        result = s.run(
            """
            MATCH (a:Entity {canonical_name: $name})-[r:COMMONLY_ORDERED_WITH]->(b:Entity)
            RETURN a.canonical_name AS subject, b.canonical_name AS object,
                   r.confidence AS confidence, r.evidence AS evidence
            """,
            name=canonical_name,
        )
        return [
            _edge_to_result(row["subject"], "commonly_ordered_with", row["object"],
                            row["confidence"], row["evidence"])
            for row in result
        ]


def _get_requires(canonical_name: str) -> list[FactResult]:
    with _session() as s:
        result = s.run(
            """
            MATCH (a:Entity {canonical_name: $name})-[r:REQUIRES]->(b:Entity)
            RETURN a.canonical_name AS subject, b.canonical_name AS object,
                   r.confidence AS confidence, r.evidence AS evidence
            """,
            name=canonical_name,
        )
        return [
            _edge_to_result(row["subject"], "requires", row["object"],
                            row["confidence"], row["evidence"])
            for row in result
        ]


def _get_symptom_indicates(canonical_name: str) -> list[FactResult]:
    with _session() as s:
        result = s.run(
            """
            MATCH (a:Entity {canonical_name: $name})-[r:SYMPTOM_INDICATES]->(b:Entity)
            RETURN a.canonical_name AS subject, b.canonical_name AS object,
                   r.confidence AS confidence, r.evidence AS evidence
            """,
            name=canonical_name,
        )
        return [
            _edge_to_result(row["subject"], "symptom_indicates", row["object"],
                            row["confidence"], row["evidence"])
            for row in result
        ]


_HANDLERS: dict[str, Callable[[str], list[FactResult]]] = {
    "get_compatible":          _get_compatible,
    "get_incompatible":        _get_incompatible,
    "get_substitutes":         _get_substitutes,
    "get_ordering_companions": _get_ordering_companions,
    "get_requires":            _get_requires,
    "get_symptom_indicates":   _get_symptom_indicates,
}


def execute_operations(canonical_name: str, operations: list[str]) -> list[FactResult]:
    results = []
    for op in operations:
        handler = _HANDLERS.get(op)
        if handler:
            results.extend(handler(canonical_name))
    return results
