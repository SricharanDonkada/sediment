from google import genai
from google.genai.types import EmbedContentConfig

from app.config import settings
from app.models import ExtractedFact

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def build_embedding_text(fact: ExtractedFact) -> str:
    entities = ", ".join(fact.entities) if fact.entities else "none"
    return f"[{fact.category}] {fact.fact}\nEntities: {entities}"


def embed_document(text: str) -> list[float]:
    client = _get_client()
    response = client.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=text,
        config=EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return list(response.embeddings[0].values)
