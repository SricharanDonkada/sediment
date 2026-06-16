# Sediment — Knowledge Extraction & Graph Design Spec

## Context

Sediment extracts domain knowledge from B2B hardware/parts distributor call recordings and
surfaces it as real-time coaching during live sales calls. This document covers the knowledge
extraction pipeline and graph storage design. It is the authoritative spec for implementing
the `extraction` service and the Neo4j graph layer.

---

## Storage Architecture

Two complementary layers. Neither replaces the other — they answer different query types.

| Layer | Technology | Stores | Query type |
|---|---|---|---|
| Graph | Neo4j | Entities + relationships | Precise: "what replaces part X?" |
| Vector | PostgreSQL + pgvector | Chunk embeddings + transcript metadata | Fuzzy: "what do I ask when a customer mentions refrigerant?" |

At query time the knowledge API fans out to both layers and merges results before responding
to the client. The graph layer is **Interpretation A** — it holds only entities and
relationships, not transcript chunks. Chunks and embeddings stay in PostgreSQL.

---

## Neo4j Graph Model

### Node types

Every node is an `Entity` with a `type` property. Neo4j label is always `Entity`.
Do not use separate Neo4j labels per type — keep querying uniform.

| Type | Description | Examples |
|---|---|---|
| `component` | A physical part or device | Taco 007 Circulator, Honeywell T6 thermostat |
| `system` | An assembly or system | Air handler, RTU, split system |
| `condition` | A physical or operational state | High static pressure, low refrigerant |
| `symptom` | An observable problem | Constant drip during operation, rust at unit bottom |
| `procedure` | A maintenance or installation action | Brush-clean condensate drain, leak test |
| `brand` | A manufacturer or brand | Taco, Honeywell, Carrier, Watts |
| `supplier` | A distributor or supplier | Ferguson Enterprises, Johnstone Supply |

`brand` and `supplier` are **not** properties on component/system nodes — they are
separate Entity nodes connected by edges. See the insertion logic section for how
`brand` convenience fields on extracted entities are unpacked into nodes and edges.

### Node properties

```
Entity {
  canonical_name: string   // primary identifier, unique
  type:           string   // one of the types above
  aliases:        string[] // all known name variations seen in transcripts
  part_number:    string?  // for component/system entities only
  created_at:     datetime
  updated_at:     datetime
}
```

### Edge types

All edges are directed. Symmetric relationships (e.g. `compatible_with`) are stored as
two directed edges.

| Edge type | Direction | Description |
|---|---|---|
| `compatible_with` | A → B and B → A | Parts are confirmed to work together |
| `incompatible_with` | A → B and B → A | Parts are confirmed to fail together; high value |
| `replaces` | A → B | A can substitute for B in the field |
| `supersedes` | A → B | A is the official manufacturer replacement for B |
| `requires` | A → B | A needs B to function; installation dependency |
| `part_of` | A → B | A is a component of system/assembly B |
| `commonly_ordered_with` | A → B and B → A | Statistical co-occurrence across calls; emerges from data, not explicit statements |
| `symptom_indicates` | A → B | Symptom A points to diagnosis/condition B |
| `fixes` | A → B | Part or procedure A resolves symptom B |
| `manufactured_by` | A → B | Component/system A is made by brand B |
| `supplied_by` | A → B | Component/system A is distributed by supplier B |
| `other` | A → B | Unknown relationship type; see discovery section |

### Edge properties

Every edge carries these properties regardless of type:

```
{
  confidence:   float      // 0.0–1.0, LLM-assigned per extraction
  source_ids:   string[]   // transcript IDs that support this edge (provenance)
  evidence:     string?    // verbatim quote from transcript that supports the edge
  frequency:    int        // how many transcripts contain this edge (incremented on merge)
  created_at:   datetime
  updated_at:   datetime
  // only populated when type == "other"
  predicate_description: string?
}
```

