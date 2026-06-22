import logging

from google import genai
from google.genai import types

from app.config import settings
from app.models import FactResult

log = logging.getLogger("knowledge_api.synthesis")

_client: genai.Client | None = None

_SYSTEM_PROMPT = """You are answering a question using knowledge extracted from HVAC technical
call recordings. You will receive two types of knowledge:

  (fact)  — a statement extracted directly from a call transcript
  (graph) — a structured relationship between two named entities, e.g.
             "single direction flow filter dryer incompatible with heat pump"

Rules:
- Use only the provided knowledge. Do not add information not present.
- Cite the fact ID(s) you drew from in brackets, e.g. [abc123].
- If the knowledge is insufficient to answer the question, say so explicitly.
- For graph results, use the subject/predicate/object structure directly —
  do not paraphrase in a way that changes the meaning."""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True)
    return _client


def _format_fact(f: FactResult) -> str:
    if f.source == "graph":
        base = f"{f.subject} {f.predicate.replace('_', ' ')} {f.object}"
        if f.source_quote:
            return f"[{f.id}] (graph) {base}\n  Evidence: {f.source_quote}"
        return f"[{f.id}] (graph) {base}"
    else:
        base = f.fact or ""
        if f.source_quote:
            return f"[{f.id}] (fact) {base}\n  Source: {f.source_quote}"
        return f"[{f.id}] (fact) {base}"


def synthesize(query: str, facts: list[FactResult]) -> str | None:
    if not facts:
        return None

    facts_block = "\n\n".join(_format_fact(f) for f in facts)
    prompt = f"Query: {query}\n\nFacts:\n{facts_block}"

    client = _get_client()
    response = client.models.generate_content(
        model=settings.gemini_synthesis_model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=_SYSTEM_PROMPT),
    )
    return response.text
