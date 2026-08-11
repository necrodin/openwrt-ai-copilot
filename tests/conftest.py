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
os.environ["AUTH_ADMIN_API_KEY"] = "test-admin-key"
os.environ["AUTH_READONLY_API_KEY"] = "test-readonly-key"
# Keep the persisted SSH host-key store out of the working tree during tests.
os.environ["OPENWRT_AI_KNOWN_HOSTS"] = f"{_TMP_DIR}/known_hosts"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tests.auth import admin_headers  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """FastAPI TestClient with lifespan (database init) executed."""
    from app.main import create_app

    with TestClient(create_app(), headers=admin_headers()) as test_client:
        yield test_client
