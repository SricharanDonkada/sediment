from fastapi import APIRouter

from app import retrieve as retriever
from app import synthesis as synth
from app.models import QueryRequest, QueryResponse

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    facts = retriever.retrieve(req.query, req.top_k, req.min_score, req.category)
    synthesis_text = synth.synthesize(req.query, facts) if req.synthesize else None
    return QueryResponse(facts=facts, synthesis=synthesis_text, query_used=req.query)
