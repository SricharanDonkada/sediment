# Extraction Service

Consumes transcripts produced by the [transcription service](../transcription), extracts
**structured domain facts** from each one using Gemini Flash, embeds each fact with
Gemini `text-embedding-004`, and stores the results in PostgreSQL (pgvector) for
downstream semantic search.

This is a standalone **worker** (no web surface) — it blocks on a Redis queue,
processes one transcript at a time, and loops. It is the terminal stage of the current
pipeline.

## Pipeline

```
extract ──claim──▶ download transcript ──▶ extract facts ──▶ embed each fact ──▶ store
                   (MinIO `transcripts`)   (Gemini Flash)     (text-embedding-004)  (pgvector)
```

1. **Claim** a job from `extract` (`BLMOVE` onto a processing list — see [Reliability](#reliability)).
2. **Download** the speaker-labeled `.txt` transcript from the `transcripts` bucket.
3. **Extract** structured facts with Gemini `gemini-2.5-flash`, guided by a system prompt
   that produces a JSON array of `{fact, category, entities, source_quote, interpretation_confidence}`.
4. **Filter** — drop any fact where `interpretation_confidence < 0.5`.
5. **Normalise** — remap any unknown category to `"general"` and log.
6. **Embed** each fact's `embedding_text` (`"[{category}] {fact}\nEntities: ..."`) with
   Gemini `text-embedding-004`, `task_type=RETRIEVAL_DOCUMENT`, producing a 768-dim vector.
7. **Store** a batch `INSERT INTO fact_chunks ... ON CONFLICT DO NOTHING` — idempotent by `(transcript_id, fact)`.
8. **Ack** the job.

### Fact categories

Gemini assigns each fact one of 17 categories:

`compatibility` · `incompatibility` · `substitution` · `specification` · `sizing_rule` ·
`installation_procedure` · `installation_requirement` · `maintenance_procedure` ·
`maintenance_interval` · `diagnostic_sign` · `diagnostic_procedure` · `failure_mode` ·
`safety_warning` · `regulatory_requirement` · `ordering_pattern` · `application_condition` ·
`general` (fallback for unrecognised values)

### Example stored fact

```
transcript_id:             "abc-123.txt"
fact:                      "Pre-made condensate traps are too shallow for HVAC units over 5 tons."
category:                  "sizing_rule"
entities:                  ["condensate trap", "5-ton unit"]
source_quote:              "the pre-made traps are too shallow"
interpretation_confidence: 0.9
embedding_text:            "[sizing_rule] Pre-made condensate traps are too shallow for HVAC units over 5 tons.\nEntities: condensate trap, 5-ton unit"
embedding:                 [0.032, -0.014, …]   # 768 floats
```

## Modules

| File | Responsibility |
|---|---|
| [`app/config.py`](app/config.py) | `Settings` via pydantic-settings; defaults match `docker-compose.yml`. |
| [`app/models.py`](app/models.py) | `ExtractedFact` Pydantic model and `VALID_CATEGORIES` set. |
| [`app/queue.py`](app/queue.py) | Reliable Redis: `claim`, `ack`, `dead_letter`. |
| [`app/storage.py`](app/storage.py) | MinIO: download transcript text (read-only; bucket created by transcription). |
| [`app/db.py`](app/db.py) | Postgres: `ensure_schema()` on startup, `store_facts()` batch insert. |
| [`app/extract.py`](app/extract.py) | Gemini Flash: system prompt + JSON parse + filter + normalise → `list[ExtractedFact]`. |
| [`app/embed.py`](app/embed.py) | Gemini text-embedding-004: `build_embedding_text()` + `embed_document()`. |
| [`app/pipeline.py`](app/pipeline.py) | Orchestrates extract → embed → store for one transcript. |
| [`app/worker.py`](app/worker.py) | The loop: claim → process → ack / dead-letter. |

## Reliability

`claim` uses `BLMOVE` to atomically move a job from `extract` to `extract:processing`
while it is in flight, so a crash mid-job does not lose it. On success the job is `ack`ed
(removed from the processing list); on **any** exception the worker logs the failure and
moves the job to `extract:dead` for inspection.

| Redis list | Role |
|---|---|
| `extract` | Input (produced by transcription service) |
| `extract:processing` | In-flight jobs |
| `extract:dead` | Failed jobs, for inspection |

The `fact_chunks` table has a `UNIQUE(transcript_id, fact)` constraint — re-processing
the same transcript is safe, duplicates are silently ignored via `ON CONFLICT DO NOTHING`.
The schema is created on worker startup via `db.ensure_schema()`, so no migration tooling
is needed for POC.

## Configuration

Environment variables (defaults match `docker-compose.yml`):

| Variable | Default | Notes |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `EXTRACTION_QUEUE` | `extract` | |
| `MINIO_ENDPOINT` | `localhost:9000` | `minio:9000` in compose |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | `sediment` / `sediment-dev` | |
| `MINIO_SECURE` | `false` | |
| `TRANSCRIPTS_BUCKET` | `transcripts` | |
| `POSTGRES_DSN` | `postgresql://sediment:sediment@localhost:5432/sediment` | |
| `GEMINI_EXTRACTION_MODEL` | `gemini-2.5-flash` | |
| `GEMINI_EMBEDDING_MODEL` | `text-embedding-004` | |
| `GOOGLE_CLOUD_PROJECT` | _(required)_ | GCP project with Vertex AI API enabled |
| `GOOGLE_CLOUD_LOCATION` | `asia-south1` | Vertex AI region |

> **Vertex AI credentials are required.** Run `gcloud auth application-default login`
> before starting the service, and set `GOOGLE_CLOUD_PROJECT` in your `.env`.

## Running

```bash
docker compose up -d extraction
docker compose logs -f extraction
```

The worker initialises the `fact_chunks` schema on startup — no separate migration step
needed. Postgres, Redis, and MinIO must be healthy before the service starts (enforced
by the `depends_on` conditions in `docker-compose.yml`).

## Development & testing

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```bash
cd services/extraction
uv sync
uv run pytest -m "not integration"   # unit tests only (no live services needed)
```

Integration tests require live Redis and Postgres:

```bash
docker compose up -d redis postgres
uv run pytest -m integration
```

The Gemini client and MinIO client are monkeypatched in all unit tests — no API key or
live services are needed for the unit suite.
