"""Tests for SSH backends: MockSSHBackend, build_backend, error normalization."""

from __future__ import annotations

import time

import pytest

from router_agent.errors import CommandError
from router_agent.transport.ssh.backends import (
    MockSSHBackend,
    asyncssh_available,
    build_backend,
)
from router_agent.transport.ssh.config import SSHConfig, SSHCredentials
from router_agent.transport.ssh.errors import (
    AuthenticationError,
    HostKeyError,
    SSHError,
)
from router_agent.transport.ssh.errors import (
    ConnectionError as SSHConnectionError,
)
from router_agent.transport.ssh.errors import (
    TimeoutError as SSHTimeoutError,
)


def _config(**kwargs) -> SSHConfig:
    defaults = {"host": "10.0.0.1", "credentials": SSHCredentials(username="root")}
    return SSHConfig(**(defaults | kwargs))


# =============================================================================
# MockSSHBackend — connect
# =============================================================================


@pytest.mark.asyncio
async def test_mock_connect_success() -> None:
    backend = MockSSHBackend(_config())
    await backend.connect()
    assert backend.connected is True
    assert backend.connect_count == 1


@pytest.mark.asyncio
async def test_mock_connect_fail_connect() -> None:
    backend = MockSSHBackend(_config(), fail_connect=True)
    with pytest.raises(SSHConnectionError):
        await backend.connect()
    assert backend.connected is False
    assert backend.connect_count == 1


@pytest.mark.asyncio
async def test_mock_connect_fail_auth() -> None:
    backend = MockSSHBackend(_config(), fail_auth=True)
    with pytest.raises(AuthenticationError):
        await backend.connect()


@pytest.mark.asyncio
async def test_mock_connect_fail_host_key() -> None:
    backend = MockSSHBackend(_config(), fail_host_key=True)
    with pytest.raises(HostKeyError):
        await backend.connect()


@pytest.mark.asyncio
async def test_mock_connect_timeout() -> None:
    backend = MockSSHBackend(_config(), timeout_on_connect=True)
    with pytest.raises(SSHTimeoutError):
        await backend.connect()


@pytest.mark.asyncio
async def test_mock_require_username_rejects_wrong_username() -> None:
    backend = MockSSHBackend(_config(), require_username="admin")
    with pytest.raises(AuthenticationError):
        await backend.connect()


@pytest.mark.asyncio
async def test_mock_require_username_allows_correct_username() -> None:
    backend = MockSSHBackend(_config(), require_username="root")
    await backend.connect()
    assert backend.connected is True


@pytest.mark.asyncio
async def test_mock_require_password_rejects_wrong_password() -> None:
    cfg = _config()
    cfg = SSHConfig(
        host="10.0.0.1",
        credentials=SSHCredentials(username="root", password="wrong"),
    )
    backend = MockSSHBackend(cfg, require_password="correct")
    with pytest.raises(AuthenticationError):
        await backend.connect()


@pytest.mark.asyncio
async def test_mock_require_password_allows_correct_password() -> None:
    cfg = SSHConfig(
        host="10.0.0.1",
        credentials=SSHCredentials(username="root", password="secret"),
    )
    backend = MockSSHBackend(cfg, require_password="secret")
    await backend.connect()
    assert backend.connected is True


@pytest.mark.asyncio
async def test_mock_require_key_rejects_no_key() -> None:
    backend = MockSSHBackend(_config(), require_key=True)
    with pytest.raises(AuthenticationError):
        await backend.connect()


@pytest.mark.asyncio
async def test_mock_require_key_allows_with_key() -> None:
    cfg = SSHConfig(
        host="10.0.0.1",
        credentials=SSHCredentials(username="root", private_key="fake-key-data"),
    )
    backend = MockSSHBackend(cfg, require_key=True)
    await backend.connect()
    assert backend.connected is True


# =============================================================================
# MockSSHBackend — run
# =============================================================================


@pytest.mark.asyncio
async def test_mock_run_scripted_output() -> None:
    backend = MockSSHBackend(_config(), scripts={"df -h": "filesystem...", "free": "memory..."})
    await backend.connect()
    assert await backend.run("df -h") == "filesystem..."
    assert await backend.run("free -m") == "memory..."
    assert "df -h" in backend.calls
    assert "free -m" in backend.calls
    assert backend.run_count == 2


@pytest.mark.asyncio
async def test_mock_run_raises_for_unscripted_command() -> None:
    backend = MockSSHBackend(_config())
    await backend.connect()
    with pytest.raises(CommandError):
        await backend.run("unknown_command")


