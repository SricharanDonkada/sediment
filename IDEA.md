# Sediment — Business Note

## What It Is

Sediment is an open-source, privacy-first call intelligence platform that extracts domain knowledge from audio recordings and surfaces it as real-time coaching during live sales calls. The core idea is democratizing siloed institutional knowledge within organizations where that knowledge lives entirely in the heads of experienced people and is shared orally over phone calls.

## The Problem

In B2B hardware supply companies — construction, HVAC, plumbing, electrical distributors — the most valuable knowledge is tacit and human-carried. A 25-year veteran sales rep knows which parts are compatible, what substitutes exist for backordered items, and what a customer probably needs beyond what they asked for. A junior rep on the same call knows none of this. The gap between those two outcomes isn't effort — it's accumulated domain knowledge that was never written down anywhere. When the veteran retires, that knowledge walks out the door.

## Target Market

B2B hardware and parts distributors: construction supply, HVAC distributors, plumbing and electrical supply companies, industrial parts distributors. These companies already record calls (mostly for compliance), have no Salesforce, run on aging ERPs, and are completely ignored by the Gong-tier sales intelligence market which targets tech companies with Zoom-heavy sales cycles.

## Positioning

Privacy-first, self-hosted alternative to Gong and Chorus. The incumbents are expensive SaaS products that don't serve this market. Enterprises with strict data residency requirements — and these traditional B2B companies often have them — have no good on-prem option. Sediment runs entirely within the customer's infrastructure.

## The Moat

A compounding knowledge flywheel. Every call processed makes the system smarter for the next one. The resulting knowledge base is specific to the company's catalog, suppliers, and customers — impossible for a competitor to replicate without that call history. The longer a company uses Sediment, the more differentiated their knowledge base becomes.

## Sales Wedge

**The retiring veteran.** Every one of these companies has one or two people who carry 80% of the technical product knowledge in their heads. When that person announces retirement, the owner panics. Sediment positioned as "capture everything Dave knows before he leaves in April" is an immediate, obvious sale that naturally converts into ongoing infrastructure.

## Product Phases

**Phase 1 — Offline knowledge extraction:** Ingest call recordings → transcribe → extract structured facts → build queryable knowledge base. Delivers standalone value as a knowledge management tool.

**Phase 2 — Real-time assist:** Listen to live calls and surface relevant recommendations to the rep in real time based on the knowledge base built in Phase 1.

**Phase 3 — AI agent (long-term):** Autonomous agent that handles calls directly. Deferred until Phase 2 has validation.

## MVP Plan

