# Sprint 24B — Release Candidate Stabilization

## Objective
Stabilize the Router pipeline for v1.0 by removing an API inconsistency, fixing
the legacy router-status test failures, and locking down the public
`GET /router/status` contract with regression tests.

## Root Cause
`GET /api/v1/router/status` was registered **twice** with two different
contracts:

| Module | Contract | Status |
| --- | --- | --- |
| `backend/app/api/v1/router_status.py` | `{snapshot, diagnosis, recommendations}` | Included first → actually served |
| `backend/app/api/v1/router.py` | `{connected, source, device_id, last_snapshot_at, sequence, error, server_time}` | Included second → shadowed, never served |

The legacy tests in `tests/unit/test_router_api.py` asserted the second
contract (`KeyError: 'connected'`). The tests were not wrong: the legacy
contract was still defined but unreachable because the newer snapshot-based
endpoint won the duplicate registration. This was an implementation
inconsistency, not just stale tests.

## Fix (backward compatible)
- **Merged the contract into a single superset endpoint.** `router_status.py`
  now returns the preserved connection-state fields *plus* the derived
  snapshot/diagnosis/recommendations:

  ```
  {connected, source, device_id, last_snapshot_at, sequence, error, server_time,
   snapshot, diagnosis, recommendations}
  ```

  The connection-state fields come from the live snapshot feed
  (`snapshot_service.latest()`), so `connected`/`error` correctly reflect a
  disconnected feed even while the last good snapshot is retained and still
  served. Existing clients that read either the legacy fields or the derived
  fields keep working unchanged (the frontend destructures
  `{snapshot, diagnosis, recommendations}` and ignores the rest).
- **Removed the dead duplicate** `/router/status` handler from `router.py`
  (only the module docstring reference remains, pointing at `router_status.py`).
  `GET /router/info` and `GET /router/context` are untouched.
- No changes to RouterManager, RouterExecutor, RouterTool, Diagnosis,
  Recommendation, Intent Detection, Prompt Builder, or the frontend. No new
  endpoints, no new features.

## Contract Verification
- Response schema: one coherent JSON object; legacy fields always present.
- Field names: unchanged from both historical contracts (`connected`, `source`,
  `device_id`, `last_snapshot_at`, `sequence`, `error`, `server_time`, plus
  `snapshot`, `diagnosis`, `recommendations`).
- Optional fields / null handling: `snapshot` is `null` when the router is
  unavailable; `last_snapshot_at` and `error` are `null` when absent;
  `diagnosis`/`recommendations` are empty arrays.
- States:
  - Healthy — `connected: true`, populated snapshot, empty findings.
  - Disconnected — `connected: false`, `error` set, retained snapshot still
    served and diagnosed.
  - Unavailable — `connected: false`, `snapshot: null`, empty arrays, HTTP 200.
  - Malformed snapshot — tolerated (HTTP 200), diagnosed as `Unknown router
    values` / `rec-data-quality` instead of crashing.
  - Empty snapshot — treated as unavailable (`snapshot: null`).

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/api/v1/router_status.py` | Merge legacy connection-state fields into the status response; keep the derived snapshot/diagnosis/recommendations. |
| `backend/app/api/v1/router.py` | Remove the shadowed duplicate `/router/status` handler and now-unused `datetime` import; note the merged endpoint in the docstring. |
| `tests/unit/test_router_status_api.py` | Add feed stub, `_assert_unavailable` helper, merged-contract assertions, and regression tests for healthy/disconnected/unavailable/malformed/backward-compat states. |
| `tests/e2e/test_router_pipeline.py` | Update status assertions to the merged contract; add `connected`/`sequence`/`error` checks. |

The three legacy status tests in `tests/unit/test_router_api.py` were **not
modified** — they now pass unchanged, proving backward compatibility of the
preserved fields.

## Regression Tests Added
- `test_disconnected_router_reports_error_with_retained_snapshot`
- `test_malformed_snapshot_is_tolerated`
- `test_legacy_fields_coexist_with_derived_status`
- Merged-contract assertions in `test_healthy_router`, `test_unavailable_router`,
  `test_empty_snapshot_is_unavailable`.

## Duplicated Assertions
No duplicated assertions were removed: the legacy tests (`test_router_api.py`)
cover the preserved connection-state fields, while `test_router_status_api.py`
covers the derived fields — complementary coverage, not duplicates.

## Tests Executed
- Full router-related suite (status API, legacy router API, chat, RAG chat,
  diagnosis, recommendation, manager, snapshot, tool, executor, selector,
  registry, intent detector, context cache, action guard, e2e pipeline) —
  173 passed.
- Full project suite — 734 passed (previously 731 passed / 3 failed).
- Command: `.venv/bin/python3 -m pytest -o addopts="" -q`.

## Verification
- `ruff check` passes on all modified files.
- `ruff format --check` passes on all modified files.
