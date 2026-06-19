import json
import logging

from google import genai
from google.genai.types import GenerateContentConfig
from pydantic import BaseModel

from app.config import settings

log = logging.getLogger("knowledge_api.planner")

_client: genai.Client | None = None

_KNOWN_OPS = {
    "get_compatible",
    "get_incompatible",
    "get_substitutes",
    "get_ordering_companions",
    "get_requires",
    "get_symptom_indicates",
}

_SYSTEM_PROMPT = """
You analyze HVAC knowledge base queries to determine if graph database lookups
are needed. The graph stores relationships between named parts, components,
systems, brands, suppliers, symptoms, and conditions.

Available operations and when to use each:
  get_compatible          — entity is a part/system; query asks what works with it
  get_incompatible        — entity is a part/system; query asks what cannot be used with it
  get_substitutes         — entity is a part; query asks what can replace or substitute for it
  get_ordering_companions — entity is a part; query asks what is commonly ordered alongside it
  get_requires            — entity is a part/system; query asks what it needs to function
  get_symptom_indicates   — entity is a symptom or observable problem; query asks what it points to

Return JSON matching exactly this schema — no markdown, no explanation:
{
  "entity": "<entity name as it appears in the query, or null>",
  "operations": ["<operation>"]
}

Return {"entity": null, "operations": []} when:
  - The query is procedural ("how do I install...", "what are the steps to...")
  - The query is diagnostic but situational ("unit isn't cooling", "pressure is low")
  - The query is about a general concept with no specific named entity
  - There is not enough information in the query to identify a specific entity
  - No operation from the list applies

Extract only one entity — the most specific named part, component, system,
brand, supplier, or symptom in the query. Do not invent entity names.
Do not select operations that do not apply to the query intent.
"""


class GraphPlan(BaseModel):
    entity: str | None
    operations: list[str]


EMPTY_PLAN = GraphPlan(entity=None, operations=[])


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True)
    return _client


def plan(query: str) -> GraphPlan:
    try:
        client = _get_client()
        response = client.models.generate_content(
            model=settings.gemini_planner_model,
            contents=query,
            config=GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        raw = response.text.strip()
        data = json.loads(raw)
        result = GraphPlan.model_validate(data)
        result.operations = [op for op in result.operations if op in _KNOWN_OPS]
        return result
    except Exception:
        log.warning("planner failed for query=%r, returning empty plan", query)
        return EMPTY_PLAN
