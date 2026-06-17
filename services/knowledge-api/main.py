from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db
from app.routes import facts, stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()
    yield
    db.close_pool()


app = FastAPI(title="Sediment Knowledge API", lifespan=lifespan)

app.include_router(stats.router)
app.include_router(facts.router)
