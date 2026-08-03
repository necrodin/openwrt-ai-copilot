# Sprint 16B — AI Recommendation Engine

## Objective
Generate actionable, prioritized recommendations from an existing
`DiagnosisReport`, and have `ChatService` append them to router context after
the diagnosis section whenever a `DiagnosisReport` exists. Deterministic — no
LLM, no external APIs, no additional router analysis.

## Architecture
```
ChatService.router_context_markdown(...)
  ├─ snapshot_service.render_markdown(snapshot, intents)          → markdown
  ├─ RouterDiagnosisEngine.diagnose(snapshot, router_id)          → DiagnosisReport
  │     └─ render_markdown()  (## Router Diagnosis)
  └─ RouterRecommendationEngine.generate(diagnosis)               → RecommendationReport
        ├─ findings grouped by rule template (merge related findings)
        ├─ priority from highest finding severity (urgent/high/medium)
        └─ render_markdown()  (## Recommendations, appended after diagnosis)
```

- `RouterRecommendationEngine` consumes only the `DiagnosisReport` it is given;
  it never performs router analysis and never executes Router Tools.
- Findings are grouped into rule templates by title. Related findings merge
  into a single recommendation (e.g. CPU + high load → one CPU recommendation;
  multiple storage findings → one storage recommendation).
- Priority is derived deterministically from the highest finding severity in
  the group: `critical` → `urgent`, `warning` → `high`, `info` → `medium`.
- Each `Recommendation` carries `id`, `priority`, `category`, `title`,
  `description`, `action`, and `impact`; `RecommendationReport` aggregates them
  and serializes to dict or renders markdown. Unknown finding titles fall back
  to a generic per-finding recommendation.
- Recommendations are deterministic: stable ids, merged descriptions, sorted by
  priority (then id) for stable output ordering.
- `ChatService` accepts an optional `recommendation_engine` (defaulting to a new
  `RouterRecommendationEngine`) and appends the rendered report after the
  diagnosis section only when findings exist.

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/services/router_recommendation.py` | **new** — `Recommendation`, `RecommendationReport`, `RouterRecommendationEngine` (rule templates, merging, priority mapping). |
| `backend/app/services/chat_service.py` | Accept `recommendation_engine`; generate recommendations from the diagnosis and append their markdown after the diagnosis section. |
| `tests/unit/test_router_recommendation.py` | **new** — structure, merging, priority mapping, sorting, dict/markdown output, generic fallback. |

## Tests Executed
```
.venv/bin/python3 -m pytest tests/unit/test_router_recommendation.py \
  tests/unit/test_chat_api.py -o addopts="" -q
28 passed
```

## Verification
- Empty diagnosis produces no recommendations and no markdown.
- Offline finding maps to an `urgent` connectivity recommendation; severity to
  priority mapping verified for all three severities.
- Related findings merge into a single recommendation (CPU + high load,
  multiple storage findings); priority reflects the highest severity.
- Recommendations are sorted urgent → high → medium with stable ordering.
- Unknown finding titles fall back to a deterministic generic recommendation.
- `RecommendationReport`/`Recommendation` serialize to dict and render markdown.
- Router-aware chat responses include `## Recommendations` after
  `## Router Diagnosis`; unavailable router data still yields no router context.
- No Router Agent / Router Tool / RouterSnapshot / RouterDiagnosisEngine rule
  changes; no duplicated diagnosis logic.
- Frontend build not run: no frontend files changed.
