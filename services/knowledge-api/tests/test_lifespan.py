"""Tests that app startup wires the Neo4j driver with the correct settings."""
from unittest.mock import call, patch

from fastapi.testclient import TestClient

import main
from app.config import settings


def test_graph_init_called_with_settings_on_startup():
    """graph.init must be called with settings values during app lifespan startup."""
    with patch("app.db.init_pool"), patch("app.db.close_pool"), \
         patch("app.graph.init") as mock_init, patch("app.graph.close"):
        with TestClient(main.app):
            mock_init.assert_called_once_with(
                settings.neo4j_uri,
                settings.neo4j_user,
                settings.neo4j_password,
            )


def test_graph_close_called_on_shutdown():
    """graph.close must be called during app lifespan shutdown."""
    with patch("app.db.init_pool"), patch("app.db.close_pool"), \
         patch("app.graph.init"), patch("app.graph.close") as mock_close:
        with TestClient(main.app):
            pass  # context exit triggers shutdown
        mock_close.assert_called_once()
