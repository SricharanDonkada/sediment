from app import db, embed
from app.models import FactResult

_GRAPH_CATEGORIES = {"compatibility", "incompatibility", "substitution", "ordering_pattern"}


def _vector_retrieve(
    embedding: list[float],
    top_k: int,
    category: str | None,
    min_score: float,
) -> list[dict]:
    return db.search_facts(embedding, top_k, category, min_score)


def _graph_retrieve(embedding: list[float], category: str | None) -> list[dict]:
    # Phase 2: activate Neo4j here
    return []


def _merge(
    vector_results: list[dict],
    graph_results: list[dict],
    top_k: int,
    min_score: float,
) -> list[dict]:
    seen: dict[str, dict] = {}
    for row in vector_results + graph_results:
        rid = row["id"]
        row_score = row.get("score") or 0.0
        existing_score = seen[rid].get("score") or 0.0 if rid in seen else -1.0
        if row_score > existing_score:
            seen[rid] = row
    filtered = [row for row in seen.values() if (row.get("score") or 0.0) >= min_score]
    return sorted(filtered, key=lambda row: row.get("score") or 0.0, reverse=True)[:top_k]


def retrieve(
    query: str,
    top_k: int,
    min_score: float,
    category: str | None,
) -> list[FactResult]:
    embedding = embed.embed_query(query)
    vector_results = _vector_retrieve(embedding, top_k, category, min_score)
    use_graph = category is None or category in _GRAPH_CATEGORIES
    graph_results = _graph_retrieve(embedding, category) if use_graph else []
    merged = _merge(vector_results, graph_results, top_k, min_score)
    return [FactResult(**row) for row in merged]
