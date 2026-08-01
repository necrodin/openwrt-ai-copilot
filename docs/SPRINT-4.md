# Sprint 4 — Live Dashboard

Status: **complete** (verification: 126 pytest passed, ruff clean, Next.js
typecheck + lint + production build pass; REST + WebSocket verified against a
running backend).

## Goal

A real-time monitoring dashboard for a router with **twelve live widgets** and
**WebSocket-driven updates**. No AI. Data comes from the Sprint-4+ router agent's
normalized `DeviceSnapshot`.

## Widgets

| Widget | Source section | Content |
|---|---|---|
| CPU | `cpu` | Usage %, load 1/5/15, cores, frequency, uptime |
| RAM | `memory` | Used/total gauge, free, available, cached, buffered |
| Storage | `storage` | Per-mount usage gauges (total/used/percent) |
| Temperature | `temperature` | Per-zone readings, color-coded by threshold |
| WAN | `network` (uplink) | Addresses, link, speed, rx/tx totals |
| LAN | `network` (local) | Addresses, link, speed, rx/tx totals |
| Firewall | `firewall` | Zone policies (input/output/forward), masquerade, rule count |
| VPN | `vpn` | Tunnel status, kind, peers, listen port |
| Wireless | `wifi` | Radios (SSID, band, channel), client/station counts |
| Bandwidth | `network` (deltas) | Live rx/tx throughput with sparklines (last 60 samples) |
| Connected Devices | `clients`/`arp` | Hostname, IP, MAC, interface table |
| Internet | `routing` + `network` | Online/Degraded/Offline from default route + WAN address |

WAN vs LAN classification: `proto` in
{dhcp, dhcpv6, pppoe, ppp, qmi, wwan, wwan6, 3g, lte} or a `wan*` name counts as
WAN; everything else is LAN.

## Realtime architecture

```
router-agent collectors (SSH / local / ubus)
        │  one normalized DeviceSnapshot
        ▼
SnapshotService (asyncio task) ──poll interval──► to_thread(_collect_once)
        │  _frame() → DashboardUpdate {sequence, source, connected, error, snapshot}
        ▼
subscriber asyncio.Queues (maxsize=1, drop-oldest)
        ▼
WS /api/v1/dashboard/ws  ──►  Next.js useDashboardSocket() hook
```

- **`app/services/snapshot_service.py`**: background task collects on a timer and
  fans each `DashboardUpdate` out to every subscribed queue. Blocking collection
  runs in `asyncio.to_thread` so the event loop never stalls. If the device is
  unreachable, the last good snapshot is retained, `connected` flips to `False`,
  and polling continues (automatic recovery).
- **`app/services/demo_source.py`**: simulated source producing a plausible,
  time-drifting snapshot (load, CPU %, temperature, traffic counters, device
  count). Default when no router is configured, so the dashboard animates out of
  the box and tests never touch the network.
- **`app/schemas/dashboard.py`**: `DashboardUpdate` wire schema.
- **`app/api/v1/dashboard.py`**: `GET /dashboard/latest` (REST fallback) and
  `WS /dashboard/ws` (streams the latest frame on connect, then every poll).

## Frontend

- `app/dashboard/page.tsx` — page shell, connection/source badges, skeleton
  loading, reconnect banner, responsive grid (1/2/3 columns).
- `hooks/use-dashboard-socket.ts` — WebSocket hook with capped exponential
  backoff reconnect (`500ms → 10s`) and connection status.
- `lib/dashboard.ts` / `lib/dashboard-utils.ts` — snapshot TS types, WAN/LAN
  classifier, WebSocket URL builder, formatters, frame parser.
- `components/dashboard/` — `widget` (Card shell), `gauge`, `sparkline`
  (dependency-free SVG), plus the twelve widgets.
- Bandwidth widget computes rx/tx deltas between consecutive frames client-side
  and keeps a 60-sample history for the sparklines.
- No new npm dependencies.

## Configuration

Environment variables (see `backend/.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `ROUTER_DEVICE_TRANSPORT` | `""` | `""`, `"ssh"`, `"local"`, `"simulated"` |
| `ROUTER_DEVICE_HOST` | `""` | Router address; empty ⇒ simulated demo |
| `ROUTER_DEVICE_PORT` | `22` | SSH port |
| `ROUTER_USERNAME` | `root` | SSH username |
| `ROUTER_SSH_KEY` | `""` | SSH private key path |
| `ROUTER_PASSWORD` | `""` | Optional SSH password |
| `ROUTER_POLL_INTERVAL` | `5.0` | Seconds between polls |

Empty transport auto-selects: `ssh` when a host is set, otherwise `simulated`.

## Tests

`tests/unit/test_dashboard_api.py`:

- Simulated snapshot: all twelve widget sections populated; values drift over
  time.
- Snapshot service: publishes connected updates to a subscriber queue.
- REST `/dashboard/latest`: empty placeholder and populated update.
- WebSocket: streams the initial latest frame then queued frames.

`make test` now runs 126 tests; `make lint` is clean.

## Run

```bash
make dev-backend    # http://localhost:8000/api/docs
make dev-frontend   # http://localhost:3000/dashboard  (demo mode by default)
```

Point the dashboard at a real router by setting `ROUTER_DEVICE_HOST` (+ key)
in `backend/.env`, or force `ROUTER_DEVICE_TRANSPORT=simulated` to preview the
demo feed.

## Roadmap note

This sprint supersedes the original Sprint-4 row in `SPRINT-1.md` (which
planned "router agent + device control" first). Device control (safe
apply / dry-run / rollback) is deferred to a later sprint; the dashboard and
the data-collection agent it depends on land first.
