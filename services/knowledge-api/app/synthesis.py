import logging

from google import genai
from google.genai import types

from app.config import settings
from app.models import FactResult

log = logging.getLogger("knowledge_api.synthesis")

_client: genai.Client | None = None

_SYSTEM_PROMPT = """You are a knowledge assistant for HVAC systems and B2B parts distribution.

You are given a user query and a list of relevant facts extracted from expert call transcripts.

Rules:
- Answer using ONLY the provided facts. Do not use outside knowledge.
- Cite the fact IDs you drew from (e.g. "According to [abc-123]...").
- If the facts are insufficient to answer the query, say so directly.
- Be concise and technical."""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def synthesize(query: str, facts: list[FactResult]) -> str | None:
    if not facts:
        return None

    facts_block = "\n\n".join(
        f"[{f.id}] {f.fact}\nSource: \"{f.source_quote}\"" for f in facts
    )
    prompt = f"Query: {query}\n\nFacts:\n{facts_block}"

    client = _get_client()
    response = client.models.generate_content(
        model=settings.gemini_synthesis_model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
    )
    return response.text
