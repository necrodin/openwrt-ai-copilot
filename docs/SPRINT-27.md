# Sprint 27 — Professional Dashboard (UI Only)

## Objective

Transform the on-screen prototype into a production-quality Network Operations
Center (NOC) dashboard inspired by Grafana, UniFi, Omada, and Microsoft Defender
— **without touching the backend, the onboarding APIs, or the router-agent**, and
**without any fake or mock data**.

The dashboard is rebuilt around a persistent app shell (collapsible sidebar, top
header, right AI Copilot placeholder), a responsive reusable widget grid, an
explicit loading/empty/error contract for every widget, dark/light theming, and a
transport-agnostic data layer so the future WebSocket feed can replace today's
polling **without changing a single widget**.

## Scope guards honored

- **Backend untouched.** No API signature, route, or response shape was modified.
- **No mock data.** Widgets render only what the live REST endpoints return.
- **No new WebSockets.** The dashboard now polls two existing REST endpoints
  (`GET /api/v1/dashboard/latest`, `GET /api/v1/router/status`). The existing
  `useDashboardSocket` hook is retained as the documented future transport.
- **Existing features preserved.** Router onboarding, SSH connection test,
  Save Router, dashboard loading, live diagnosis, and recommendations all keep
  working. The real AI chat page stays at `/chat`.

## Existing REST endpoints used

| Purpose | Endpoint | Cadence |
| --- | --- | --- |
| Live snapshot (widgets) | `GET /api/v1/dashboard/latest` | polled every 5s |
| Snapshot + diagnosis + recommendations | `GET /api/v1/router/status` | polled every 60s |
| Saved router list | `GET /api/v1/router/connections` | on mount |

No mock data is synthesized; empty/offline states are rendered honestly.

## Architecture decisions

1. **UI-only, route-group shell.** The console pages live under
   `app/(console)/` sharing one `layout.tsx` that mounts `AppShell`. Only the
   **Dashboard** page is functional; every other nav target is a `ComingSoon`
   placeholder. `/chat` and `/onboarding` remain outside the shell and keep
   their prior layouts.

2. **Transport-agnostic data layer.** Components never `fetch` directly. The
   dashboard consumes `useDashboardData()` / `useRouterStatus()`, which wrap a
   generic `usePolling()` hook (`hooks/use-polling.ts`). Swapping polling for the
   WebSocket feed later only changes the internals of `useDashboardData` — the
   public `{ update, status, loading, error, refetch }` contract is unchanged.
   `useDashboardSocket` already returns the same `{ update, status }` shape.

3. **Reusable widget shell.** Every widget renders through `Widget`
   (`components/dashboard/widget.tsx`), which centralizes title/icon/subtitle,
   the **loading** (skeleton) and **error** states, plus layout. Individual
   widgets only implement their empty-vs-content logic. `StatusBadge`,
   `WidgetSkeleton`, `WidgetGrid`, and `ChartPlaceholder` are shared and never
   duplicated per widget.

4. **Explicit state contract per widget.** Each widget accepts optional
   `loading?: boolean` and `error?: string | null` and renders (a) skeleton,
   (b) error, (c) empty, or (d) content. The page derives these flags once:
   `loading` only while the first snapshot is pending; `error` only when there is
   no data to show yet (stale data keeps rendering with a warning banner).

5. **Theming.** A `ThemeProvider` (light/dark) toggles the `dark` class on the
   root element using the existing design-system tokens in `globals.css`,
   persists the choice in `localStorage`, respects the OS preference, and
   injects a tiny inline script to avoid a flash of incorrect theme.

6. **Health Score is pure client logic.** `computeHealthScore()` derives a
   0–100 score and contributing factors from the live snapshot (CPU, memory,
   storage, WAN, temperature, VPN, wireless). No backend call was added.

## Component tree

```
app/layout.tsx                      → ThemeProvider + theme-init script
└── ThemeProvider
    ├── /                           (home, unchanged)
    ├── /onboarding                 (unchanged)
    ├── /chat                       (unchanged, dedicated layout)
    └── app/(console)/layout.tsx    → AppShell
        ├── AppShell                (client; desktop rail + mobile drawer)
        │   ├── Sidebar             collapsible nav (Dashboard, Routers, Clients,
        │   │                       Wireless, Network, Firewall, VPN, Monitoring,
        │   │                       AI Chat, Settings)
        │   ├── Header              NOC label, HealthStatus, ThemeToggle
        │   └── <main> children
        ├── /dashboard              (functional)
        │   ├── page.tsx            composes header + grid + AI panel
        │   │   ├── useDashboardData      → usePolling → GET /dashboard/latest
        │   │   └── useRouterStatus       → usePolling → GET /router/status
        │   ├── WidgetGrid
        │   │   ├── HealthScoreWidget       (new)
        │   │   ├── CpuWidget / MemoryWidget / StorageWidget
        │   │   ├── WanWidget / LanWidget / InternetWidget
        │   │   ├── WirelessWidget / DevicesWidget / TemperatureWidget
        │   │   ├── FirewallWidget / VpnWidget / BandwidthWidget
        │   │   ├── DiagnosisWidget         (new)
        │   │   └── RecommendationsWidget   (new)
        │   └── AiCopilotPanel     placeholder
        └── /routers /clients /wireless /network /firewall /vpn /monitoring /settings
            └── ComingSoon placeholder pages
```

