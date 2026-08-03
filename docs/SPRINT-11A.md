# Sprint 11A — Router Dashboard Integration

Status: **complete**

## Goal

Deliver the first end-to-end router dashboard integration: a new set of API endpoints
(`/router/info`, `/router/status`, `/router/context`) that expose structured router
information, a lightweight connection status summary, and an AI-ready context document
built from the latest device snapshot, alongside transport improvements and a richer
dashboard frontend.

## Scope

### API — router endpoints (`backend/app/api/v1/router.py`)

- `GET /api/v1/router/info` — structured router data (hostname, model, firmware,
  kernel, CPU, memory, storage, network interfaces).
- `GET /api/v1/router/status` — lightweight connection state (online, source,
  device ID, last snapshot, error).
- `GET /api/v1/router/context` — AI-ready structured context including markdown
  summary pipelined for chat injection.

Registered under the aggregated `/api/v1` prefix via `backend/app/api/router.py`.

### AI Context Service (`backend/app/services/router_context.py`)

- Module `router_context` with `build_context()`: consumes a `DashboardUpdate` and
  produces a structured dict with router identity, system health, storage, network,
  WiFi summaries, a pre-rendered markdown block, and the raw snapshot.
- Handles empty/missing snapshots gracefully.

### Router Transport (`router-agent/.../ssh/transport.py`)

- Connection lifecycle: `connect()`, `disconnect()`, `reconnect()`, `close()`.
- State reporting: `connected` (bool), `state` (ConnectionState enum), `config`, `host`,
  `port`, `backend` properties.
- `ConnectionState` exported from `router_agent.transport.ssh`.
- Backward-compatible constructor with new `auto_connect: bool` parameter.

### Frontend Dashboard (`frontend/app/dashboard/page.tsx`)

- Extended header: shows router label, hostname, firmware version, kernel
  version, plus "Online/Offline" connection status badge.

### Tests (`tests/unit/test_router_api.py`)

- Tests for all three `/router/*` endpoints: empty, populated, offline scenarios.
- Unit tests for `build_context()`: None input, no snapshot, markdown coverage,
  serializability, edge cases for CPU/memory/wifi/storage/network.
- Parametrized endpoint registration test.
- `test_router_api.py` — 20 tests alongside the existing 2 indirect dashboard tests.

### Lint Fixes

- Import ordering, unused imports, variable naming (cpu_data -> cpu), line-length
  wraps across `router_context.py`, `router.py`, `transport.py`.
- `SIM105` — `try/except/pass` replaced with `contextlib.suppress`.

## Verification

- 596 pytest tests pass (all)
- ruff check clean
- Next.js production build passes
- Frontend typecheck + lint clean
- git status clean after commit