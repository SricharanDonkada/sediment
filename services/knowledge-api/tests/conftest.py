from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    """TestClient with DB pool patched out — routes patch their own DB calls."""
    with patch("app.db.init_pool"), patch("app.db.close_pool"):
        with TestClient(main.app) as c:
            yield c