**Relationship reification is deferred.** For MVP, `source_ids[]` as an edge property
is sufficient. Do not model source chunks as graph nodes yet — that complexity is not
justified until Phase 2.

---

## Extraction Pipeline

Two LLM passes per transcript. Never combine into one pass — splitting reduces
hallucination by giving Pass 2 resolved entity anchors to work from.

```
transcript
    │
    ▼
[Pass 1] Entity extraction
    │   → raw entity list with mentions and types
    ▼
Entity resolution
    │   → check canonical_name + aliases against existing Neo4j nodes
    │   → merge with existing nodes or create new ones
    │   → output: resolved entity list (canonical names only)
    ▼
[Pass 2] Relationship extraction
    │   → transcript + resolved entity list as grounding
    │   → LLM picks relationships between known anchors only
    ▼
Validate entity references
    │   → both subject and object must exist in resolved entity list
    │   → log skipped relationships for review
    ▼
Write to Neo4j
```

---

## Pydantic Schemas

These are the **source of truth** for LLM output shapes. They drive both the tool
use schema (via `model_json_schema()`) and the validation layer. Import from
`shared/schemas/extraction.py`.

```python
from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class DomainEntityType(str, Enum):
    component = "component"
    system    = "system"
    condition = "condition"
    symptom   = "symptom"
    procedure = "procedure"
    brand     = "brand"
    supplier  = "supplier"


class RelationshipType(str, Enum):
    compatible_with      = "compatible_with"
    incompatible_with    = "incompatible_with"
    replaces             = "replaces"
    supersedes           = "supersedes"
    requires             = "requires"
    part_of              = "part_of"
    commonly_ordered_with = "commonly_ordered_with"
    symptom_indicates    = "symptom_indicates"
    fixes                = "fixes"
    manufactured_by      = "manufactured_by"
    supplied_by          = "supplied_by"
    other                = "other"


# ── Pass 1 output ────────────────────────────────────────────────────────────

class ExtractedEntity(BaseModel):
    mention:        str            # raw string as it appeared in transcript
    canonical_name: str            # normalized, de-duplicated name
    entity_type:    DomainEntityType
    aliases:        list[str] = Field(default_factory=list)
    # Convenience fields — component/system only. Populated by the LLM when
    # the brand or part number is evident from context. The insertion layer
    # unpacks these into separate Brand/Supplier nodes and edges so the LLM
    # does not need to extract them as standalone entities.
    brand:          str | None = None
    part_number:    str | None = None

class EntityExtractionOutput(BaseModel):
    entities: list[ExtractedEntity]


# ── Pass 2 output ────────────────────────────────────────────────────────────

class ExtractedRelationship(BaseModel):
    subject_canonical: str              # must match a canonical_name from Pass 1
    predicate:         RelationshipType
    object_canonical:  str              # must match a canonical_name from Pass 1
    confidence:        float = Field(ge=0.0, le=1.0)
    evidence_quote:    str | None = None  # verbatim line from transcript
    # Only required when predicate == "other"
    predicate_description: str | None = None

class RelationshipExtractionOutput(BaseModel):
    relationships: list[ExtractedRelationship]
```

---

## Entity Resolution

Entity resolution runs between Pass 1 and Pass 2. It is a first-class concern —
not bolted on later. Graph fragmentation from unresolved aliases silently corrupts
the knowledge base.

### Algorithm

For each entity extracted in Pass 1:

1. Check `canonical_name` against existing Neo4j nodes (exact match).
2. If no exact match, check against all `aliases[]` arrays of existing nodes.
3. If still no match, run embedding similarity against existing `canonical_name` values.
   Threshold: cosine similarity ≥ 0.92 (tune after seeing real data).
4. If a match is found above threshold, add the new `mention` to the existing node's
   `aliases[]` array and return the existing `canonical_name`.
5. If no match, create a new node with `canonical_name` and `aliases = [mention]`.

