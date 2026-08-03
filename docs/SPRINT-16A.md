# Sprint 16A — AI Router Diagnosis

## Objective
Introduce a deterministic diagnosis engine that analyzes an existing
`RouterSnapshot` and produces structured health findings, with `ChatService`
automatically appending the diagnosis to router context whenever a snapshot
exists. No LLM reasoning and no external APIs: findings are derived from fixed
rules over the snapshot data.

## Architecture
```
ChatService.router_context_markdown(message, router_aware, session_id, router_id)
  ├─ RegisteredRouter.snapshot_service.build(executor, session_id, requests)
  │     └─ RouterSnapshot  (system, cpu, memory, storage, network, wifi)
  ├─ RegisteredRouter.snapshot_service.render_markdown(snapshot, intents) → markdown
  └─ RouterDiagnosisEngine.diagnose(snapshot, router_id)
        ├─ checks: offline, cpu, memory, storage, high load,
        │          missing WAN, missing WiFi, unknown values
        └─ DiagnosisReport.render_markdown()  → appended to router context
```

- `RouterDiagnosisEngine` analyzes the **already-built** `RouterSnapshot`; it
  never executes Router Tools and never touches the network.
- Findings are deterministic and threshold-based:
  - CPU utilization ≥ 75% warning, ≥ 90% critical.
  - Memory utilization ≥ 75% warning, ≥ 90% critical.
  - Storage utilization ≥ 85% warning, ≥ 95% critical (per mountpoint).
  - Load average ≥ core count warning, ≥ 2× core count critical.
  - Offline router (no populated sections) critical.
  - No WAN interface among network interfaces → warning.
  - No WiFi radios → warning.
  - Missing/unknown values → info.
- Each `Finding` carries `severity` (`info`/`warning`/`critical`), `category`,
  `title`, `description`, and `recommendation`; a `DiagnosisReport` aggregates
  findings and can serialize to dict or render to markdown.
- `ChatService` accepts an optional `diagnosis_engine` (defaulting to a new
  `RouterDiagnosisEngine`) and appends the rendered report to router context
  after the snapshot markdown. When the snapshot produces no markdown, router
  context still returns `None` (unchanged behaviour).

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/services/router_diagnosis.py` | **new** — `Finding`, `DiagnosisReport`, `RouterDiagnosisEngine` (eight deterministic checks). |
| `backend/app/services/chat_service.py` | Accept `diagnosis_engine`; run diagnosis on the built snapshot and append its markdown to router context. |
| `tests/unit/test_router_diagnosis.py` | **new** — findings, thresholds, structure, markdown/dict output for every check. |

## Tests Executed
```
.venv/bin/python3 -m pytest tests/unit/test_router_diagnosis.py \
  tests/unit/test_chat_api.py tests/unit/test_router_intent_detector.py \
  tests/unit/test_router_context_cache.py tests/unit/test_router_snapshot.py \
  tests/unit/test_router_manager.py -o addopts="" -q
60 passed
```

## Lint
```
.venv/bin/python3 -m ruff check backend/app/services/router_diagnosis.py \
  backend/app/services/chat_service.py tests/unit/test_router_diagnosis.py
.venv/bin/python3 -m ruff format --check <same files>
All checks passed
```

## Verification
- Healthy snapshots produce no findings; offline routers, high utilization,
  missing WAN/WiFi, and unknown values each yield the expected severity and
  title.
- `DiagnosisReport` serializes to dict and renders markdown (or `None` when
  there are no findings).
- Router-aware chat responses now include a `## Router Diagnosis` section when
  the snapshot warrants findings; unavailable router data still yields no
  router context, preserving prior behaviour.
- No Router Agent / Router Tool / RouterManager / RouterSnapshot changes; no
  duplicated logic; no LLM or external API involvement.
- Frontend build not run: no frontend files changed.
