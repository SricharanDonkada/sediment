# Sediment — Semantic Search Pipeline Design

## Overview

The pipeline takes a raw transcript and produces searchable, structured facts
stored as vector embeddings in pgvector. It runs offline, after transcription.

```
raw transcript (str)
        │
        ▼
  [LLM extraction]        Gemini — system prompt extracts structured facts
        │
        ▼
  [validation]            JSON parse → Pydantic → drop confidence < 0.5
        │
        ▼
  [build embedding text]  "[{category}] {fact}\nEntities: {entities}"
        │
        ▼
  [embed]                 Gemini text-embedding-004, task_type=RETRIEVAL_DOCUMENT
        │
        ▼
  [store]                 INSERT INTO fact_chunks ... ON CONFLICT DO NOTHING


  — at query time —

  user query (str)
        │
        ▼
  [embed query]           Gemini text-embedding-004, task_type=RETRIEVAL_QUERY
        │
        ▼
  [pgvector search]       ORDER BY embedding <=> query_vec LIMIT k
        │
        ▼
  list[SearchResult]
```

---

## Step 1 — Transcript Format

Transcripts arrive as flat text with speaker labels. No timestamps at this stage.
This is the output of WhisperX serialised to a readable string.

```
SPEAKER_A: I pretty much did a trap event set up like a bad and then
           some good options here...
SPEAKER_B: okay cool let's take a quick peek at our traps here again...
SPEAKER_C: yeah so depending on the equipment the pre-made traps are
           great and they look pretty...
```

**No chunking for the MVP.** A typical B2B call transcript is 3,000–8,000
tokens. Gemini Flash supports 1M tokens. Chunking introduces boundary
artefacts — facts that emerge from cross-speaker exchanges can be silently
split. This complexity is deferred until the Ollama / small-model path is
validated in a later phase.

---

## Step 2 — LLM Extraction

### System Prompt

```
You are a domain knowledge extractor for HVAC systems and B2B parts distribution.

Your task is to read a transcript and extract every reusable piece of
technical knowledge as a structured list of facts.


## Critical constraint: stay grounded to the transcript

Extract ONLY what the speakers actually said or clearly implied.
Do not inject general HVAC knowledge from your training — even if you
believe something is true. If it wasn't discussed in this transcript,
it does not belong in the output.


## What makes a good fact

- Self-contained: readable without the transcript.
  Bad:  "That part won't work there."
  Good: "Pre-made condensate traps are too shallow for HVAC units
         over 5 tons operating at high static pressure."

- Specific: include part numbers, model names, brands, and measurements
  exactly as they appear in the transcript.

- Clean language: write in clear technical English. You are
  reconstructing what the speaker meant, not transcribing what they said.
  Ignore filler words, false starts, and incomplete sentences.

- One claim per fact: do not bundle multiple unrelated claims into one
  statement. Split them.


## Categories

Assign exactly one category to each fact:

  compatibility            — X works with Y
  incompatibility          — X explicitly does NOT work with Y
  substitution             — X can replace Y (cross-references, OEM vs aftermarket)
  specification            — measurable property of a part or system
  sizing_rule              — how to choose the right size/depth/capacity for a given condition
  installation_procedure   — how to correctly install or configure something
  installation_requirement — what must be true for X to work correctly
  maintenance_procedure    — how to service, clean, or inspect equipment
  maintenance_interval     — how often something needs attention
  diagnostic_sign          — observable symptom that points to a specific root cause
  diagnostic_procedure     — how to test or confirm a suspected problem
  failure_mode             — what commonly fails on specific equipment, when, and why
  safety_warning           — hazard, never-do, or dangerous practice
  regulatory_requirement   — code, permit, EPA, or licensing requirement
  ordering_pattern         — what customers with X commonly also need
  application_condition    — how environment or use case changes the correct approach


## Output schema

Return a JSON array only. No markdown fences, no explanation, no preamble.

[
  {
    "fact": "Clean, self-contained statement in technical English.",
    "category": "<one category from the list above>",
    "entities": ["part numbers, model names, brands, system types mentioned"],
    "source_quote": "brief verbatim fragment from the transcript this fact is drawn from",
    "interpretation_confidence": 0.95
  }
]


## interpretation_confidence

Reflects how confidently you interpreted what the speakers meant.
Not whether the fact is technically correct in the real world.

  0.9 – 1.0  Explicitly stated, clean speech, meaning is unambiguous
  0.7 – 0.9  Clearly stated but from noisy speech, or strongly implied
  0.5 – 0.7  Partially stated; reconstructed from fragmented speech
  < 0.5      Do not extract — too unclear to produce a reliable fact

If two speakers contradict each other, extract both facts and reduce
confidence on the less-supported claim.

If no extractable facts are found, return an empty array: []
```