### Why this matters

A veteran on a call may say "the Taco 007", "the circulator", "part 1400-50RP",
and "007" all referring to the same part. Without resolution, these become four
disconnected nodes and all edges between them are lost.

### Two-pass LLM resolution option

For high-value transcripts or when the embedding threshold is uncertain, run an
additional LLM step between Pass 1 and Neo4j lookup:

- Input: raw entity mention list from Pass 1 + existing canonical entity list from Neo4j
- Task: "Which of these mentions refer to the same entity? Group them."
- Output: resolved mention → canonical_name mapping

This is optional for MVP but improves accuracy significantly on domain-specific
naming conventions (part numbers, brand abbreviations, regional slang).

---

## LLM Interface

The extraction service must support OpenAI, Anthropic, and Ollama without code
changes — only config. Design as an injected dependency.

### Primary approach: tool use / structured output

Tool use constrains the LLM to produce output matching the schema. Use
`model_json_schema()` on the Pydantic model to generate the tool schema
automatically — do not maintain the schema in two places.

```python
import anthropic
from shared.schemas.extraction import EntityExtractionOutput

client = anthropic.Anthropic()

def run_pass1(transcript: str) -> EntityExtractionOutput:
    tools = [{
        "name": "extract_entities",
        "description": "Extract all named entities from the transcript.",
        "input_schema": EntityExtractionOutput.model_json_schema()
    }]
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        tools=tools,
        tool_choice={"type": "tool", "name": "extract_entities"},
        messages=[{"role": "user", "content": build_pass1_prompt(transcript)}]
    )
    tool_block = next(b for b in response.content if b.type == "tool_use")
    return EntityExtractionOutput(**tool_block.input)  # Pydantic validates
```

Apply the same pattern for Pass 2 with `RelationshipExtractionOutput`.

### Fallback: JSON prompting (Ollama and models without tool use)

```python
import re, json

def parse_llm_json(text: str) -> dict:
    # Strip markdown fences the model may add
    text = re.sub(r"```(?:json)?\s*", "", text).strip().strip("`")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not extract JSON from output: {text[:300]}")

def run_pass1_json_fallback(transcript: str, schema_cls) -> dict:
    schema_str = json.dumps(schema_cls.model_json_schema(), indent=2)
    prompt = (
        f"{build_pass1_prompt(transcript)}\n\n"
        f"Respond ONLY with valid JSON matching this schema. "
        f"No preamble, no markdown fences, no explanation.\n\n"
        f"Schema:\n{schema_str}"
    )
    raw_text = ollama_chat(prompt)
    return parse_llm_json(raw_text)
```

### Retry on validation failure

Pydantic validation failures are recoverable. Feed the error back to the model.

```python
from pydantic import ValidationError

def extract_with_retry(prompt_fn, schema_cls, max_retries: int = 2):
    prompt = prompt_fn()
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            raw = call_llm(prompt)                 # tool use or JSON fallback
            return schema_cls(**raw)
        except (ValidationError, ValueError) as e:
            last_error = e
            if attempt < max_retries:
                prompt += (
                    f"\n\nYour previous response failed validation with this error:\n{e}"
                    f"\n\nPlease correct and try again."
                )
    raise last_error
```

---

## Pass 1 Prompt Design

Key requirements for the system prompt:

- Instruct the model to output one entity per unique real-world thing, not per mention.
- Instruct it to normalize `canonical_name` to the most specific, unambiguous form
  (prefer "Taco 007 Circulator" over "007" or "the pump").
- Instruct it to populate `brand` on component/system entities when evident from
  context — do **not** extract the brand as a standalone entity in the same pass
  if it only appears as part of a product name.
- Instruct it to use `brand` as a standalone entity only when the brand is discussed
  independently of any specific product.
- Include an example of a well-formed output.

---

## Pass 2 Prompt Design

Key requirements:

