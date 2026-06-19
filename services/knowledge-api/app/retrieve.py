import logging

from app import db, embed, entity_resolve, graph, planner
from app.models import FactResult

log = logging.getLogger("knowledge_api.retrieve")


def _vector_retrieve(
    embedding: list[float],
    top_k: int,
    category: str | None,
    min_score: float,
) -> list[FactResult]:
    rows = db.search_facts(embedding, top_k, category, min_score)
    return [FactResult(**{**row, "source": "vector"}) for row in rows]


def _merge(
    vector_results: list[FactResult],
    graph_results: list[FactResult],
    top_k: int,
    min_score: float,
) -> list[FactResult]:
    seen: dict[str, FactResult] = {}
    for row in vector_results + graph_results:
        rid = row.id
        row_score = row.score or 0.0
        existing_score = seen[rid].score or 0.0 if rid in seen else -1.0
        if row_score > existing_score:
            seen[rid] = row
    filtered = [row for row in seen.values() if (row.score or 0.0) >= min_score]
    return sorted(filtered, key=lambda row: row.score or 0.0, reverse=True)[:top_k]


def retrieve(
    query: str,
    top_k: int,
    min_score: float,
    category: str | None,
) -> list[FactResult]:
    graph_plan = planner.plan(query)

    graph_results: list[FactResult] = []
    if graph_plan.entity and graph_plan.operations:
        canonical = entity_resolve.resolve(graph_plan.entity)
        if canonical:
            graph_results = graph.execute_operations(canonical, graph_plan.operations)
        else:
            log.debug(
                "entity resolution failed for mention=%r, skipping graph ops",
                graph_plan.entity,
            )

    query_embedding = embed.embed_query(query)
    vector_results = _vector_retrieve(query_embedding, top_k, category, min_score)

    return _merge(vector_results, graph_results, top_k, min_score)
