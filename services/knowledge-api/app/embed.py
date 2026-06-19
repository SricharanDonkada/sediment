from google import genai
from google.genai.types import EmbedContentConfig

from app.config import settings

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True)
    return _client


def embed_query(text: str) -> list[float]:
    client = _get_client()
    response = client.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=text,
        config=EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=768),
    )
    return list(response.embeddings[0].values)


def embed_entity(name: str) -> list[float]:
    client = _get_client()
    response = client.models.embed_content(
        model=settings.gemini_embedding_model,
        contents=name,
        config=EmbedContentConfig(task_type="SEMANTIC_SIMILARITY", output_dimensionality=768),
    )
    return list(response.embeddings[0].values)
