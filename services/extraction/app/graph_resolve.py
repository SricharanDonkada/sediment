import logging

import numpy as np

from app import db, embed
from app.graph_models import EntityCluster, MatchedEntity
from app.models import ExtractedFact

log = logging.getLogger("extraction.graph_resolve")

_COSINE_THRESHOLD = 0.92


def aggregate_mentions(facts: list[ExtractedFact]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for fact in facts:
        for mention in fact.entities:
            if mention not in index:
                index[mention] = []
            if fact.source_quote not in index[mention]:
                index[mention].append(fact.source_quote)
    return index


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=float)
    vb = np.array(b, dtype=float)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def resolve(
    mention_index: dict[str, list[str]],
    existing_entities: list[dict],
) -> tuple[list[EntityCluster], list[MatchedEntity]]:
    name_to_entity: dict[str, dict] = {e["canonical_name"]: e for e in existing_entities}
    alias_to_name: dict[str, str] = {}
    for e in existing_entities:
        for alias in e.get("aliases") or []:
            alias_to_name[alias] = e["canonical_name"]

    matched: dict[str, list[str]] = {}
    unmatched: dict[str, list[str]] = {}

    for mention, quotes in mention_index.items():
        if mention in name_to_entity:
            matched.setdefault(mention, []).append(mention)
            continue
        if mention in alias_to_name:
            matched.setdefault(alias_to_name[mention], []).append(mention)
            continue
        mention_emb = embed.embed_entity(mention)
        match = db.find_closest_entity(mention_emb, _COSINE_THRESHOLD)
        if match:
            matched.setdefault(match["canonical_name"], []).append(mention)
            continue
        unmatched[mention] = quotes

    matched_entities = []
    for canonical_name, mention_strings in matched.items():
        existing_aliases = set(name_to_entity[canonical_name].get("aliases") or [])
        new_aliases = [
            m for m in mention_strings
            if m not in existing_aliases and m != canonical_name
        ]
        matched_entities.append(MatchedEntity(canonical_name=canonical_name, new_aliases=new_aliases))

    new_clusters = _cluster_unmatched(unmatched)
    return new_clusters, matched_entities


def _cluster_unmatched(unmatched: dict[str, list[str]]) -> list[EntityCluster]:
    if not unmatched:
        return []
    mentions = list(unmatched.keys())
    if len(mentions) == 1:
        m = mentions[0]
        return [EntityCluster(mentions=[m], candidate_canonical=m, source_quotes=unmatched[m])]

    embeddings = {m: embed.embed_entity(m) for m in mentions}
    clusters: list[list[str]] = []

    for mention in mentions:
        best_cluster, best_sim = None, 0.0
        for i, members in enumerate(clusters):
            seed = max(members, key=len)
            sim = _cosine_similarity(embeddings[mention], embeddings[seed])
            if sim >= _COSINE_THRESHOLD and sim > best_sim:
                best_sim, best_cluster = sim, i
        if best_cluster is not None:
            clusters[best_cluster].append(mention)
        else:
            clusters.append([mention])

    result = []
    for members in clusters:
        candidate = max(members, key=len)
        quotes: list[str] = []
        for m in members:
            for q in unmatched[m]:
                if q not in quotes:
                    quotes.append(q)
        result.append(EntityCluster(mentions=members, candidate_canonical=candidate, source_quotes=quotes))
    return result
