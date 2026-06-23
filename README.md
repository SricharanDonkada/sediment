# Sediment

A privacy-first, self-hosted call intelligence platform for B2B hardware distributors. Sediment transcribes call recordings, extracts structured domain knowledge from them, and surfaces that knowledge as a queryable knowledge base — and eventually, as real-time coaching during live calls.

It is a self-hosted alternative to Gong and Chorus, built specifically for distributors in HVAC, plumbing, electrical, and construction supply, where institutional knowledge lives in the heads of experienced reps and is lost when they retire.

---

## The Problem

In traditional B2B distribution, the most valuable knowledge is:

- **Tacit and human-carried** — a 25-year veteran knows which parts are compatible, what substitutes exist for backordered items, and what a customer probably needs beyond what they asked for
- **Siloed and unreplicable** — when that rep retires, the knowledge walks out the door
- **Ignored by incumbent vendors** — Gong and Chorus target tech companies with Zoom-heavy sales cycles, not hardware distributors with legacy phone systems

Sediment processes call recordings into a compounding knowledge base. Every call makes it smarter. The resulting knowledge base is specific to your catalog, suppliers, and customers — impossible to replicate without that call history.

---

## Architecture

Sediment is a Python monorepo with four discrete microservices connected by Redis queues. All services write in Python 3.12.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Pipeline (Phase 1)                         │
│                                                                     │
│  Audio file /         ┌───────────┐    ┌───────────────┐           │
│  YouTube URL  ──────▶ │ Ingestion │───▶│ Transcription │           │
│                       │  :8000    │    │   (worker)    │           │
│                       └───────────┘    └───────┬───────┘           │
│                            │                   │                   │
│                         MinIO               MinIO                  │
│                         (audio)          (transcripts)             │
│                                              │                     │
│                                    ┌─────────▼──────────┐         │
│                                    │     Extraction      │         │
│                                    │     (worker)        │         │
│                                    └────────┬────────────┘         │
│                                             │                      │
│                                   ┌─────────┴──────────┐          │
│                                   │  PostgreSQL+pgvector│          │
│                                   │  Neo4j graph DB     │          │
│                                   └─────────┬──────────┘          │
│                                             │                      │
│                                    ┌────────▼──────────┐          │
│                                    │  Knowledge API     │          │
│                                    │     :8001          │          │
│                                    └───────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

### Repository layout

```
sediment/
├── services/
│   ├── ingestion/        # FastAPI: audio intake, normalize, queue push
│   ├── transcription/    # Worker: faster-whisper + pyannote diarization
│   ├── extraction/       # Worker: LLM fact extraction + embedding → pgvector + Neo4j
│   ├── knowledge-api/    # FastAPI: semantic search, graph query, synthesis
│   └── realtime/         # Phase 2: streaming ASR + live retrieval (placeholder)
├── shared/
│   └── schemas/          # Shared Pydantic models (inter-service contract)
├── infra/
│   └── docker/
├── docs/
│   └── superpowers/      # Design specs and implementation plans (gitignored)
├── docker-compose.yml
├── .env.example
└── LICENSE
```

---

## Services

### Ingestion (`services/ingestion/` — port 8000)

FastAPI service. Accepts an audio file upload (any format ffmpeg understands) or a YouTube URL, normalizes to 16 kHz mono WAV, stores in MinIO, and pushes a job to the `audio-transcribe` Redis queue.

**Pipeline:**
```
upload / YouTube URL → ffmpeg (16kHz mono WAV) → MinIO `audio` bucket → Redis `audio-transcribe`
```

**API:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ingest` | Submit a file or YouTube URL |
| `GET`  | `/` | Browser UI for manual testing |

`POST /ingest` accepts `multipart/form-data` with exactly one of:
- `file` — binary audio (mp3, m4a, ogg, wav, …)
- `youtube_url` — YouTube video URL

Returns `{"object_key": "<uuid>.wav", "bucket": "audio"}` on success.

---

### Transcription (`services/transcription/` — worker)

Standalone worker. Consumes jobs from `audio-transcribe`, transcribes with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), diarizes with [pyannote.audio](https://github.com/pyannote/pyannote-audio), merges into a speaker-labeled script, stores to MinIO, and enqueues for extraction.

**Pipeline:**
```
Redis `audio-transcribe` → download WAV (MinIO) → transcribe (faster-whisper)
                        → diarize (pyannote) → merge speakers → store .txt (MinIO `transcripts`)
                        → Redis `extract`
