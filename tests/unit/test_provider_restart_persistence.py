"""Real restart persistence for provider configuration and credentials.

Spins up the actual uvicorn app in an isolated temporary data directory,
creates a provider with an API key over HTTP, then kills and restarts the
process to prove that after a backend restart:

- the provider configuration survives (providers.yaml metadata only),
- the encrypted credential decrypts through the vault,
- ``GET /providers`` reports ``has_credential: true`` without ever returning
  the key,
- the saved model survives.
"""

from __future__ import annotations

import json
import os
import pathlib
import socket
import subprocess
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PY = str(ROOT / ".venv" / "bin" / "python")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _env(tmp: pathlib.Path, port: int) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "PROVIDER_CONFIG_FILE": str(tmp / "providers.yaml"),
            "DATABASE_URL": f"sqlite:///{tmp / 'data' / 'test.db'}",
            "SECRET_KEY": "restart-test-secret-not-placeholder",
            "AUTH_ADMIN_API_KEY": "restart-test-admin-key",
            "AUTH_READONLY_API_KEY": "restart-test-readonly-key",
            "AUTH_ADMIN_USERNAME": "admin",
            "AUTH_ADMIN_PASSWORD": "restart-test-password",
            "AUTH_READONLY_USERNAME": "viewer",
            "AUTH_READONLY_PASSWORD": "restart-test-password",
            "OPENWRT_AI_KNOWN_HOSTS": str(tmp / "known_hosts"),
            "ROUTER_DEVICE_TRANSPORT": "",
            "RAG_CONFIG_FILE": str(tmp / "rag-missing.yaml"),
            "PYTHONPATH": str(BACKEND),
        }
    )
    return env


def _wait_ready(base: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/v1/health", timeout=2):
                return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.4)
    raise TimeoutError("backend did not become ready")


def _start(base: str, tmp: pathlib.Path, port: int) -> subprocess.Popen:
    (tmp / "data").mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            PY,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(BACKEND),
        env=_env(tmp, port),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_ready(base)
    return proc


def _stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _request(
    base: str,
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{base}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            parsed = json.loads(payload)
        except ValueError:
            parsed = {}
        return exc.code, parsed


def _login(base: str) -> str:
    status, body = _request(
        base,
        "POST",
        "/api/v1/auth/login",
        {"username": "admin", "password": "restart-test-password"},
    )
    assert status == 200, body
    return body["token"]


def test_provider_and_credential_survive_backend_restart(tmp_path: pathlib.Path) -> None:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    secret = "restart-test-secret"

    proc = _start(base, tmp_path, port)
    try:
        token = _login(base)
        status, created = _request(
            base,
            "POST",
            "/api/v1/providers",
            {
                "type": "deepseek",
                "name": "DeepSeek",
                "model": "deepseek-v4-flash",
                "credential": secret,
            },
            token,
        )
        assert status == 201, created
        assert created["has_credential"] is True
        assert created["model"] == "deepseek-v4-flash"
    finally:
        _stop(proc)

    # At rest: metadata-only YAML + encrypted credential file, no plaintext key.
    yaml_text = (tmp_path / "providers.yaml").read_text(encoding="utf-8")
    assert "deepseek:" in yaml_text
    assert secret not in yaml_text
    cred_path = tmp_path / "provider_credentials.json"
    assert cred_path.is_file()
    cred_raw = cred_path.read_text(encoding="utf-8")
    assert secret not in cred_raw
    assert "encv1:" in cred_raw

    # Simulate an application restart.
    proc = _start(base, tmp_path, port)
    try:
        token = _login(base)
        status, listed = _request(base, "GET", "/api/v1/providers", token=token)
        assert status == 200
        providers = {p["type"]: p for p in listed["providers"]}
        assert "deepseek" in providers
        deepseek = providers["deepseek"]
        assert deepseek["has_credential"] is True
        assert deepseek["model"] == "deepseek-v4-flash"
        assert secret not in json.dumps(listed)

        status, detail = _request(base, "GET", "/api/v1/providers/deepseek", token=token)
        assert status == 200
        assert detail["has_credential"] is True
        assert detail["model"] == "deepseek-v4-flash"
    finally:
        _stop(proc)
