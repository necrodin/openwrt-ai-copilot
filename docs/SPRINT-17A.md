# Sprint 17A — Safe Router Actions

## Objective
Introduce a safety layer before any router write operation. A `RouterActionGuard`
evaluates every requested router action and returns an `ActionDecision`
(`allow` / `require_confirmation` / `deny`). `RouterToolExecutor` consults the
guard before executing any write-capable tool. The project currently has
read-only tools only, so behavior is unchanged and no write operation is
introduced.

## Architecture
```
RouterToolExecutor.execute(requests)
  └─ for each request name:
       └─ RouterActionGuard.evaluate(name) → ActionDecision
             ├─ decision: allow | require_confirmation | deny
             ├─ risk: low | medium | high | critical
             ├─ reason
             ├─ confirmation_required
             └─ action_name
       ├─ decision == allow          → run registered tool (read-only path, unchanged)
       ├─ decision == require_confirmation → blocked; decision recorded in result
       └─ decision == deny           → blocked; decision recorded in result
```

- `RouterActionGuard` is purely declarative and deterministic: no LLM, no
  external APIs, no tool execution.
- Read-only actions (anything not in the disruptive/dangerous lists) are always
  `allow` with `low` risk.
- Potentially disruptive actions (`reboot`, `restart service`,
  `reload firewall`, `restart network`, `wifi disable`, `interface down`) return
  `require_confirmation` with `high` risk.
- Dangerous actions (`factory reset`, `firmware upgrade`, `package removal`,
  `delete configuration`, `filesystem erase`) return `deny` with `critical`
  risk.
- `RouterToolExecutor` takes an optional `guard` (defaults to a new
  `RouterActionGuard`). Non-`allow` requests are never executed; the
  `ActionDecision` is recorded in the result (`ok=False`, decision in
  `result`, reason in `error`). Read-only requests resolve and run exactly as
  before.

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/services/router_action_guard.py` | **new** — `ActionDecision`, `RouterActionGuard` (read-only/disruptive/dangerous rules). |
| `backend/app/services/router_tool_executor.py` | Consult the guard before executing each request; block non-`allow` actions without executing. |
| `tests/unit/test_router_action_guard.py` | **new** — allow/confirm/deny rules, risk/confirmation fields, determinism. |
| `tests/unit/test_router_tool_executor.py` | Block write and dangerous actions even when registered; read-only behavior unchanged. |

## Tests Executed
```
.venv/bin/python3 -m pytest tests/unit/test_router_action_guard.py \
  tests/unit/test_router_tool_executor.py -o addopts="" -q
13 passed
```
```
.venv/bin/python3 -m pytest tests/unit/test_router_snapshot.py \
  tests/unit/test_router_diagnosis.py tests/unit/test_router_recommendation.py \
  tests/unit/test_router_context_cache.py tests/unit/test_chat_api.py -o addopts="" -q
58 passed
```

## Verification
- Read-only action names produce `allow` / `low` / no confirmation.
- Every disruptive action returns `require_confirmation` / `high` / requires
  confirmation.
- Every dangerous action returns `deny` / `critical` / no confirmation.
- `ActionDecision.to_dict()` exposes all fields; evaluations are deterministic.
- `RouterToolExecutor` never runs a disruptive or dangerous tool even when such
  a tool is registered; the guard decision is recorded instead.
- Read-only behavior is unchanged: registered read-only tools still execute and
  return `ok=True`; snapshot/diagnosis/recommendation/chat suites still pass.
- No Router Agent protocol changes, no new write operations, no external APIs,
  no LLM, no duplicated logic.
- Frontend build not run: no frontend files changed.
