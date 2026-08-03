# Sprint 18A — Expose Router Status Through a REST Endpoint

## Objective
Expose the router's live state, diagnosis, and recommendations through a single
REST endpoint. `GET /router/status` builds one `RouterSnapshot` from the
registered router and derives diagnosis and recommendations from that same
snapshot — no duplicated tool execution, no direct RouterAgent access, no
markdown. JSON only.

## Architecture
```
GET /api/v1/router/status
  └─ app.api.v1.router_status
       ├─ router_manager.default                          (RegisteredRouter)
       ├─ router.snapshot_service.build(executor, None, all sections)  → RouterSnapshot
       ├─ RouterDiagnosisEngine.diagnose(snapshot)        → DiagnosisReport
       ├─ RouterRecommendationEngine.generate(diagnosis)  → RecommendationReport
       └─ response: {snapshot, diagnosis, recommendations}
```
- Registered before the existing v1 router endpoints in `app/api/router.py` so
  the new status contract takes precedence at `GET /router/status`.
- Reuses `RouterSnapshot`, `RouterDiagnosisEngine`, and
  `RouterRecommendationEngine`; no diagnosis or recommendation logic is
  duplicated.
- One snapshot is built and everything is derived from it; tools are never
  executed twice.
- Unavailable router (no default router, build failure, or an unpopulated
  snapshot) returns HTTP 200 with `snapshot=null`, `diagnosis=[]`,
  `recommendations=[]`.

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/api/v1/router_status.py` | **new** — `GET /router/status` endpoint returning `{snapshot, diagnosis, recommendations}`. |
| `backend/app/api/router.py` | Register the new router ahead of the existing v1 endpoints. |
| `tests/unit/test_router_status_api.py` | **new** — healthy router, unavailable router, empty snapshot, diagnosis included, recommendations included. |

## Tests Executed
```
.venv/bin/python3 -m pytest tests/unit/test_router_status_api.py -o addopts="" -q
5 passed
```

## Verification
- Healthy router returns the snapshot plus empty diagnosis/recommendations.
- Unavailable router and empty snapshot return HTTP 200 with `null`/empty
  arrays.
- High memory and high CPU snapshots produce the expected diagnosis findings
  and `rec-cpu` urgent recommendation respectively.
- Response is pure JSON; no markdown anywhere.
- No RouterAgent protocol changes, no duplicated diagnosis/recommendation
  logic, no double tool execution.
- Frontend build not run: no frontend files changed.
