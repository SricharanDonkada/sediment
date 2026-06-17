from fastapi import APIRouter

from app import db
from app.models import StatsResponse

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
def get_stats() -> StatsResponse:
    return StatsResponse(**db.get_stats())