```

**Example transcript output:**
```
SPEAKER_A: I need a replacement for the Carrier 24ACC636A003.

SPEAKER_B: Would an aftermarket work or do you need exact match?

SPEAKER_A: Exact match preferred, open to compatible if it's cheaper.
```

Speaker labels are assigned alphabetically by first appearance. Consecutive same-speaker segments are joined. No word-level timestamps — the goal is a readable conversation script, not alignment data.

**GPU support:** Set `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE_TYPE=float16`. The Hugging Face model cache is stored in the `hf-cache` named volume so it is not re-downloaded on restart.

---

### Extraction (`services/extraction/` — worker)

Standalone worker. Consumes transcripts from `extract`, runs two LLM passes to extract structured facts and entity-relationship graphs, embeds facts, and stores results in PostgreSQL (pgvector) and Neo4j.

**Pipeline:**
```
Redis `extract` → download transcript (MinIO) → Pass 1: entity extraction (LLM)
               → entity resolution (Neo4j lookup + embedding similarity)
               → Pass 2: relationship extraction (LLM, grounded to resolved entities)
               → embed facts (Gemini text-embedding-004, RETRIEVAL_DOCUMENT)
               → store facts (PostgreSQL fact_chunks) + graph (Neo4j)
               → ack
```

**Fact categories** — the LLM assigns one of 17 categories per fact:

`compatibility` · `incompatibility` · `substitution` · `specification` · `sizing_rule` · `installation_procedure` · `installation_requirement` · `maintenance_procedure` · `maintenance_interval` · `diagnostic_sign` · `diagnostic_procedure` · `failure_mode` · `safety_warning` · `regulatory_requirement` · `ordering_pattern` · `application_condition` · `general`

**Example stored fact:**
```
fact:                      "Pre-made condensate traps are too shallow for HVAC units over 5 tons."
category:                  "sizing_rule"
entities:                  ["condensate trap", "5-ton unit"]
source_quote:              "the pre-made traps are too shallow"
interpretation_confidence: 0.9
embedding:                 [768-dim vector]
```

Facts with `interpretation_confidence < 0.5` are dropped. Pipeline is idempotent — the `fact_chunks` table has a `UNIQUE(transcript_id, fact)` constraint; re-processing a transcript is safe.

**LLM provider:** Currently Gemini (Vertex AI). The extraction service is designed to support Anthropic, OpenAI, and Ollama via config — no code changes required. The LLM interface is injected as a dependency using Pydantic tool schemas generated from `shared/schemas/extraction.py`.

---

### Knowledge API (`services/knowledge-api/` — port 8001)

FastAPI read surface. Semantic search over `fact_chunks` via pgvector, graph queries via Neo4j (Phase 2), and optional synthesis with Gemini Flash. Read-only — no Redis or MinIO dependency.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/query` | Semantic search with optional synthesis |
| `GET`  | `/facts` | Paginated fact list |
| `GET`  | `/facts/{id}` | Single fact by UUID |
| `GET`  | `/stats` | Knowledge base aggregate stats |

**`POST /query` request:**
```json
{
  "query": "How deep should condensate traps be for large units?",
  "top_k": 10,
  "min_score": 0.5,
  "category": null,
  "synthesize": true
}
```

**`POST /query` response:**
```json
{
  "facts": [
    {
      "id": "...",
      "transcript_id": "abc-123.txt",
      "fact": "Pre-made condensate traps are too shallow for HVAC units over 5 tons.",
      "category": "sizing_rule",
      "entities": ["condensate trap", "5-ton unit"],
      "source_quote": "the pre-made traps are too shallow",
      "interpretation_confidence": 0.9,
      "created_at": "2026-06-17T...",
      "score": 0.87
    }
  ],
  "synthesis": "For units over 5 tons, use a minimum 4-inch trap (6 inches recommended).",
  "query_used": "How deep should condensate traps be for large units?"
}
```

Categories `compatibility`, `incompatibility`, `substitution`, and `ordering_pattern` are routed to both vector and graph retrieval. The graph layer is a stub returning `[]` today; activation requires only changes inside `_graph_retrieve()` in `app/retrieve.py`.