---

## Step 3 — Validation

Applied in order after the LLM response is received:

1. **JSON parse** — if the response is not valid JSON, log and raise. Do not
   silently swallow.
2. **Schema validation** — each item is validated against the `ExtractedFact`
   schema (see below). Items that fail are logged and skipped; the rest
   continue.
3. **Confidence filter** — drop any fact where `interpretation_confidence < 0.5`.
   This threshold is applied in code, not in the prompt, so it can be tuned
   without re-running extraction.
4. **Category normalisation** — if `category` is not one of the 16 valid
   values, remap to `general` rather than hard-failing. Log the occurrence.

### ExtractedFact Schema

```
ExtractedFact
  fact                     string    required   clean factual statement
  category                 string    required   one of 16 valid categories
  entities                 string[]  default [] part numbers, brands, model names
  source_quote             string    required   verbatim fragment from transcript
  interpretation_confidence float    required   0.0 – 1.0
```

---

## Step 4 — Embedding Text Construction

Each fact is serialised into a single text snippet before embedding.
This snippet is what the vector represents — not the raw `fact` field alone.

**Format:**
```
[{category}] {fact}
Entities: {entity_1}, {entity_2}, ...
```

**Example:**
```
[diagnostic_sign] Rust at the bottom of an air handler indicates the
condensate trap is losing water under filter load.
Entities: condensate trap, air handler, filter
```

**Why this format:**
- The category prefix anchors the embedding in the right semantic neighbourhood
  even when the query doesn't use category language.
- Explicit entity names improve exact-match retrieval for part numbers and
  model names.
- The `fact` field stored in the database remains clean and unmodified.
- `embedding_text` is stored alongside the vector so re-embedding after a
  model change is straightforward.

---

## Step 5 — Embedding Model

**Model:** Gemini `text-embedding-004`
**Dimensions:** 768

The Gemini embedding API accepts a `task_type` parameter that optimises the
vector space for asymmetric retrieval. This must be set correctly:

| Context              | task_type            |
|----------------------|----------------------|
| Embedding facts for storage | `RETRIEVAL_DOCUMENT` |
| Embedding a search query    | `RETRIEVAL_QUERY`    |

The document and query vectors are optimised differently. Using the wrong
`task_type` at query time degrades recall.

---

## Step 6 — Storage Schema (pgvector)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE fact_chunks (
    id                        UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    transcript_id             TEXT    NOT NULL,
    fact                      TEXT    NOT NULL,
    category                  TEXT    NOT NULL,
    entities                  JSONB   NOT NULL DEFAULT '[]',
    source_quote              TEXT,
    interpretation_confidence FLOAT   NOT NULL,
    embedding_text            TEXT    NOT NULL,
    embedding                 vector(768),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_transcript_fact UNIQUE (transcript_id, fact)
);

-- HNSW: no training data required, better recall at low-to-mid volumes,
-- works correctly from zero rows
CREATE INDEX ON fact_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX ON fact_chunks (transcript_id);
CREATE INDEX ON fact_chunks (category);
```

**Key decisions:**

- `UNIQUE (transcript_id, fact)` makes the pipeline idempotent. Re-running
  extraction on the same transcript is safe — duplicates are silently ignored
  via `ON CONFLICT DO NOTHING`.

- `embedding_text` is stored so the exact input to the embedding model is
  auditable and re-embedding after a model swap requires no reconstruction.

- HNSW is chosen over IVFFlat because IVFFlat requires a training pass
  (`VACUUM ANALYZE`) before queries return meaningful results. HNSW works
  correctly from day one with any number of rows.

- 768 dimensions matches Gemini `text-embedding-004`. If the embedding model
  changes, the column definition and index must be rebuilt.

---

## Future Fields (not in MVP)

```
factual_confidence   float   — cross-validated against other transcripts or
                               external sources. Separate from interpretation_confidence,
                               which only reflects transcript fidelity.
source_speaker       text    — speaker label this fact was primarily drawn from.
                               Useful once speaker identification (SPEAKER_00 →
                               "Dave, senior tech") is added upstream.
```