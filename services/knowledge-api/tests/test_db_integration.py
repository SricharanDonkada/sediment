import pytest
from app import db


@pytest.fixture(autouse=True)
def pool():
    db.init_pool()
    yield
    db.close_pool()


@pytest.mark.integration
def test_get_stats_returns_correct_shape():
    stats = db.get_stats()
    assert "total_facts" in stats
    assert "facts_by_category" in stats
    assert "transcript_count" in stats
    assert "avg_confidence" in stats
    assert isinstance(stats["total_facts"], int)
    assert isinstance(stats["facts_by_category"], dict)
    assert isinstance(stats["avg_confidence"], float)


@pytest.mark.integration
def test_list_facts_returns_tuple():
    rows, total = db.list_facts(page=1, limit=10, category=None)
    assert isinstance(rows, list)
    assert isinstance(total, int)
    assert total >= 0


@pytest.mark.integration
def test_get_fact_by_id_returns_none_for_unknown():
    result = db.get_fact_by_id("00000000-0000-0000-0000-000000000000")
    assert result is None


@pytest.mark.integration
def test_list_facts_category_filter():
    rows, total = db.list_facts(page=1, limit=10, category="sizing_rule")
    assert all(r["category"] == "sizing_rule" for r in rows)


@pytest.mark.integration
def test_search_facts_returns_list():
    embedding = [0.0] * 768
    results = db.search_facts(embedding, top_k=5, category=None)
    assert isinstance(results, list)
