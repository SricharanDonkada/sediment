from unittest.mock import MagicMock, patch

from app.models import FactResult


def _make_driver_mock(rows):
    mock_session = MagicMock()
    mock_session.run.return_value = rows
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    return mock_driver, mock_session


def test_get_compatible_returns_fact_results():
    row = {"subject": "TXV", "object": "R-410A", "confidence": 0.95, "evidence": "works together"}
    mock_driver, _ = _make_driver_mock([row])

    with patch("app.graph._driver", mock_driver):
        from app.graph import _get_compatible
        results = _get_compatible("TXV")

    assert len(results) == 1
    r = results[0]
    assert r.subject == "TXV"
    assert r.predicate == "compatible_with"
    assert r.object == "R-410A"
    assert r.source == "graph"
    assert r.fact is None
    assert r.score == 0.95
    assert r.source_quote == "works together"


def test_get_incompatible_returns_fact_results():
    row = {"subject": "single direction filter dryer", "object": "heat pump", "confidence": 0.9, "evidence": "burns out"}
    mock_driver, _ = _make_driver_mock([row])

    with patch("app.graph._driver", mock_driver):
        from app.graph import _get_incompatible
        results = _get_incompatible("single direction filter dryer")

    assert len(results) == 1
    assert results[0].predicate == "incompatible_with"
    assert results[0].source == "graph"


def test_get_substitutes_queries_inbound_edges():
    mock_driver, mock_session = _make_driver_mock([])

    with patch("app.graph._driver", mock_driver):
        from app.graph import _get_substitutes
        _get_substitutes("old-part")

    cypher = mock_session.run.call_args[0][0]
    assert "REPLACES|SUPERSEDES" in cypher
    assert "->(e:Entity" in cypher


def test_get_substitutes_returns_fact_results():
    row = {"subject": "new-part", "predicate": "REPLACES", "object": "old-part", "confidence": 0.88, "evidence": "direct replacement"}
    mock_driver, _ = _make_driver_mock([row])

    with patch("app.graph._driver", mock_driver):
        from app.graph import _get_substitutes
        results = _get_substitutes("old-part")

    assert len(results) == 1
    assert results[0].predicate == "replaces"
    assert results[0].subject == "new-part"
    assert results[0].object == "old-part"


def test_get_ordering_companions_returns_fact_results():
    row = {"subject": "filter dryer", "object": "service valve", "confidence": 0.85, "evidence": "always order together"}
    mock_driver, _ = _make_driver_mock([row])

    with patch("app.graph._driver", mock_driver):
        from app.graph import _get_ordering_companions
        results = _get_ordering_companions("filter dryer")

    assert len(results) == 1
    assert results[0].predicate == "commonly_ordered_with"


def test_get_requires_returns_fact_results():
    row = {"subject": "TXV", "object": "external equalizer line", "confidence": 0.92, "evidence": "needs line for operation"}
    mock_driver, _ = _make_driver_mock([row])

    with patch("app.graph._driver", mock_driver):
        from app.graph import _get_requires
        results = _get_requires("TXV")

    assert len(results) == 1
    assert results[0].predicate == "requires"


def test_get_symptom_indicates_returns_fact_results():
    row = {"subject": "liquid slugging", "object": "refrigerant overcharge", "confidence": 0.87, "evidence": "common cause"}
    mock_driver, _ = _make_driver_mock([row])

    with patch("app.graph._driver", mock_driver):
        from app.graph import _get_symptom_indicates
        results = _get_symptom_indicates("liquid slugging")

    assert len(results) == 1
    assert results[0].predicate == "symptom_indicates"


def test_handler_empty_result_set_returns_empty_list():
    mock_driver, _ = _make_driver_mock([])

    with patch("app.graph._driver", mock_driver):
        from app.graph import _get_compatible
        results = _get_compatible("TXV")

    assert results == []


def test_execute_operations_skips_unknown_operation():
    mock_driver, _ = _make_driver_mock([])

    with patch("app.graph._driver", mock_driver):
        from app.graph import execute_operations
        results = execute_operations("TXV", ["totally_unknown_op"])

    assert results == []


def test_execute_operations_concatenates_multiple_operation_results():
    row_a = {"subject": "TXV", "object": "R-410A", "confidence": 0.9, "evidence": None}
    row_b = {"subject": "TXV", "object": "refrigerant line", "confidence": 0.8, "evidence": None}
    mock_driver, mock_session = _make_driver_mock([])
    mock_session.run.side_effect = [[row_a], [row_b]]

    with patch("app.graph._driver", mock_driver):
        from app.graph import execute_operations
        results = execute_operations("TXV", ["get_compatible", "get_requires"])

    assert len(results) == 2


def test_all_fact_results_have_source_graph():
    row = {"subject": "A", "object": "B", "confidence": 0.9, "evidence": None}
    mock_driver, _ = _make_driver_mock([row])

    with patch("app.graph._driver", mock_driver):
        from app.graph import _get_compatible
        results = _get_compatible("A")

    assert all(r.source == "graph" for r in results)
    assert all(r.fact is None for r in results)
    assert all(r.transcript_id is None for r in results)
