from unittest.mock import MagicMock


def test_embed_query_returns_768_floats(monkeypatch):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.embeddings = [MagicMock(values=[0.1] * 768)]
    mock_client.models.embed_content.return_value = mock_response
    monkeypatch.setattr("app.embed._client", mock_client)

    from app.embed import embed_query
    result = embed_query("how deep should condensate traps be?")

    assert len(result) == 768
    assert all(isinstance(v, float) for v in result)


def test_embed_query_uses_retrieval_query_task(monkeypatch):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.embeddings = [MagicMock(values=[0.1] * 768)]
    mock_client.models.embed_content.return_value = mock_response
    monkeypatch.setattr("app.embed._client", mock_client)

    from app.embed import embed_query
    embed_query("test")

    _, kwargs = mock_client.models.embed_content.call_args
    # Verify RETRIEVAL_QUERY task type is passed (not RETRIEVAL_DOCUMENT used by extraction)
    assert "RETRIEVAL_QUERY" in str(kwargs.get("config", ""))
