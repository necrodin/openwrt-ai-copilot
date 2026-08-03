"""SSH transport layer (Sprint 10A).

The communication layer for reaching an OpenWrt device: an async-native engine
over three interchangeable backends — **asyncssh** (preferred), the **paramiko**
fallback, and an in-memory **mock** — plus connection pooling, reconnects,
retries, timeouts, keep-alive, host key verification, and health probes.

The synchronous :class:`SSHTransport` keeps the existing ``CommandRunner``
contract used by collectors and the dashboard, so nothing upstream changes.
"""

from router_agent.transport.ssh.backends import (
    AsyncSSHBackend,
    MockSSHBackend,
    ParamikoBackend,
    SSHBackend,
    asyncssh_available,
    build_backend,
)
from router_agent.transport.ssh.bridge import EventLoopBridge
from router_agent.transport.ssh.client import SSHClient
from router_agent.transport.ssh.config import HOST_KEY_POLICIES, SSHConfig, SSHCredentials
from router_agent.transport.ssh.connection import DEFAULT_PROBE, SSHConnection
from router_agent.transport.ssh.errors import (
    AuthenticationError,
    ConnectionError,
    HostKeyError,
    SSHError,
    TimeoutError,
)
from router_agent.transport.ssh.health import SSHHealth
from router_agent.transport.ssh.pool import SSHConnectionPool
from router_agent.transport.ssh.transport import ConnectionState, SSHTransport

__all__ = [
    "SSHClient",
    "SSHConnection",
    "SSHConnectionPool",
    "SSHConfig",
    "SSHCredentials",
    "SSHHealth",
    "SSHTransport",
    "ConnectionState",
    "SSHBackend",
    "AsyncSSHBackend",
    "ParamikoBackend",
    "MockSSHBackend",
    "build_backend",
    "asyncssh_available",
    "EventLoopBridge",
    "DEFAULT_PROBE",
    "HOST_KEY_POLICIES",
    "SSHError",
    "AuthenticationError",
    "ConnectionError",
    "HostKeyError",
    "TimeoutError",
]
