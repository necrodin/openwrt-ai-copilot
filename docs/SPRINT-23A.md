# Sprint 23A — AI Uses Router Context in Final Answers

## Objective
Make the assistant actually use the router context when answering. The router
pipeline (generate, cache, diagnose, recommend, expose, render) is complete;
this sprint wires the context into the model prompt with an explicit instruction
to prefer factual router values over model assumptions.

## Architecture
The change is confined to `ChatService.compose()` in `chat_service.py`:

```
system = self.system_prompt()
if router_context:
    system = (
        f"{system}\n\n### Router Context\n{router_context}\n"
        "### End Router Context\n\n"
        "If Router Context exists, prefer factual values from it over "
        "model assumptions.\n"
        "Never invent router values.\n"
        "If Router Context is empty, answer normally."
    )
```

- When `router_context` is present, it is placed inside a dedicated
  `### Router Context ... ### End Router Context` section followed immediately
  by the grounding instruction.
- When `router_context` is empty/absent, the system prompt is byte-for-byte
  unchanged (existing chat behaviour is preserved).
- No changes to RouterManager, RouterTools, RouterExecutor, IntentDetector, or
  the Snapshot/Diagnosis/Recommendation engines. No new APIs, no frontend
  changes, no persistence, no refactoring.

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/services/chat_service.py` | `compose()` wraps `router_context` in a `### Router Context / ### End Router Context` section and appends the "prefer factual values / never invent router values" instruction. |
| `tests/unit/test_chat_api.py` | Update marker assertions to the new section headers; add `test_compose_injects_router_context_section` and `test_compose_without_router_context_keeps_prompt_unchanged`. |

## Tests Executed
- `tests/unit/test_chat_api.py` + `tests/unit/test_chat_api_rag.py` — 24 passed.
- New tests prove: router context is injected into the system prompt inside the
  dedicated section; no context leaves the prompt unchanged; existing chat
  behaviour (auto-detect, streaming, RAG, executor, caching) is unchanged.

## Verification
- `ruff check` passes on both modified files.
- `ruff format --check` passes (both files already formatted).
