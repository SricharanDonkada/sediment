# services/extraction/app/extract.py
import json
import logging

from google import genai
from google.genai import types

from app.config import settings
from app.models import VALID_CATEGORIES, ExtractedFact

log = logging.getLogger("extraction.extract")

_client: genai.Client | None = None

SYSTEM_PROMPT = """You are a domain knowledge extractor for HVAC systems and B2B parts distribution.

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

- Deduplicate: if the transcript revisits the same topic in different words,
  extract one canonical phrasing — the clearest and most specific. Do not emit
  two facts that express the same underlying claim.


## Categories

Assign exactly one category to each fact:

  compatibility            — X works with Y
  incompatibility          — X explicitly does NOT work with Y
  substitution             — X can replace Y (cross-references, OEM vs aftermarket)
  specification            — measurable property of a part or system
  sizing_rule              — how to choose the right size/depth/capacity for a given condition
  installation_procedure   — how to correctly install or configure something
  installation_requirement — what must be true for X to work correctly
  maintenance_procedure    — hands-on equipment tasks: cleaning coils, flushing drain lines, replacing
                             wear parts, inspecting components. Equipment-focused only — not documentation
                             standards, note-taking practices, photo workflows, or professional conduct.
  maintenance_interval     — how often something needs attention
  diagnostic_sign          — an observable symptom (visual, audible, or measured) that points to a root cause
  diagnostic_procedure     — active troubleshooting steps taken during a service call to isolate a specific fault
  failure_mode             — what commonly fails on specific equipment, when, and why
  safety_warning           — hazard, never-do, or dangerous practice
  regulatory_requirement   — code, permit, EPA, or licensing requirement
  ordering_pattern         — what customers with X commonly also need
  application_condition    — how environment or use case changes the correct approach

If a fact does not clearly fit one of the categories above, omit it entirely.
Do not extract documentation standards, workflow procedures, quoting practices,
administrative tasks, or professional conduct guidelines — even if discussed at
length in the transcript.


## Entities

List named things: product models, brand names, error codes, component names,
system types (e.g. "VRV3", "REMQ 120", "J2", "twinning kit", "VRV/VRF").

Do NOT list:
- Bare numbers or sizes ("72", "120", "2.6")
- Quantities or measurements ("two compressors", "10%", "six feet")
- Generic nouns ("compressor", "oil", "age")


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

  1.0        The source quote directly and completely states this fact with no rewording needed
  0.9        Clearly stated but required paraphrasing or collating from nearby sentences
  0.7 – 0.8  Required inferring from context or piecing together fragmented statements
  0.5 – 0.7  Partially stated; reconstructed from fragmented speech
  < 0.5      Do not extract — too unclear to produce a reliable fact

If two speakers contradict each other, extract both facts and reduce
confidence on the less-supported claim.

If no extractable facts are found, return an empty array: []"""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True)
    return _client


def run(transcript: str) -> list[ExtractedFact]:
    client = _get_client()
    response = client.models.generate_content(
        model=settings.gemini_extraction_model,
        contents=transcript,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction=SYSTEM_PROMPT,
        ),
    )

    try:
        raw: list[dict] = json.loads(response.text)
    except json.JSONDecodeError:
        log.error("LLM returned invalid JSON: %s", response.text[:500])
        raise

    facts = []
    for item in raw:
        fact = ExtractedFact.model_validate(item)
        if fact.interpretation_confidence < 0.5:
            log.debug("dropping low-confidence fact: %s", fact.fact[:80])
            continue
        if fact.category not in VALID_CATEGORIES:
            log.warning("unknown category %r → 'general'", fact.category)
            fact = fact.model_copy(update={"category": "general"})
        facts.append(fact)

    return facts