---

## Storage

### Two-layer knowledge store

| Layer | Technology | Answers |
|-------|------------|---------|
| Vector | PostgreSQL + pgvector | "What do I ask when a customer mentions refrigerant?" |
| Graph | Neo4j | "What replaces part X?" / "What's compatible with Y?" |

**`fact_chunks` table (pgvector):**

Stores structured facts with 768-dimensional embeddings. HNSW index for cosine similarity search (no training pass required, works from day one). Fact embeddings use the format `[{category}] {fact}\nEntities: ...` to anchor vectors in the right semantic neighbourhood even when queries don't use category language.

**Neo4j graph:**

Entity nodes (`component`, `system`, `condition`, `symptom`, `procedure`, `brand`, `supplier`) connected by typed edges (`compatible_with`, `replaces`, `supersedes`, `requires`, `commonly_ordered_with`, `symptom_indicates`, `fixes`, `manufactured_by`, `supplied_by`, and others).

Entity resolution runs before relationship extraction: known aliases, part numbers, and embedding similarity (≥ 0.92 cosine threshold) are checked so "the Taco 007", "007", and "part 1400-50RP" resolve to the same node rather than fragmenting the graph.

### Redis queues

| Queue | Producer | Consumer |
|-------|----------|----------|
| `audio-transcribe` | ingestion | transcription |
| `audio-transcribe:processing` | transcription worker | transcription worker |
| `audio-transcribe:dead` | transcription worker (on error) | operator |
| `extract` | transcription | extraction |
| `extract:processing` | extraction worker | extraction worker |
| `extract:dead` | extraction worker (on error) | operator |

All workers use atomic move-on-claim (`BLMOVE`) so a mid-job crash does not lose the job. Failed jobs land in `:dead` queues for inspection.

### MinIO buckets

| Bucket | Written by | Read by |
|--------|------------|---------|
| `audio` | ingestion | transcription |
| `transcripts` | transcription | extraction |

---

## Prerequisites