- Provide the **resolved entity list** (canonical names only) from Pass 1 as grounding.
  The model must only use names from this list for `subject_canonical` and
  `object_canonical`. This eliminates hallucinated entity names in relationships.
- Instruct the model to choose `predicate: "other"` and fill in
  `predicate_description` when no existing edge type fits. Do not force a close
  approximation — unknown relationship types discovered this way are used to extend
  the schema after reviewing real data.
- Instruct the model to assign `confidence` honestly: a veteran explicitly stating a
  fact is 0.9+; something inferred from context is 0.6–0.8; speculation is below 0.5.
- Include the list of valid predicate values in the prompt.

---

## Validate Entity References (between Pass 2 and insertion)

Both `subject_canonical` and `object_canonical` must exist in the resolved entity set
from Pass 1. The LLM occasionally drifts from the provided list.

```python
def validate_relationships(
    output: RelationshipExtractionOutput,
    known_canonical_names: set[str]
) -> tuple[list[ExtractedRelationship], list[ExtractedRelationship]]:
    valid, skipped = [], []
    for rel in output.relationships:
        if (rel.subject_canonical in known_canonical_names
                and rel.object_canonical in known_canonical_names):
            valid.append(rel)
        else:
            skipped.append(rel)  # log for review; may indicate resolution miss
    return valid, skipped
```

Log skipped relationships with the full relationship object and the transcript ID.
They are useful for diagnosing entity resolution threshold issues.

---

## Graph Insertion Logic

### Entity insertion

```python
def insert_entity(tx, entity: ExtractedEntity) -> None:
    # Upsert the main entity node
    tx.run("""
        MERGE (e:Entity {canonical_name: $canonical_name})
        SET e.type        = $type,
            e.part_number = $part_number,
            e.updated_at  = datetime()
        ON CREATE SET e.created_at = datetime(),
                      e.aliases   = $aliases,
                      e.frequency = 1
        ON MATCH  SET e.aliases   = [x IN e.aliases + $aliases WHERE x IS NOT NULL] | DISTINCT,
                      e.frequency = e.frequency + 1
    """,
        canonical_name=entity.canonical_name,
        type=entity.entity_type.value,
        part_number=entity.part_number,
        aliases=entity.aliases,
    )

    # If the entity has a brand, create the Brand node and edge automatically.
    # This unpacks the convenience field into proper graph structure.
    if entity.brand:
        tx.run("""
            MERGE (b:Entity {canonical_name: $brand})
            ON CREATE SET b.type       = 'brand',
                          b.aliases    = [],
                          b.created_at = datetime()
            WITH b
            MATCH (e:Entity {canonical_name: $canonical_name})
            MERGE (e)-[r:MANUFACTURED_BY]->(b)
            ON CREATE SET r.confidence  = 0.95,
                          r.source_ids  = [$source_id],
                          r.frequency   = 1,
                          r.created_at  = datetime()
            ON MATCH  SET r.source_ids  = r.source_ids + [$source_id],
                          r.frequency   = r.frequency + 1,
                          r.updated_at  = datetime()
        """,
            brand=entity.brand,
            canonical_name=entity.canonical_name,
            source_id=current_transcript_id,
        )
```

### Relationship insertion

```python
def insert_relationship(tx, rel: ExtractedRelationship, transcript_id: str) -> None:
    query = f"""
        MATCH (a:Entity {{canonical_name: $subject}})
        MATCH (b:Entity {{canonical_name: $object}})
        MERGE (a)-[r:{rel.predicate.value.upper()}]->(b)
        ON CREATE SET r.confidence            = $confidence,
                      r.source_ids            = [$transcript_id],
                      r.evidence              = $evidence,
                      r.predicate_description = $predicate_description,
                      r.frequency             = 1,
                      r.created_at            = datetime()
        ON MATCH  SET r.confidence            = (r.confidence * r.frequency + $confidence)
                                                / (r.frequency + 1),
                      r.source_ids            = r.source_ids + [$transcript_id],
                      r.frequency             = r.frequency + 1,
                      r.updated_at            = datetime()
    """
    tx.run(query,
        subject=rel.subject_canonical,
        object=rel.object_canonical,
        confidence=rel.confidence,
        transcript_id=transcript_id,
        evidence=rel.evidence_quote,
        predicate_description=rel.predicate_description,
    )
```