### Data flow

```
usePolling ──GET──▶ /dashboard/latest  ──▶ DashboardUpdate ──▶ snapshot ──▶ widgets
usePolling ──GET──▶ /router/status     ──▶ diagnosis + recommendations ──▶ widgets
```

## Widgets

| Widget | Data | Empty state | Loading | Error |
| --- | --- | --- | --- | --- |
| Health Score | snapshot (derived score) | yes | yes | yes |
| CPU | snapshot.cpu | yes | yes | yes |
| Memory | snapshot.memory | yes | yes | yes |
| Storage | snapshot.storage | yes | yes | yes |
| WAN Status | snapshot.network (wan) | yes | yes | yes |
| LAN Status | snapshot.network (lan) | yes | yes | yes |
| Wireless | snapshot.wifi | yes | yes | yes |
| Connected Clients | snapshot.clients/arp | yes | yes | yes |
| Firewall | snapshot.firewall | yes | yes | yes |
| VPN | snapshot.vpn | yes | yes | yes |
| Internet | snapshot (routing/network) | yes | yes | yes |
| Temperature | snapshot.temperature | yes | yes | yes |
| Bandwidth | snapshot.network rates | yes | yes | yes |
| Latest Diagnosis | /router/status.diagnosis | yes | yes | yes |
| Recommendations | /router/status.recommendations | yes | yes | yes |

All widgets are responsive (1/2/3 columns via `WidgetGrid`) and may span columns
(e.g. Connected Clients spans 2, Bandwidth spans 3).

## Future WebSocket integration plan

Polling is intentionally a stand-in. To move to the live feed later:

1. Replace the fetcher inside `useDashboardData` with a subscription to
   `useDashboardSocket` (already returns `{ update, status }`), or add an
   optional `transport` argument (`"rest" | "ws"`) to the hook.
2. Keep the returned `{ update, status, loading, error, refetch }` shape
   identical — **no widget changes required**.
3. `useRouterStatus` can keep polling or switch to a push channel for
   diagnosis/recommendations once the backend exposes one.
4. Delete `usePolling`/`dashboard-api` polling once WebSockets are the only
   path, or retain as a graceful offline fallback.

## Screenshots

None were auto-generated in this sprint (no headless browser pipeline). To
capture: start the stack (`npm run dev` with the backend up), open `/dashboard`
in light and dark mode, toggle the sidebar, and screenshot at desktop and mobile
widths. Suggested paths if added to the repo: `docs/screenshots/sprint27-dash-light.png`,
`docs/screenshots/sprint27-dash-dark.png`, `docs/screenshots/sprint27-mobile.png`.

## Validation

Run from `frontend/` — all green:

```
npm run lint          → no errors
npm run typecheck     → no errors
npm run build         → 13 static pages generated (incl. 8 Coming Soon pages)
```

## Files changed

**New — data layer:** `lib/dashboard-api.ts`, `lib/health-score.ts`,
`hooks/use-polling.ts`, `hooks/use-dashboard-data.ts`, `hooks/use-router-status.ts`.

**New — UI:** `components/ui/status-badge.tsx`, `components/ui/theme-toggle.tsx`,
`components/theme/theme-provider.tsx`, `components/dashboard/widget-skeleton.tsx`,
`components/dashboard/widget-grid.tsx`, `components/dashboard/chart-placeholder.tsx`,
`components/dashboard/health-score-widget.tsx`, `components/dashboard/diagnosis-widget.tsx`,
`components/dashboard/recommendations-widget.tsx`,
`components/layout/app-shell.tsx`, `sidebar.tsx`, `header.tsx`,
`ai-copilot-panel.tsx`, `coming-soon.tsx`.

**New — pages:** `app/(console)/layout.tsx`, `app/(console)/dashboard/page.tsx`,
and `app/(console)/{routers,clients,wireless,network,firewall,vpn,monitoring,settings}/page.tsx`.

**Changed:** `components/dashboard/widget.tsx` (loading/error shell),
13 existing widgets (added `loading`/`error` pass-through), `app/layout.tsx`
(ThemeProvider), `app/(console)/dashboard/page.tsx` (rewritten; moved from
`app/dashboard/page.tsx`).

**Retained as documented future transport:** `hooks/use-dashboard-socket.ts`.

**Docs:** `docs/SPRINT-27.md`.