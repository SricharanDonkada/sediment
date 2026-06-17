from datetime import datetime
from pydantic import BaseModel


class FactResult(BaseModel):
    id: str
    transcript_id: str
    fact: str
    category: str
    entities: list[str]
    source_quote: str | None
    interpretation_confidence: float
    created_at: datetime
    score: float | None = None


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