@pytest.mark.asyncio
async def test_mock_run_raises_when_not_connected() -> None:
    backend = MockSSHBackend(_config())
    with pytest.raises(SSHConnectionError):
        await backend.run("echo hi")


@pytest.mark.asyncio
async def test_mock_run_timeout_on_matching_commands() -> None:
    backend = MockSSHBackend(_config(), timeout_commands=("slow",))
    await backend.connect()
    with pytest.raises(SSHTimeoutError):
        await backend.run("slow --verbose", timeout=0.1)


@pytest.mark.asyncio
async def test_mock_run_timeout_skips_non_matching_commands() -> None:
    backend = MockSSHBackend(_config(), timeout_commands=("slow",), scripts={"fast": "done"})
    await backend.connect()
    result = await backend.run("fast")
    assert result == "done"


@pytest.mark.asyncio
async def test_mock_run_latency_is_applied() -> None:
    backend = MockSSHBackend(_config(), scripts={"ping": "pong"}, latency=0.05)
    await backend.connect()
    start = time.perf_counter()
    result = await backend.run("ping")
    elapsed = time.perf_counter() - start
    assert result == "pong"
    assert elapsed >= 0.04


# =============================================================================
# MockSSHBackend — is_alive, close, tracking
# =============================================================================


@pytest.mark.asyncio
async def test_mock_is_alive_false_before_connect() -> None:
    backend = MockSSHBackend(_config())
    assert await backend.is_alive() is False


@pytest.mark.asyncio
async def test_mock_is_alive_after_connect() -> None:
    backend = MockSSHBackend(_config())
    await backend.connect()
    assert await backend.is_alive() is True


@pytest.mark.asyncio
async def test_mock_is_alive_after_close() -> None:
    backend = MockSSHBackend(_config())
    await backend.connect()
    await backend.close()
    assert await backend.is_alive() is False


@pytest.mark.asyncio
async def test_mock_is_alive_with_drop_after() -> None:
    backend = MockSSHBackend(_config(), drop_after=2, scripts={"cmd": "ok"})
    await backend.connect()
    assert await backend.is_alive() is True
    await backend.run("cmd 1")
    assert await backend.is_alive() is True
    await backend.run("cmd 2")
    assert await backend.is_alive() is False


@pytest.mark.asyncio
async def test_mock_drop_after_zero_never_drops() -> None:
    backend = MockSSHBackend(_config(), drop_after=0, scripts={"cmd": "ok"})
    await backend.connect()
    for _ in range(100):
        await backend.run("cmd x")
    assert await backend.is_alive() is True


@pytest.mark.asyncio
async def test_mock_last_activity_updated_on_connect_and_run() -> None:
    backend = MockSSHBackend(_config(), scripts={"test": "ok"})
    assert backend.last_activity is None
    await backend.connect()
    assert backend.last_activity is not None
    t_connect = backend.last_activity
    await backend.run("test")
    assert backend.last_activity >= t_connect


@pytest.mark.asyncio
async def test_mock_close_resets_state() -> None:
    backend = MockSSHBackend(_config(), scripts={"test": "ok"})
    await backend.connect()
    await backend.run("test")
    await backend.close()
    assert backend.connected is False
    with pytest.raises(SSHConnectionError):
        await backend.run("test")


@pytest.mark.asyncio
async def test_mock_keepalive_calls_tracked() -> None:
    backend = MockSSHBackend(_config())
    await backend.set_keepalive(30.0)
    await backend.set_keepalive(60.0)
    assert backend.keepalive_calls == [30.0, 60.0]


# =============================================================================
# build_backend factory
# =============================================================================


def test_build_backend_mock_explicit() -> None:
    backend = build_backend(_config(), name="mock")
    assert isinstance(backend, MockSSHBackend)


def test_build_backend_invalid_name() -> None:
    with pytest.raises(SSHError, match="unknown SSH backend"):
        build_backend(_config(), name="bogus")


def test_build_backend_auto_chooses_asyncssh_when_available() -> None:
    from router_agent.transport.ssh.backends import AsyncSSHBackend

    if not asyncssh_available():
        pytest.skip("asyncssh not installed")
    backend = build_backend(_config(), name=None)
    assert isinstance(backend, AsyncSSHBackend)


def test_build_backend_asyncssh_not_installed_falls_back_to_paramiko(monkeypatch) -> None:
    import router_agent.transport.ssh.backends as mod

    def _unavailable() -> bool:
        return False

    monkeypatch.setattr(mod, "asyncssh_available", _unavailable)
    backend = build_backend(_config(), name=None)
    assert backend.name == "paramiko"
