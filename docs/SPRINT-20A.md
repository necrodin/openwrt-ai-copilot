# Sprint 20A — Complete the Router-Aware Chat Pipeline

## Objective
Complete the first end-to-end AI experience: when a user asks a router-related
question from the chat UI, the backend automatically detects router intent,
collects router status, generates diagnosis and recommendations, injects router
context, and lets the LLM produce the final answer. All components already
exist; this sprint verifies and documents the wiring.

## Architecture
```
User message → POST /api/v1/chat
  └─ chat.py._router_context_markdown
       └─ ChatService.router_context_markdown
            ├─ _resolve_router(router_id)                  (Router Manager)
            ├─ router.detector.classify(message)           (Intent Detector)
            ├─ router.selector.select(message)             (tool selection)
            ├─ router.snapshot_service.build(...)          (Snapshot)
            ├─ render_markdown(snapshot, intents)          (Router Context)
            ├─ RouterDiagnosisEngine.diagnose(snapshot)    (Diagnosis)
            ├─ RouterRecommendationEngine.generate(...)    (Recommendations)
            └─ returns combined markdown
  ├─ ChatService.compose(router_context=...)               (ChatService)
  └─ ChatService.complete(provider, request)               (LLM)
```
- Router intent is auto-detected: with `router_aware=None` the
  `RouterIntentDetector` classifies the message; non-router messages skip the
  tool layer entirely, router messages run the full pipeline.
- The snapshot is built once and diagnosis/recommendations are derived from it
  (no duplicate tool execution).
- Router context (snapshot markdown + diagnosis + recommendations) is appended
  to the system prompt via `compose`, then handed to the LLM.
- When the router is unavailable (`_resolve_router` → `None`, build failure, or
  unrenderable snapshot), `router_context_markdown` returns `None` and the chat
  continues normally — no exceptions, no HTTP errors.

## Files Changed
| File | Change |
| --- | --- |
| `docs/SPRINT-20A.md` | **new** — documents the verified end-to-end pipeline. |

No backend or frontend code changed: the router-aware chat pipeline was already
wired together by previous sprints and is confirmed complete.

## Tests Executed
```
.venv/bin/python3 -m pytest tests/unit/test_chat_api.py \
  tests/unit/test_chat_api_rag.py -o addopts="" -q
22 passed
```

## Verification
- Non-streaming chat auto-injects router context (snapshot, diagnosis, and
  recommendations) for router-related messages; non-router messages skip the
  tool layer.
- Router-aware requests execute through the executor and reuse cached results;
  unavailable router state still yields a normal 200 chat reply.
- Streaming chat mirrors the same pipeline.
- Frontend production build succeeds.
- No RouterAgent or Router Tool changes; no duplicated logic.
