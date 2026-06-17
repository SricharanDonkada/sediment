import uuid

from fastapi import APIRouter, HTTPException, Query

from app import db
from app.models import FactResult, PagedFacts

router = APIRouter()


@router.get("/facts", response_model=PagedFacts)
def list_facts(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    category: str | None = Query(None),
) -> PagedFacts:
    rows, total = db.list_facts(page, limit, category)
    return PagedFacts(
        facts=[FactResult(**r) for r in rows],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/facts/{fact_id}", response_model=FactResult)
def get_fact(fact_id: uuid.UUID) -> FactResult:
    row = db.get_fact_by_id(str(fact_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    return FactResult(**row)
