from unittest.mock import MagicMock, patch


def _make_mock_conn(fetchone_return):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fetchone_return
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    return mock_conn, mock_cursor


def test_find_entity_exact_returns_entity_on_match():
    mock_conn, _ = _make_mock_conn(("TXV", ["txv", "thermal expansion valve"]))

    with patch("app.db._get_conn", return_value=mock_conn), patch("app.db._put_conn"):
        from app.db import find_entity_exact
        result = find_entity_exact("TXV")

    assert result == {"canonical_name": "TXV", "aliases": ["txv", "thermal expansion valve"]}


def test_find_entity_exact_returns_none_on_miss():
    mock_conn, _ = _make_mock_conn(None)

    with patch("app.db._get_conn", return_value=mock_conn), patch("app.db._put_conn"):
        from app.db import find_entity_exact
        result = find_entity_exact("unknown")

    assert result is None


def test_find_entity_by_alias_returns_entity_on_match():
    mock_conn, _ = _make_mock_conn(("TXV", ["txv"]))

    with patch("app.db._get_conn", return_value=mock_conn), patch("app.db._put_conn"):
        from app.db import find_entity_by_alias
        result = find_entity_by_alias("txv")

    assert result == {"canonical_name": "TXV", "aliases": ["txv"]}


def test_find_entity_by_alias_returns_none_on_miss():
    mock_conn, _ = _make_mock_conn(None)

    with patch("app.db._get_conn", return_value=mock_conn), patch("app.db._put_conn"):
        from app.db import find_entity_by_alias
        result = find_entity_by_alias("unknown")

    assert result is None


def test_find_closest_entity_returns_entity_when_above_threshold():
    mock_conn, _ = _make_mock_conn(("TXV", ["txv"], 0.95))

    with patch("app.db._get_conn", return_value=mock_conn), patch("app.db._put_conn"):
        from app.db import find_closest_entity
        result = find_closest_entity([0.1] * 768, 0.92)

    assert result == {"canonical_name": "TXV", "aliases": ["txv"]}


def test_find_closest_entity_returns_none_when_below_threshold():
    mock_conn, _ = _make_mock_conn(("TXV", ["txv"], 0.80))

    with patch("app.db._get_conn", return_value=mock_conn), patch("app.db._put_conn"):
        from app.db import find_closest_entity
        result = find_closest_entity([0.1] * 768, 0.92)

    assert result is None


def test_find_closest_entity_returns_none_on_empty_table():
    mock_conn, _ = _make_mock_conn(None)

    with patch("app.db._get_conn", return_value=mock_conn), patch("app.db._put_conn"):
        from app.db import find_closest_entity
        result = find_closest_entity([0.1] * 768, 0.92)

    assert result is None