No access to real call recordings yet. Use HVAC School (Bryan Orr's podcast/YouTube channel) as a proxy dataset — it is highly technical, references actual part numbers, discusses compatibility and substitutions, and mirrors the kind of knowledge this product aims to capture. The MVP demonstrates the full offline pipeline and a queryable knowledge base. Real-time assist is simulated by replaying a transcript line-by-line.

## License

**AGPL v3.** Closes the SaaS loophole — any company running Sediment as a hosted service must open-source their modifications. Sets up a natural dual-licensing model later: open-source under AGPL for the community, paid commercial license for companies that want to embed it in proprietary products.

## Identity

- **Name:** Sediment — knowledge that layers and accumulates over time, and gets lost when people leave.
- **GitHub description:** "Turns past call recordings into a compounding knowledge base that coaches your reps on live calls."

# Sediment — Technical Note

## Architecture Overview

Monorepo with discrete subservices for each pipeline stage and an orchestration layer coordinating them. Single language (Python) across the entire codebase for contributor accessibility. FastAPI for all web-facing surfaces. Celery + Redis for task orchestration.

## Repository Structure

```
sediment/
├── services/
│   ├── ingestion/        # audio intake, format normalization, queue push
│   ├── transcription/    # faster-whisper + pyannote (combined, not split)
│   ├── extraction/       # LLM pass → structured facts + embeddings
│   ├── knowledge-api/    # FastAPI REST + WebSocket
│   └── realtime/         # streaming ASR + live retrieval (Phase 2)
├── orchestrator/         # Celery worker definitions and task graph
├── shared/
│   └── schemas/          # shared Pydantic models (the contract between services)
├── web/                  # React frontend
├── infra/
│   └── docker/
├── docker-compose.yml
└── Makefile              # single command local bootstrap
```

## Service Breakdown

### Ingestion
Accepts audio files (upload) and YouTube URLs (via yt-dlp for MVP). Normalizes to a consistent format and pushes a job to the Celery queue.

### Transcription
Runs faster-whisper and pyannote.audio **together as one service** using WhisperX. Diarization and transcription are combined — running them jointly produces significantly better speaker turn accuracy than piping them sequentially. Output is a diarized transcript with speaker labels and timestamps.

### Extraction
The core of the system. Takes a diarized transcript and produces two outputs:
- **Structured facts** into a typed facts table: entities (parts, products, systems), relationships (replaces, compatible_with, incompatible_with, requires, commonly_ordered_with), and confidence scores.
- **Chunk embeddings** stored in pgvector for semantic search over raw transcript content.

The prompt design and output schema here is the primary differentiator. The LLM provider is injected via config — not hardcoded — to support OpenAI, Anthropic, and local Ollama (critical for on-prem deployments).

### Knowledge API
FastAPI service exposing:
- REST endpoints for querying the knowledge base (used by web UI and CLI)
- WebSocket endpoint for real-time assist (Phase 2)

Queries hit both the structured facts table (precise lookups: "what replaces part X?") and pgvector (semantic search: "what do I ask when a customer mentions refrigerant issues?").

### Realtime (Phase 2)
Connects to a streaming ASR source, maintains a rolling transcript window per call, and triggers retrieval after each speaker turn. Pushes suggestions to the rep's UI via WebSocket.

## Technology Decisions

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python only | Single language = lower contributor friction; bottlenecks are compute-bound not language-bound |
| Web framework | FastAPI | Async by default, native Pydantic integration, auto-generated OpenAPI docs |
| Transcription | faster-whisper | 4x faster than vanilla Whisper via CTranslate2 |
| Diarization | pyannote.audio (via WhisperX) | Combined with transcription for better accuracy |
| Vector store | PostgreSQL + pgvector | Avoids a separate vector DB; structured facts and embeddings in one place |
| Orchestration | Celery + Redis | Lightweight enough for local dev; Temporal would require contributors to run a cluster |
| Package manager | uv | Monorepo workspace support; significantly faster than pip |
| Schema contract | Pydantic (shared/schemas) | Replaces proto files; single source of truth for all inter-service data shapes |

## Knowledge Store Design

Two complementary storage layers:

**Structured facts table** — typed relationships extracted by the LLM:
```
facts(id, subject_entity, relationship_type, object_entity, confidence, source_transcript_id, timestamp)
```
Handles precise queries with exact answers.

**pgvector embeddings** — chunked transcript segments with embeddings:
```
chunks(id, transcript_id, speaker, text, embedding, start_time, end_time)
```
Handles fuzzy semantic queries where the user doesn't know exactly what they're looking for.

Queries fan out to both layers and results are merged before returning to the client.

## Key Design Constraints

**LLM provider abstraction from day one.** On-prem deployability is a core value proposition. The extraction service must support local models (Ollama) without code changes — only config. Design the LLM interface as an injected dependency.

**CPU-bound tasks use multiprocessing, not async.** Whisper inference and LLM extraction are compute-bound. Celery workers run these in separate processes. Async (asyncio) is reserved for I/O-bound work like API requests and queue polling — it provides no benefit for CPU-heavy work.

**Single Makefile command for local bootstrap.** `make dev` should pull models, start all containers, seed with a sample audio file, and confirm a working query. This is the difference between a project that gets contributors and one that doesn't.

**Shared Pydantic schemas are the inter-service contract.** Every service imports from `shared/schemas`. The transcript schema, fact schema, entity types, and relationship types are defined once. No duplication.

## MVP Scope

Phase 1 pipeline only: ingestion → transcription → extraction → knowledge store → queryable API. Real-time assist is simulated in the MVP by replaying a stored transcript line-by-line with a delay and triggering retrieval after each turn. Live audio infrastructure comes in Phase 2.