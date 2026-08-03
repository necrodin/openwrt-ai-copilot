# Sprint 21A — Add Live Router Status Panel to Chat

## Objective
Add a collapsible "Router Status" card inside the existing Chat page
(`frontend/app/chat/page.tsx`) sourced from the existing `GET /router/status`
endpoint. The status is fetched on page load and refreshed before every
message. No new pages, no backend changes, no UI redesign.

## Architecture
```
frontend/app/chat/page.tsx
  ├─ useState routerStatus / routerLoading / routerError / collapsed
  ├─ loadRouterStatus() → fetch("/api/v1/router/status")   (useCallback)
  │     ├─ on mount  → useEffect(loadRouterStatus, [])
  │     └─ before each message → called in ChatInput.onSend, then sendMessage
  ├─ loading state  → Skeleton placeholder
  ├─ error state    → destructive banner "Router unavailable — <reason>"
  └─ RouterStatusCard (local component)
        ├─ snapshot == null  → Offline badge + "Router unavailable"
        └─ otherwise         → Online badge, hostname, firmware, kernel,
                               CPU usage, memory usage, storage usage,
                               storage mounts, diagnosis list,
                               recommendations list
```
- The card is collapsible via a chevron toggle (`useState`); it sits in a bar
  above the chat message list and never blocks sending messages.
- Reuses existing UI components only: `Badge`, `Skeleton` from
  `@/components/ui`; response types (`RouterSnapshotData`, `RouterFinding`,
  `RouterRecommendation`) mirror the backend `to_dict()` shapes (same as the
  dashboard).
- Badge variants match the dashboard mappings: severity `critical` →
  destructive, `warning` → outline, else secondary; priority `urgent` →
  destructive, `high` → outline, `medium` → secondary, `low` → default.
- The chat pipeline is untouched: the router-status refresh is fire-and-forget
  in `onSend`, so an unavailable router never interrupts a message.

## Files Changed
| File | Change |
| --- | --- |
| `frontend/app/chat/page.tsx` | Fetch and refresh router status (`GET /router/status`) on load and before every message; render a collapsible Router Status card above the chat with Online/Offline badge, hostname, firmware, kernel, CPU, memory, storage, diagnosis, and recommendations; degrade gracefully to "Router unavailable". |

## Tests Executed
- No affected tests: there are no frontend test files, and no backend files
  changed.

## Verification
- `npm run lint` passes.
- `npm run typecheck` passes.
- `npm run build` (production) succeeds; `/chat` compiles to a static route.
- Healthy snapshot renders the full status card; `snapshot: null` renders
  Offline + "Router unavailable" without throwing; fetch failures surface an
  error banner; loading renders a skeleton; collapsing/expanding the card works;
  chat still sends messages when the router is unavailable.