Note: confidence is updated as a running average weighted by frequency. An edge seen
in 50 transcripts with consistent confidence is much more reliable than one seen once.

### Symmetric edges

`compatible_with`, `incompatible_with`, and `commonly_ordered_with` are symmetric.
Insert both directions:

```python
def insert_symmetric_relationship(tx, rel: ExtractedRelationship, transcript_id: str) -> None:
    insert_relationship(tx, rel, transcript_id)
    flipped = rel.model_copy(update={
        "subject_canonical": rel.object_canonical,
        "object_canonical":  rel.subject_canonical,
    })
    insert_relationship(tx, flipped, transcript_id)

SYMMETRIC_EDGES = {
    RelationshipType.compatible_with,
    RelationshipType.incompatible_with,
    RelationshipType.commonly_ordered_with,
}
```

---

## Domain Rules — Separate Store

Some knowledge extracted from transcripts is numerical or procedural and does not
map cleanly to entity-entity edges. Examples from a single HVAC transcript:

- Trap depth for commercial units >5 tons: minimum 4 inches, recommended 6 inches
- Static threshold: 0.5 inches of static can empty a shallow trap
- Trap physics: vertical depth determines effectiveness, not width
- Diagnostic pattern: unit drains when off but drips during operation → inadequate trap

Store these in a PostgreSQL `knowledge_rules` table, not in Neo4j:

```sql
CREATE TABLE knowledge_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_text       TEXT NOT NULL,
    domain          TEXT,              -- e.g. "condensate drainage", "trap sizing"
    source_ids      TEXT[] NOT NULL,   -- transcript IDs
    confidence      FLOAT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

Extract these in a third optional LLM pass or as part of Pass 2 with a separate
output field. At query time, domain rules are retrieved via keyword/semantic search
alongside graph results.

---

## The "Other" Predicate — Schema Discovery

The extraction prompt deliberately includes `other` as a valid predicate with a
required `predicate_description`. Unknown relationship types discovered in real data
should not be forced into the closest existing type.

After processing each batch of transcripts, review all edges where
`predicate = "other"` and group by `predicate_description`. Patterns that appear
in ≥ 3 transcripts are candidates for a new first-class edge type. Promote them
by updating the `RelationshipType` enum and backfilling existing `other` edges.

This is how the schema stays grounded in real domain knowledge rather than
premature taxonomy.

---

## Technology Notes

- **Neo4j version**: Community Edition (self-hosted). No clustering or RBAC needed
  for single-tenant on-prem deployment.
- **Python driver**: `neo4j` (official driver). Do not use an OGM like neomodel —
  raw Cypher gives full control and is more transparent for contributors.
- **MemgraphDB**: Noted as a Cypher-compatible alternative worth benchmarking for
  Phase 2 real-time latency. Cypher compatibility means minimal query changes if
  switching. Defer evaluation until Phase 2.
- **LLM provider**: Injected via config. Extraction service must support Anthropic,
  OpenAI, and Ollama without code changes. See LLM interface section above.
- **Model for extraction**: `claude-sonnet-4-6` (Anthropic). Configurable.

---

## What Is Out of Scope Here

- Chunk embeddings and pgvector schema → handled by the `transcription` service
- Transcript ingestion and storage → handled by the `ingestion` service
- Real-time retrieval (Phase 2) → handled by the `realtime` service
- Query fan-out logic (merging graph + vector results) → handled by `knowledge-api`
- Relationship reification (edges pointing to chunk nodes) → deferred post-MVP