"""Shared authentication helpers for the API test-suite.

The values mirror the keys/credentials configured in ``tests/conftest.py`` via
environment variables so the application settings resolve to the same values.

Browser logins use a username + password (``TEST_ADMIN_USERNAME`` /
``TEST_ADMIN_PASSWORD`` and the read-only pair); programmatic clients use the
static API keys via ``Authorization: Bearer``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

TEST_ADMIN_KEY = "test-admin-key"
TEST_READONLY_KEY = "test-readonly-key"
TEST_UNKNOWN_KEY = "not-a-real-key"

TEST_ADMIN_USERNAME = "admin"
TEST_ADMIN_PASSWORD = "test-admin-password"
TEST_READONLY_USERNAME = "viewer"
TEST_READONLY_PASSWORD = "test-readonly-password"


def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_ADMIN_KEY}"}


def readonly_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_READONLY_KEY}"}


def unknown_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_UNKNOWN_KEY}"}


def ws_token_query(*, admin: bool = True) -> str:
    key = TEST_ADMIN_KEY if admin else TEST_READONLY_KEY
    return f"token={key}"


def browser_login(
    client: TestClient,
    *,
    admin: bool = True,
    username: str | None = None,
    password: str | None = None,
) -> str:
    """Mint a browser session token via the username/password login endpoint.

    Defaults to the admin account; pass ``admin=False`` for the read-only
    account or explicit ``username``/``password`` for custom credentials.
    """
    username = username or (TEST_ADMIN_USERNAME if admin else TEST_READONLY_USERNAME)
    password = password or (TEST_ADMIN_PASSWORD if admin else TEST_READONLY_PASSWORD)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]
