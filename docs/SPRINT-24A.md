# Sprint 24A — End-to-End Router Pipeline Integration Tests

## Objective
Add a deterministic, end-to-end integration test suite covering the full router
pipeline with real components and mocked AI transports only:

```
Intent Detection → Router Manager → Tool Executor → Snapshot
    → Diagnosis → Recommendation → Router Context
    → System Prompt → Final Chat Response
```

Every scenario builds a deterministic `DeviceSnapshot`, registers a real
`RouterManager` over it (exactly like `app.main`), and asserts on the provider
request actually sent plus the API response. No production code changed; no new
features added.

## Scenario Coverage
| Scenario | Test |
| --- | --- |
| Healthy router | `test_healthy_router_chat_injects_context_without_findings`, `test_status_endpoint_healthy_router_full_pipeline` |
| Router unavailable | `test_chat_continues_when_router_unavailable`, `test_status_endpoint_unavailable_without_router` |
| Offline router | `test_offline_router_produces_connectivity_finding_and_recommendation` |
| High CPU | `test_high_cpu_chat_reports_finding_and_recommendation`, `test_status_endpoint_high_cpu_reports_diagnosis_and_recommendation` |
| High memory | `test_high_memory_chat_reports_finding_and_recommendation` |
| Missing WAN | `test_missing_wan_chat_reports_wan_and_wifi_findings` |
| Multiple findings | `test_multiple_findings_chat_recommendations_priority_ordered` |
| Non-router conversation | `test_non_router_conversation_skips_router_context` |
| Streaming response | `test_streaming_chat_emits_router_context_once_on_done` |
| RAG-enabled chat | `test_rag_chat_works_alongside_router_pipeline` |
| Cached router context | `test_cached_router_context_reuses_executor_results` |
| Router context disabled | `test_router_aware_false_disables_context`, `test_router_aware_true_with_non_router_message_skips_tool_layer` |

## Verification Guarantees
- Router Context appears only when appropriate: auto-detected router intent,
  populated snapshot, `router_aware` not `false`. Absent for non-router messages,
  unavailable routers, and disabled override.
- Recommendations match deterministic rules: severity→priority
  (critical→urgent, warning→high) and group merge (e.g. `rec-cpu`, `rec-wan`).
  The multi-finding test asserts strict priority ordering (urgent first, then high).
- Diagnosis matches the snapshot: threshold checks (CPU/memory 75/90%,
  storage 85/95%, load 1.0x/2.0x cores) verified against hand-built snapshots.
- The final system prompt sent to the provider contains the
  `### Router Context` / `### End Router Context` section when a context exists
  and is byte-identical to the plain prompt when it does not.
- Chat keeps working when the router is unavailable (reply still returned,
  `router_context` is `null`).
- Streaming is unchanged: tokens are the same, `router_context` appears exactly
  once, on the `done` event only.
- Cache behaviour is unchanged: the same session reuses tool results
  (`_CountingRouterTool` records exactly one `system` execution across two turns,
  cache hit ≥ 1).

## Files Changed
| File | Change |
| --- | --- |
| `tests/e2e/test_router_pipeline.py` | New suite: 16 tests exercising the full router pipeline over the chat + status endpoints with mocked AI transports. |

## Tests Executed
- `tests/e2e/test_router_pipeline.py` — 16 passed.
- Full router-related suite (chat, RAG chat, status API, diagnosis, recommendation,
  manager, snapshot, tool, executor, selector, registry, intent detector, context
  cache, action guard) — 167 passed.
- `test_router_api.py` has 3 pre-existing failures (`KeyError: 'connected'`) —
  they assert an old `connected` field on `/api/v1/router/status` that the current
  endpoint no longer returns. Unrelated to this sprint; left untouched.

## Verification
- `ruff check` passes on the new test file.
- `ruff format --check` passes (file already formatted).
- Tests were run with the repo's default command:
  `.venv/bin/python3 -m pytest tests/e2e/test_router_pipeline.py -o addopts="" -q`.
