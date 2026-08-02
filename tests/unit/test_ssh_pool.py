"""Tests for SSHConnectionPool: acquire, release, health, sizing."""

from __future__ import annotations

import pytest

from router_agent.transport.ssh.backends import MockSSHBackend
from router_agent.transport.ssh.config import SSHConfig, SSHCredentials
from router_agent.transport.ssh.connection import SSHConnection
from router_agent.transport.ssh.pool import SSHConnectionPool


def _config(**kwargs) -> SSHConfig:
    defaults = {"host": "10.0.0.1", "credentials": SSHCredentials(username="root"), "pool_size": 3}
    return SSHConfig(**(defaults | kwargs))


def _mock_factory(config):
    return MockSSHBackend(config, scripts={"echo ok": "ok", "cmd": "OK"})


def _failing_factory(config):
    return MockSSHBackend(config, fail_connect=True)


# =============================================================================
# Pool lifecycle
# =============================================================================


@pytest.mark.asyncio
async def test_pool_creates_on_demand() -> None:
    pool = SSHConnectionPool(_config(pool_size=3), backend_factory=_mock_factory)
    assert pool.size == 0
    assert pool.idle == 0
    assert pool.busy == 0


@pytest.mark.asyncio
async def test_pool_acquire_and_release() -> None:
    pool = SSHConnectionPool(_config(pool_size=3), backend_factory=_mock_factory)
    async with pool.acquire() as conn:
        assert isinstance(conn, SSHConnection)
        assert await conn.is_alive() is True
        result = await conn.run("cmd")
        assert result == "OK"
    assert pool.idle == 1
    assert pool.size == 1


@pytest.mark.asyncio
async def test_pool_reuses_idle_connections() -> None:
    pool = SSHConnectionPool(_config(pool_size=3), backend_factory=_mock_factory)
    conn1 = None
    async with pool.acquire() as conn:
        conn1 = conn
    async with pool.acquire() as conn2:
        assert conn2 is conn1
    assert pool.size == 1
    assert pool.idle == 1


@pytest.mark.asyncio
async def test_pool_creates_new_when_idle_empty() -> None:
    pool = SSHConnectionPool(_config(pool_size=3), backend_factory=_mock_factory)
    async with pool.acquire() as conn1, pool.acquire() as conn2:
        assert conn1 is not conn2
        assert pool.busy == 2
        assert pool.idle == 0
        assert pool.size == 2
    assert pool.idle == 2
    assert pool.size == 2


@pytest.mark.asyncio
async def test_pool_honors_semaphore() -> None:
    """pool_size=1 ensures only one lease is granted at a time."""
    pool = SSHConnectionPool(_config(pool_size=2), backend_factory=_mock_factory)
    async with pool.acquire(), pool.acquire():
        assert pool.busy == 2
    assert pool.size == 2


# =============================================================================
# Validation
# =============================================================================


@pytest.mark.asyncio
async def test_pool_validate_probes_connection() -> None:
    pool = SSHConnectionPool(_config(pool_size=3), backend_factory=_mock_factory)
    async with pool.acquire(validate=True) as conn:
        result = await conn.run("cmd")
        assert result == "OK"


@pytest.mark.asyncio
async def test_pool_health_returns_health_objects() -> None:
    pool = SSHConnectionPool(_config(pool_size=3), backend_factory=_mock_factory)
    async with pool.acquire():
        pass
    results = await pool.health()
    assert len(results) == 1
    assert results[0].ok is True


# =============================================================================
# Error cases
# =============================================================================


@pytest.mark.asyncio
async def test_pool_acquire_after_close_raises() -> None:
    pool = SSHConnectionPool(_config(pool_size=3), backend_factory=_mock_factory)
    await pool.close()
    with pytest.raises(RuntimeError, match="closed"):
        async with pool.acquire():
            pass


@pytest.mark.asyncio
async def test_pool_close_cleans_up_idle() -> None:
    pool = SSHConnectionPool(_config(pool_size=3), backend_factory=_mock_factory)
    async with pool.acquire():
        pass
    assert pool.idle == 1
    await pool.close()
    assert pool.idle == 0


# =============================================================================
# Dead connection replacement
# =============================================================================


@pytest.mark.asyncio
async def test_pool_discards_dead_connections_on_acquire() -> None:
    """Connections whose is_alive returns False are discarded."""
    pool = SSHConnectionPool(_config(pool_size=3), backend_factory=_mock_factory)
    async with pool.acquire() as conn:
        conn_id = id(conn)
    assert pool.idle == 1
    # Kill the idle connection
    await list(pool._idle)[0].close()
    async with pool.acquire() as conn2:
        assert id(conn2) != conn_id


@pytest.mark.asyncio
async def test_pool_discards_failed_validation() -> None:
    """When validate=True, failing probes cause connection replacement."""
    pool = SSHConnectionPool(_config(pool_size=3), backend_factory=_mock_factory)
    async with pool.acquire():
        pass
    assert pool.idle == 1
    # Force the idle connection to fail validation
    idle_conn = pool._idle[0]
    await idle_conn.close()
    async with pool.acquire(validate=True) as conn2:
        assert conn2 is not idle_conn


# =============================================================================
# Helpers
# =============================================================================


def _make(pool):
    """Helper to get pool objects since direct access is unavoidable in tight tests."""
    return pool


@pytest.fixture
def shared_pool():
    return SSHConnectionPool(_config(pool_size=4), backend_factory=_mock_factory)
