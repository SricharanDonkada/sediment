from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    """TestClient with DB pool and graph driver patched out."""
    with patch("app.db.init_pool"), patch("app.db.close_pool"), \
         patch("app.graph.init"), patch("app.graph.close"):
        with TestClient(main.app) as c:
            yield c