- **Docker and Docker Compose** — to run the full stack
- **Python 3.12** — for local development
- **[uv](https://docs.astral.sh/uv/)** — package manager used by all services (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **ffmpeg** — audio normalization (must be on PATH for local dev; included in Docker images)
- **Google Cloud project with Vertex AI API enabled** — for LLM extraction and embeddings
- **Hugging Face account** — for the pyannote speaker diarization model

---

## Environment setup

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
```

### Required

**Google Cloud (Vertex AI)** — used by extraction and knowledge-api:
```bash
# Run this first (application-default credentials, NOT gcloud auth login):
gcloud auth application-default login

GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=asia-south1   # or your preferred Vertex AI region
```

On Windows, the gcloud config directory is not in the default Linux path. Add this to your `.env`:
```bash
GCLOUD_CONFIG_DIR=C:/Users/<you>/AppData/Roaming/gcloud
```

**Hugging Face token** — used by the transcription service:
```bash
HF_TOKEN=hf_...
```

1. Create a token at https://huggingface.co/settings/tokens
2. Accept the model terms at https://huggingface.co/pyannote/speaker-diarization-community-1

### Optional overrides

All other values have defaults that match `docker-compose.yml`:

```bash
# Postgres
POSTGRES_USER=sediment
POSTGRES_PASSWORD=sediment
POSTGRES_DB=sediment

# MinIO
MINIO_ROOT_USER=sediment
MINIO_ROOT_PASSWORD=sediment-dev

# Neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=sediment-dev

# Whisper (transcription service)
WHISPER_MODEL=large-v3-turbo   # smaller model = faster, less accurate
WHISPER_DEVICE=cpu             # set to 'cuda' on a GPU host
WHISPER_COMPUTE_TYPE=int8      # set to 'float16' on GPU

# Gemini models
GEMINI_EXTRACTION_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_SYNTHESIS_MODEL=gemini-2.5-flash
```

---

## Running

### Full stack (Docker Compose)

```bash
# Start everything
docker compose up -d

# Check logs
docker compose logs -f

# Stop
docker compose down
```

Services and their exposed ports:

| Service | Port | Notes |
|---------|------|-------|
| Ingestion API | `8000` | `POST /ingest`, `GET /` |
| Knowledge API | `8001` | `POST /query`, `GET /facts`, `GET /stats` |
| PostgreSQL | `5432` | pgvector extension enabled |
| Neo4j browser | `7474` | Graph visualization UI |
| Neo4j Bolt | `7687` | Driver connection |
| MinIO API | `9000` | S3-compatible object storage |
| MinIO console | `9001` | Web UI for browsing buckets |
| Redis | `6379` | Queue broker |

The extraction worker creates the `fact_chunks` schema on first startup — no separate migration step.

Healthchecks are configured for all datastores. Compose waits for dependencies to be healthy before starting dependent services.

### Quick test

After `docker compose up -d`, ingest a sample audio file:

```bash
# Upload a local file
curl -X POST http://localhost:8000/ingest \
  -F "file=@/path/to/recording.mp3"

# Or ingest a YouTube video
curl -X POST http://localhost:8000/ingest \
  -F "youtube_url=https://www.youtube.com/watch?v=..."
```

Once the pipeline completes, query the knowledge base:

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What parts are compatible with the Carrier 24ACC636A003?", "synthesize": true}'
```

---

## Local development

Each service is independently runnable. Dependencies are managed with [uv](https://docs.astral.sh/uv/) workspaces.

### Ingestion

```bash
cd services/ingestion
uv sync
uv run pytest                            # unit tests (no infra needed)
docker compose up -d redis minio         # for integration tests
uv run pytest -m integration
uvicorn app.main:app --reload            # dev server on :8000
```

### Transcription

```bash
cd services/transcription
uv sync
uv run pytest -m "not slow"             # unit + integration (mocked models)
docker compose up -d redis minio        # for integration tests
# @pytest.mark.slow runs real Whisper/pyannote inference — omit for speed
```

### Extraction

```bash
cd services/extraction
uv sync
uv run pytest -m "not integration"      # unit tests (Gemini and MinIO mocked)
docker compose up -d redis postgres minio neo4j
uv run pytest -m integration
```

### Knowledge API

```bash
cd services/knowledge-api
uv sync
uv run pytest -m "not integration"      # unit tests
docker compose up -d postgres neo4j
uv run pytest -m integration
uvicorn main:app --reload               # dev server on :8001
```

### Shared schemas

```bash
cd shared/schemas
uv sync
uv run pytest
```

---

## Tech stack

| Component | Technology | Why |
|-----------|------------|-----|
| Language | Python 3.12 | Single language across the whole codebase; performance bottlenecks are compute-bound (Whisper, LLM), not language-bound |
| Web framework | FastAPI | Async by default, native Pydantic, auto OpenAPI docs |
| Package manager | uv | Monorepo workspace support, significantly faster than pip |
| Transcription | faster-whisper | 4x faster than vanilla Whisper via CTranslate2 |
| Diarization | pyannote.audio | Speaker turn detection; custom merge avoids WhisperX's alignment-dictionary limitation on part numbers and model names |
| LLM extraction | Gemini 2.5 Flash | Cost-effective, fast; configurable — swap Anthropic, OpenAI, or local Ollama via config |
| Embeddings | Gemini text-embedding-004 | 768 dims; asymmetric task types (`RETRIEVAL_DOCUMENT` for indexing, `RETRIEVAL_QUERY` at search time) |
| Vector store | PostgreSQL + pgvector | Structured facts + embeddings in one place; HNSW index works from zero rows without training |
| Graph DB | Neo4j Community | Entity/relationship store; full Cypher query support |
| Queue | Redis lists | Lightweight; `BLMOVE` sufficient for MVP; easier for contributors than Temporal or Celery |
| Object storage | MinIO | S3-compatible; self-hosted; no cloud dependency |
| Shared types | Pydantic (`shared/schemas`) | Single source of truth for inter-service contracts; drives both validation and LLM tool schemas |

---

## Project phases

**Phase 1 — Offline knowledge extraction (current)**

Process call recordings into a queryable knowledge base. Delivers standalone value as a knowledge management and search tool before any real-time capability exists.

**Phase 2 — Real-time assist**

Listen to live calls and surface relevant facts and recommendations to the rep as the conversation happens. Based on the knowledge base built in Phase 1.

**Phase 3 — Autonomous agent (long-term)**

Agent that handles inbound calls directly. Deferred until Phase 2 is validated.
