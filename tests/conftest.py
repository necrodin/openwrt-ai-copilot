"""Shared pytest fixtures.

Environment variables are set at import time (before any application module is
imported) so the database engine and settings bind to a throwaway SQLite file
instead of the development database.
"""

from __future__ import annotations

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="openwrt-ai-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/test.db"
os.environ["SECRET_KEY"] = "test-only-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """FastAPI TestClient with lifespan (database init) executed."""
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
