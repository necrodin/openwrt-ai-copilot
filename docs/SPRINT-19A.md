# Sprint 19A — Connect Router Dashboard to Live Backend

## Objective
Connect the existing dashboard page to the live backend `GET /router/status`
endpoint, replacing static/placeholder router values with real data and adding
loading, error, and unavailable states. No backend logic, router logic, or AI
logic changes.

## Architecture
```
frontend/app/dashboard/page.tsx
  ├─ useEffect fetch("/api/v1/router/status")
  │     └─ GET /router/status → { snapshot, diagnosis, recommendations }
  ├─ loading state      → skeleton placeholders
  ├─ error state        → destructive banner with the failure message
  └─ RouterStatusPanel  → renders when data arrives
        ├─ snapshot == null  → "Router unavailable"
        └─ otherwise         → Online badge, hostname, model, firmware, kernel,
                               CPU, memory, storage, diagnosis list,
                               recommendations list
```
- The existing WebSocket-driven widget grid is untouched; the REST status panel
  is rendered from `GET /router/status`.
- The response types (`RouterSnapshotData`, `RouterFinding`,
  `RouterRecommendation`) mirror the backend `RouterSnapshot.to_dict()`,
  `Finding.to_dict()`, and `Recommendation.to_dict()` shapes.
- Severity maps to badge variants (`critical` → destructive, `warning` →
  outline, `info` → secondary); priority maps similarly (`urgent` → destructive,
  `high` → outline, `medium` → secondary, `low` → default).
- No new pages, no UI redesign; the existing dashboard layout is preserved.

## Files Changed
| File | Change |
| --- | --- |
| `frontend/app/dashboard/page.tsx` | Fetch router status from the live backend; add loading/error/unavailable states; render a Router Status panel with hostname, firmware, kernel, CPU, memory, storage, diagnosis, and recommendations. |

## Tests Executed
- No affected tests: there are no frontend test files for the dashboard, and no
  backend files changed.

## Verification
- `npm run lint` passes.
- `npm run typecheck` passes.
- `npm run build` (production) succeeds; `/dashboard` compiles to a static
  route.
- Healthy snapshot renders all fields plus diagnosis and recommendation lists;
  `snapshot: null` renders "Router unavailable" without throwing; fetch failures
  surface an error state; loading renders skeletons.
