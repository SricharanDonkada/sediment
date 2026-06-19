import json
import logging

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.config import settings
from app.graph_models import (
    CanonicalizedEntityResponse,
    EntityCluster,
    EntityTypingOutput,
    ExtractedRelationship,
    RelationshipExtractionOutput,
)

log = logging.getLogger("extraction.graph_extract")

_client: genai.Client | None = None
_MAX_RETRIES = 2

MINI_PASS_SYSTEM_PROMPT = """\
You are classifying entities extracted from B2B hardware and parts distributor \
call transcripts. The domain is HVAC, plumbing, electrical supply, and construction.

For each cluster you receive, you will find:
- mentions: all strings from transcripts that refer to the same real-world entity
- candidate_canonical: the current best-guess canonical name
- source_quotes: lines from transcripts where these mentions appeared

Your task for each cluster:

1. Set canonical_name to the most specific, unambiguous form of the entity name.
   Prefer the full manufacturer name and model number over abbreviations.
   "Taco 007 Circulator" is correct. "007" or "the pump" are not.

2. Assign entity_type from exactly one of:
   component  — a physical part or device
   system     — an assembly or system composed of parts
   condition  — a physical or operational state (not a device)
   symptom    — an observable problem or failure sign
   procedure  — a maintenance, installation, or diagnostic action
   brand      — a manufacturer or brand (only when discussed independently)
   supplier   — a distributor or supply house

   Use source_quotes to resolve ambiguous cases.

3. Set brand if the entity is a component or system manufactured by a specific brand
   and the brand is identifiable from the mentions or quotes. Do not guess.

4. Set part_number if a specific model number or part number is present in any
   mention. Prefer the most complete form.

5. Populate aliases with all mention strings verbatim, exactly as they appeared.

6. If two clusters clearly refer to the same real-world entity, you may merge them
   into one output entity. Include all mentions from both clusters in aliases.

Do not invent information not supported by the mentions or source quotes.
Do not classify an entity as brand or supplier unless the mentions discuss it
independently of any specific product.

## Output

Return a JSON object only. No markdown fences, no explanation, no preamble.

{
  "entities": [
    {
      "canonical_name": "Full unambiguous name",
      "entity_type": "component|system|condition|symptom|procedure|brand|supplier",
      "aliases": ["mention string 1", "mention string 2"],
      "brand": "brand name or null",
      "part_number": "model/part number or null"
    }
  ]
}"""

PASS2_SYSTEM_PROMPT = """\
You are extracting relationships from a B2B hardware and parts distributor call \
transcript. The domain is HVAC, plumbing, electrical supply, and construction.

You will receive:
- A list of resolved entity names. These are the only entities you may reference.
- The full transcript of a call, with speaker labels.

Your task:

Extract every meaningful relationship between entities in the provided list that
is supported by the transcript. For each relationship:

1. Set subject_canonical and object_canonical to names from the provided entity
   list exactly as written. Do not paraphrase, abbreviate, or invent names.

2. Set predicate to the most accurate relationship type from:
   compatible_with       — two parts confirmed to work together
   incompatible_with     — two parts confirmed to fail or not work together
   replaces              — subject can substitute for object in the field
   supersedes            — subject is the official manufacturer replacement for object
   requires              — subject requires object to function
   part_of               — subject is a component of object
   commonly_ordered_with — subject and object are frequently ordered together
   symptom_indicates     — symptom subject suggests condition or diagnosis object
   fixes                 — part or procedure subject resolves symptom object
   manufactured_by       — subject is made by brand object
   supplied_by           — subject is distributed by supplier object
   other                 — none of the above; describe below

   If no predicate fits, use "other" and populate predicate_description.

3. Set confidence:
   0.9 or above  — a speaker explicitly states the relationship as fact
   0.6 to 0.8    — the relationship is strongly implied by context
   below 0.5     — omit entirely

4. Set evidence_quote to the verbatim transcript line(s) supporting the relationship.

5. For "other", set predicate_description to a short noun phrase.

Extract only relationships supported by the transcript.

## Output

Return a JSON object only. No markdown fences, no explanation, no preamble.

{
  "relationships": [
    {
      "subject_canonical": "name from entity list",
      "predicate": "relationship type",
      "object_canonical": "name from entity list",
      "confidence": 0.0,
      "evidence_quote": "verbatim quote or null",
      "predicate_description": "short phrase or null"
    }
  ]
}"""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True)
    return _client


def _llm_call_with_retry(prompt: str, system_prompt: str, output_model, call_desc: str):
    client = _get_client()
    contents = prompt
    for attempt in range(_MAX_RETRIES + 1):
        response = client.models.generate_content(
            model=settings.gemini_extraction_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                system_instruction=system_prompt,
            ),
        )
        try:
            return output_model.model_validate(json.loads(response.text))
        except (json.JSONDecodeError, ValidationError) as exc:
            if attempt < _MAX_RETRIES:
                log.warning("%s attempt %d failed: %s", call_desc, attempt + 1, exc)
                contents = (
                    f"Your previous response caused this error: {exc}\n\n"
                    f"Original prompt:\n{prompt}\n\n"
                    "Return only valid JSON matching the required schema."
                )
            else:
                log.error("%s failed after all %d attempts", call_desc, _MAX_RETRIES + 1)
                raise


def run_mini_pass(clusters: list[EntityCluster]) -> list[CanonicalizedEntityResponse]:
    if not clusters:
        return []
    clusters_json = json.dumps([c.model_dump() for c in clusters], indent=2)
    result: EntityTypingOutput = _llm_call_with_retry(
        prompt=clusters_json,
        system_prompt=MINI_PASS_SYSTEM_PROMPT,
        output_model=EntityTypingOutput,
        call_desc="mini-pass",
    )
    return result.entities


def run_pass2(transcript: str, canonical_names: list[str]) -> list[ExtractedRelationship]:
    names_str = "\n".join(f"- {n}" for n in canonical_names)
    prompt = f"Resolved entities:\n{names_str}\n\nTranscript:\n{transcript}"
    result: RelationshipExtractionOutput = _llm_call_with_retry(
        prompt=prompt,
        system_prompt=PASS2_SYSTEM_PROMPT,
        output_model=RelationshipExtractionOutput,
        call_desc="pass2",
    )
    return [r for r in result.relationships if r.confidence >= 0.5]
