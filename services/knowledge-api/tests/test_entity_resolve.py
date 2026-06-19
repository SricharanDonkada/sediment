from unittest.mock import call, patch, MagicMock


def test_resolve_returns_canonical_on_exact_match():
    with patch("app.db.find_entity_exact", return_value={"canonical_name": "TXV", "aliases": ["txv"]}) as mock_exact, \
         patch("app.db.find_entity_by_alias") as mock_alias, \
         patch("app.embed.embed_entity") as mock_embed:
        from app.entity_resolve import resolve
        result = resolve("TXV")

    assert result == "TXV"
    mock_exact.assert_called_once_with("TXV")
    mock_alias.assert_not_called()
    mock_embed.assert_not_called()


def test_resolve_falls_through_to_alias_when_exact_misses():
    with patch("app.db.find_entity_exact", return_value=None), \
         patch("app.db.find_entity_by_alias", return_value={"canonical_name": "TXV", "aliases": ["txv"]}) as mock_alias, \
         patch("app.embed.embed_entity") as mock_embed:
        from app.entity_resolve import resolve
        result = resolve("txv")

    assert result == "TXV"
    mock_alias.assert_called_once_with("txv")
    mock_embed.assert_not_called()


def test_resolve_falls_through_to_embedding_when_exact_and_alias_miss():
    with patch("app.db.find_entity_exact", return_value=None), \
         patch("app.db.find_entity_by_alias", return_value=None), \
         patch("app.embed.embed_entity", return_value=[0.1] * 768) as mock_embed, \
         patch("app.db.find_closest_entity", return_value={"canonical_name": "TXV", "aliases": []}) as mock_closest:
        from app.entity_resolve import resolve
        result = resolve("thermal expansion valve")

    assert result == "TXV"
    mock_embed.assert_called_once_with("thermal expansion valve")
    mock_closest.assert_called_once_with([0.1] * 768, 0.92)


def test_resolve_returns_none_when_all_steps_miss():
    with patch("app.db.find_entity_exact", return_value=None), \
         patch("app.db.find_entity_by_alias", return_value=None), \
         patch("app.embed.embed_entity", return_value=[0.1] * 768), \
         patch("app.db.find_closest_entity", return_value=None):
        from app.entity_resolve import resolve
        result = resolve("no such part")

    assert result is None


def test_resolve_returns_none_when_table_empty():
    with patch("app.db.find_entity_exact", return_value=None), \
         patch("app.db.find_entity_by_alias", return_value=None), \
         patch("app.embed.embed_entity", return_value=[0.1] * 768), \
         patch("app.db.find_closest_entity", return_value=None):
        from app.entity_resolve import resolve
        result = resolve("anything")

    assert result is None
