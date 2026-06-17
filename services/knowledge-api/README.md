# Knowledge API

Read surface of Sediment. FastAPI service over `fact_chunks` — semantic search,
paginated fact browsing, and knowledge base stats. Read-only; no dependency on
Redis, MinIO, or the write pipeline.

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/query` | Semantic search with optional synthesis |
| GET | `/facts` | Paginated fact list |
| GET | `/facts/{id}` | Single fact by UUID |
| GET | `/stats` | Knowledge base aggregate stats |

## Query modes

**POST /query** embeds the query with Gemini `gemini-embedding-001`
(`RETRIEVAL_QUERY` task type — the asymmetric complement to `RETRIEVAL_DOCUMENT`
used during extraction), runs cosine similarity search, and optionally synthesizes
an answer with `gemini-2.5-flash`. Set `synthesize: false` to skip synthesis.

## Graph retrieval (Phase 2)

Categories `compatibility`, `incompatibility`, `substitution`, and
`ordering_pattern` are routed to both vector and graph retrieval layers. The graph
layer is a stub returning `[]` for now. Phase 2 activation requires changes only
inside `_graph_retrieve()` in `app/retrieve.py`.

## Modules

| File | Responsibility |
|---|---|
| `app/config.py` | pydantic-settings; defaults match `docker-compose.yml` |
| `app/models.py` | Pydantic request/response models |
| `app/db.py` | `ThreadedConnectionPool` + all SQL queries |
| `app/embed.py` | `RETRIEVAL_QUERY` embedding |
| `app/retrieve.py` | Vector search + graph stub + merger |
| `app/synthesis.py` | Gemini Flash synthesis |
| `app/routes/stats.py` | `GET /stats` |
| `app/routes/facts.py` | `GET /facts`, `GET /facts/{id}` |
| `app/routes/query.py` | `POST /query` |
| `main.py` | FastAPI app, lifespan, router registration |

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_DSN` | `postgresql://sediment:sediment@localhost:5432/sediment` | |
| `GOOGLE_CLOUD_PROJECT` | _(required)_ | GCP project with Vertex AI API enabled |
| `GOOGLE_CLOUD_LOCATION` | `asia-south1` | Vertex AI region |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Must match extraction service |
| `GEMINI_SYNTHESIS_MODEL` | `gemini-2.5-flash` | |
| `DB_POOL_MIN` | `1` | |
| `DB_POOL_MAX` | `5` | |
| `DEFAULT_TOP_K` | `10` | |
| `DEFAULT_MIN_SCORE` | `0.5` | |

## Running

```bash
docker compose up -d knowledge-api
```

Requires postgres to be healthy. No Redis or MinIO dependency.

## Development

```bash
cd services/knowledge-api
uv sync
uv run pytest -m "not integration"   # unit tests only
```

Integration tests require live postgres:

```bash
docker compose up -d postgres
uv run pytest -m integration
```
