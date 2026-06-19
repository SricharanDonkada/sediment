from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class FactResult(BaseModel):
    id: str
    transcript_id: str | None
    fact: str | None
    category: str
    entities: list[str]
    source_quote: str | None
    interpretation_confidence: float
    created_at: datetime | None
    score: float | None = None
    source: Literal["vector", "graph"]
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None


class QueryRequest(BaseModel):
    query: str
    top_k: int = 10
    min_score: float = 0.5
    category: str | None = None
    synthesize: bool = True


class QueryResponse(BaseModel):
    facts: list[FactResult]
    synthesis: str | None
    query_used: str


class PagedFacts(BaseModel):
    facts: list[FactResult]
    total: int
    page: int
    limit: int


class StatsResponse(BaseModel):
    total_facts: int
    facts_by_category: dict[str, int]
    transcript_count: int
    avg_confidence: float
