from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app import db
from app.routes import facts, query, stats

# Loaded at import time — a missing or unreadable template crashes startup (all endpoints).
# Ensure the Dockerfile copies services/knowledge-api/app/templates/.
_INDEX_HTML = (Path(__file__).parent / "app" / "templates" / "index.html").read_text(
    encoding="utf-8"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()
    yield
    db.close_pool()


app = FastAPI(title="Sediment Knowledge API", lifespan=lifespan)

app.include_router(stats.router)
app.include_router(facts.router)
app.include_router(query.router)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX_HTML
