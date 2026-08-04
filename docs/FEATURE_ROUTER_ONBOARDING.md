# Router Onboarding Wizard

## Overview

A brand-new user installs the app, lands on the welcome screen, adds their first
OpenWrt router, and lands on the live dashboard — without ever editing a YAML
file or touching Swagger.

The feature is a small frontend wizard that reuses the existing onboarding API
(`/api/v1/routers/*`). No new service layers were introduced and no mock data
is produced anywhere.

## Flow

1. **Redirect** — the home page (`/`) calls `GET /api/v1/routers/connections`.
   When the list is empty the user is automatically sent to `/onboarding`.
2. **Welcome** — `/onboarding` shows the brand, a short description, and an
   **Add First Router** primary button.
3. **Router information** — a form collects Router Name, Host / IP Address,
   SSH Port (default 22), Username, and the Authentication Method
   (`Password` or `SSH Private Key`). The available actions are **Back** and
   **Test Connection**.
4. **Connection summary** — **Test Connection** calls
   `POST /api/v1/routers/detect`. On success the wizard shows a
   **✓ Connected** panel with: Hostname, OpenWrt Version, Model, Kernel,
   Architecture, CPU, Memory, Network Interfaces, Wireless Radios, and the
   Installed Package count. On failure the backend error is displayed verbatim.
5. **Save Router** — **Save Router** calls `POST /api/v1/routers/save` with the
   collected credentials and the entered name. On success the user is
   automatically navigated to `/dashboard`.
6. **Dashboard** — when at least one router exists, `/onboarding` redirects
   straight to `/dashboard`; the wizard is never shown again.

## Frontend changes

| File | Change |
|---|---|
| `frontend/app/onboarding/page.tsx` | Rebuilt as a three-view wizard (welcome → form → connected/save) that calls the existing onboarding API helpers. |
| `frontend/app/page.tsx` | Redirects to `/onboarding` when no router is configured. |
| `frontend/lib/onboarding.ts` | `DeviceInfo` extended with the connection summary fields (`kernel`, `architecture`, `cpu`, `memory`, `network_interfaces`, `wifi_radios`, `packages_count`). |

All UI reuses the existing shadcn/ui components (Button, Card, Input, Label,
Skeleton) and the existing theme tokens, so dark mode is supported out of the
box. The page is responsive on small and large viewports.

## Backend changes

`backend/app/services/onboarding.py` — the existing `detect_device` flow is
extended to also produce the wizard summary by reusing the router-agent
collectors already used by the live snapshot feed:

- `_collect_snapshot()` builds a real `DeviceSnapshot` over the same SSH
  transport, running only the sections the wizard renders (`kernel`, `cpu`,
  `memory`, `network`, `wifi`, `packages`).
- `_detail_from_snapshot()` maps that snapshot onto the flat summary fields the
  wizard displays. Missing sections map to `null`/empty values instead of
  failing.

The API contract of `POST /api/v1/routers/detect` is unchanged in spirit — it
returns `ok`, `is_openwrt`, `host`, `model`, `firmware`, `hostname`,
`device_id` — and now additionally returns the summary keys above. No new
endpoints were added.

## Tests

`tests/unit/test_onboarding_service.py` and `tests/unit/test_onboarding_api.py`
now cover the extended detect response, including the field mapping for a fully
populated snapshot and for a snapshot with no collected sections.

Run the affected tests with:

```bash
python -m pytest tests/unit/test_onboarding_service.py tests/unit/test_onboarding_api.py
```

## Build

Frontend production build (type-check, lint, static pages):

```bash
cd frontend && npm run build
```
