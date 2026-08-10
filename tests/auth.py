"""Shared authentication helpers for the API test-suite.

The values mirror the keys configured in ``tests/conftest.py`` via environment
variables so the application settings resolve to the same credentials.
"""

from __future__ import annotations

TEST_ADMIN_KEY = "test-admin-key"
TEST_READONLY_KEY = "test-readonly-key"
TEST_UNKNOWN_KEY = "not-a-real-key"


def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_ADMIN_KEY}"}


def readonly_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_READONLY_KEY}"}


def unknown_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_UNKNOWN_KEY}"}


def ws_token_query(*, admin: bool = True) -> str:
    key = TEST_ADMIN_KEY if admin else TEST_READONLY_KEY
    return f"token={key}"
