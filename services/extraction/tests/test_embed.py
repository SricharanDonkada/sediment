import pytest
from app import embed
from app.models import ExtractedFact


def _make_embed_client(vector: list[float]):
    """Return a fake genai.Client whose embed_content returns a fixed vector."""
    class FakeEmbedding:
        values = vector

    class FakeResponse:
        embeddings = [FakeEmbedding()]

    class FakeModels:
        def embed_content(self, model, contents, config):
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    return FakeClient()


def test_build_embedding_text_format():
    fact = ExtractedFact(
        fact="Condensate traps need 4-inch depth for units over 5 tons.",
        category="sizing_rule",
        entities=["condensate trap", "5-ton unit"],
        source_quote="the trap depth should be 4 inches",
        interpretation_confidence=0.9,
    )
    result = embed.build_embedding_text(fact)
    assert result == (
        "[sizing_rule] Condensate traps need 4-inch depth for units over 5 tons.\n"
        "Entities: condensate trap, 5-ton unit"
    )


def test_build_embedding_text_no_entities():
    fact = ExtractedFact(
        fact="Some general fact.",
        category="specification",
        entities=[],
        source_quote="speaker said this",
        interpretation_confidence=0.8,
    )
    result = embed.build_embedding_text(fact)
    assert result == "[specification] Some general fact.\nEntities: none"


def test_embed_document_returns_768_dim_vector(monkeypatch):
    vector = [0.1] * 768
    monkeypatch.setattr(embed, "_get_client", lambda: _make_embed_client(vector))

    result = embed.embed_document("some embedding text")

    assert isinstance(result, list)
    assert len(result) == 768
    assert result[0] == pytest.approx(0.1)  # type: ignore[arg-type]


def test_embed_document_passes_retrieval_document_task_type(monkeypatch):
    received = {}

    class FakeEmbedding:
        values = [0.0] * 768

    class FakeResponse:
        embeddings = [FakeEmbedding()]

    class FakeModels:
        def embed_content(self, model, contents, config):
            received["config"] = config
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(embed, "_get_client", lambda: FakeClient())
    embed.embed_document("test")

    assert received["config"].task_type == "RETRIEVAL_DOCUMENT"


def test_embed_entity_uses_semantic_similarity(monkeypatch):
    received = {}

    class FakeEmbedding:
        values = [0.2] * 768

    class FakeResponse:
        embeddings = [FakeEmbedding()]

    class FakeModels:
        def embed_content(self, model, contents, config):
            received["contents"] = contents
            received["config"] = config
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(embed, "_get_client", lambda: FakeClient())
    result = embed.embed_entity("Taco 007 Circulator")

    assert len(result) == 768
    assert result == [0.2] * 768
    assert received["config"].task_type == "SEMANTIC_SIMILARITY"
    assert received["contents"] == "Taco 007 Circulator"
