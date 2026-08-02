# Sprint 10A — SSH Transport Layer

## Goal

Deliver the SSH transport layer for reaching OpenWrt devices: an async-native engine
over three interchangeable backends (asyncssh, paramiko, mock), plus connection pooling,
reconnects, retries, timeouts, keep-alive, host key verification, and health probes.

## Scope

Refactors the legacy `router_agent.transport.ssh` module into a package with clean
separation of concerns:

- **Backends** — `AsyncSSHBackend`, `ParamikoBackend`, `MockSSHBackend` + factory `build_backend`
- **Connection** — `SSHConnection` wrapping a single backend session with validation
- **Pool** — `SSHConnectionPool` with bounded semaphore, idle reuse, dead‑connection replacement
- **Client** — `SSHClient` with retries and automatic reconnects on transient failures
- **Transport** — `SSHTransport` (synchronous facade preserving the `CommandRunner` contract)
- **Bridge** — `EventLoopBridge` for running async coroutines from synchronous callers
- **Config** — `SSHConfig` and `SSHCredentials` dataclasses with validation
- **Health** — `SSHHealth` reporting connection liveness and probe latency
- **Errors** — `SSHError` hierarchy extending `RouterAgentError` and `ConnectionFailedError`

## Files

### Created

```
router-agent/src/router_agent/transport/ssh/__init__.py
router-agent/src/router_agent/transport/ssh/backends.py
router-agent/src/router_agent/transport/ssh/bridge.py
router-agent/src/router_agent/transport/ssh/client.py
router-agent/src/router_agent/transport/ssh/config.py
router-agent/src/router_agent/transport/ssh/connection.py
router-agent/src/router_agent/transport/ssh/errors.py
router-agent/src/router_agent/transport/ssh/health.py
router-agent/src/router_agent/transport/ssh/pool.py
router-agent/src/router_agent/transport/ssh/transport.py
tests/unit/test_ssh_backends.py
tests/unit/test_ssh_pool.py
docs/SPRINT-10A.md
```

**Modified**

```
router-agent/pyproject.toml              — version 0.6.0a1, added paramiko + asyncssh deps
router-agent/src/router_agent/__init__.py        — version 0.6.0a1
router-agent/src/router_agent/transport/__init__.py  — import from ssh package
```

**Deleted**

```
router-agent/src/router_agent/transport/ssh.py   — replaced by ssh/ package
```

## Tests

40 new unit tests across `test_ssh_backends.py` (29) and `test_ssh_pool.py` (11).
Full suite: **575 passed**, lint clean.

## Tag

`v0.6.0-alpha.1`