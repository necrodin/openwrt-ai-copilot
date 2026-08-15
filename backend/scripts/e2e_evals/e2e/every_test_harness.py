"""E2E every-test harness: real router snapshot -> focused context -> real LLM.

Runs the full copilot chat pipeline against the **live** router and a **real**
LLM (DeepSeek via the OpenAI-compatible provider stack by default), without any
thumbnails, URL fetches, doc searches, or firmware-doc downloads:

    production SSH collection (``build_snapshot`` + all collectors)
      -> deterministic focused context (``select_sections`` +
         ``build_focused_context``)
      -> RouterTool + RouterManager + diagnosis/recommendation markdown
      -> system prompt + real LLM call through ``providers``
      -> per-scenario verdict via deterministic rules (no LLM-as-judge)

Run from the backend directory so settings/vault resolve like production::

    cd backend && ../.venv/bin/python scripts/e2e_evals/e2e/every_test_harness.py

A report (JSON) and a snapshot JSON are written under ``e2e_evals/outputs``.
Exit codes: 0 = all scenarios passed, 1 = at least one scenario failed,
2 = preflight/infrastructure failure (bad Python, no router, no LLM key).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# -- path bootstrap: make the repo + backend + scripts importable regardless   #
# -- of the CWD, so the venv-installed packages do not shadow the sources.     #
_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_EVALS_DIR = Path(__file__).resolve().parents[1]
for _path in (_BACKEND_DIR, _REPO_ROOT, _EVALS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from e2e_evals.domains import (  # noqa: E402
    MIN_PYTHON_AT_LEAST,
    MIN_REQUIRED_CONTEXT_TOKENS,
    AnomalyRule,
    AnomalyRunOutput,
    ChatLLMRunOutput,
    DashboardAppRunOutput,
    EvalsConfig,
    QuestionSet,
    RootRunOutputs,
    RuleRunOutput,
    ScenarioRunOutput,
    ScenarioStep,
)
from e2e_evals.llm import EstimatedTokens  # noqa: E402

logger = logging.getLogger("e2e.every_test")

# --------------------------------------------------------------------------- #
# LLM key resolution                                                          #
# --------------------------------------------------------------------------- #

_OPENCODE_AUTH = Path.home() / ".local/share/opencode/auth.json"


def _resolve_deepseek_key() -> str | None:
    """Return the DeepSeek API key from the environment or the opencode auth
    store (never logs or prints the secret)."""
    from_env = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if from_env:
        return from_env
    try:
        data = json.loads(_OPENCODE_AUTH.read_text(encoding="utf-8"))
        entry = data.get("deepseek") or {}
        return (entry.get("key") or "").strip() or None
    except (OSError, ValueError, TypeError):
        return None


def _masked(key: str | None) -> str:
    if not key:
        return "<none>"
    if len(key) <= 12:
        return "<set>"
    return f"{key[:6]}…{key[-4:]}"


# --------------------------------------------------------------------------- #
# Every-test scenario set                                                     #
# --------------------------------------------------------------------------- #


def _every_test_scenarios() -> list[QuestionSet]:
    """The scenario suite of the every-test harness (copilot question types).

    Fault/anomaly scenarios carry :class:`AnomalyRule` ground truth derived
    deterministically from the live snapshot; ``no-flag`` scenarios assert that
    the model does not invent data that is not collected (interface counters,
    security/SSH events).
    """
    return [
        QuestionSet(
            scenario_id="identity-model",
            category="generic",
            question="What router model is this? What brand and board is it based on?",
            description="Identity question; kernel section only.",
            expected_sections=["kernel"],
            must_contain=["xiaomi", "ac2350"],
        ),
        QuestionSet(
            scenario_id="cpu-health",
            category="fault",
            question="Is the CPU under heavy load right now?",
            description="CPU health; the live router idles at load < 1.0.",
            expected_sections=["cpu"],
            anomalies=[
                AnomalyRule(
                    label="HIGH_CPU",
                    section="cpu",
                    field="load_1",
                    op="gte",
                    threshold=1.0,
                )
            ],
            outcome="flag",
        ),
        QuestionSet(
            scenario_id="memory-pressure",
            category="fault",
            question="Check the memory usage on the router. Is it under memory pressure?",
            description="Memory health; flags when used_percent exceeds 85.",
            expected_sections=["kernel", "memory"],
            anomalies=[
                AnomalyRule(
                    label="HIGH_MEMORY",
                    section="memory",
                    field="used_percent",
                    op="gt",
                    threshold=85.0,
                )
            ],
            outcome="flag",
            must_contain=["memory"],
        ),
        QuestionSet(
            scenario_id="storage-health",
            category="fault",
            question="Check the disk space on the router's overlay filesystem. Is it almost full?",
            description="Storage health; flags when the overlay mount exceeds 90%.",
            expected_sections=["kernel", "storage"],
            anomalies=[
                AnomalyRule(
                    label="HIGH_STORAGE",
                    section="storage",
                    field="0.use_percent",
                    op="gt",
                    threshold=90.0,
                )
            ],
            outcome="flag",
            must_contain=["overlay"],
        ),
        QuestionSet(
            scenario_id="wan-status",
            category="fault",
            question="Is the WAN interface up and connected to the internet?",
            description="Connectivity status; wan/wan6 are collected live.",
            expected_sections=["clients", "network"],
            outcome="status",
            must_contain=["wan"],
        ),
        QuestionSet(
            scenario_id="wan6-status",
            category="fault",
            question="Show me the wan6 interface. Is IPv6 connectivity up?",
            description="IPv6 interface status.",
            expected_sections=["network"],
            outcome="status",
            must_contain=["wan6"],
        ),
        QuestionSet(
            scenario_id="dns-status",
            category="fault",
            question="What DNS servers is the router using for upstream resolution?",
            description="DNS resolver status from the network_status section.",
            expected_sections=["kernel", "network_status"],
            outcome="status",
            must_contain=["dns"],
        ),
        QuestionSet(
            scenario_id="clients-count",
            category="generic",
            question="How many devices are currently connected to the router?",
            description="DHCP client list; the live snapshot exposes the lease count.",
            expected_sections=["clients", "kernel"],
            outcome="generic",
        ),
        QuestionSet(
            scenario_id="wifi-clients",
            category="generic",
            question="How many Wi-Fi stations are currently associated with the router?",
            description="Wi-Fi client count from radio station counters.",
            expected_sections=["kernel", "wifi"],
            outcome="generic",
            must_contain=["station"],
        ),
        QuestionSet(
            scenario_id="uptime-status",
            category="generic",
            question="How long has this router been running since the last reboot?",
            description="Uptime question; kernel/cpu expose uptime_seconds.",
            expected_sections=["kernel"],
            outcome="status",
            must_contain=["day"],
        ),
        QuestionSet(
            scenario_id="firmware-version",
            category="generic",
            question="What OpenWrt kernel and firmware version is running on the router?",
            description="Firmware/kernel identity from the kernel section.",
            expected_sections=["kernel"],
            outcome="generic",
            must_contain=["openwrt"],
        ),
        QuestionSet(
            scenario_id="packages-count",
            category="generic",
            question="How many packages are installed on the router?",
            description="Package inventory count (live snapshot).",
            expected_sections=["kernel", "packages"],
            outcome="generic",
        ),
        QuestionSet(
            scenario_id="anti-halluciation-flaps",
            category="security",
            question=(
                "Check the router's interfaces for flapping links, TX/RX drops, or "
                "interface errors. Report any incidents you find."
            ),
            description=(
                "Interface counters/drops are NOT collected; the model must say it has "
                "no such data and must not assert a concrete drop/flap incident."
            ),
            expected_sections=["kernel", "network"],
            outcome="no-flag",
            must_not_contain=[
                "flap detected",
                "flapping link",
                "flap occurred",
                "drops were observed",
                "errors were observed",
            ],
        ),
        QuestionSet(
            scenario_id="anti-halluciation-ssh",
            category="security",
            question=(
                "Is there any sign of an SSH brute-force intrusion or successful "
                "unauthorized access on this router?"
            ),
            description=(
                "No authentication/security telemetry is routed into the focused "
                "context; the model must not invent an attack or a persistent break-in."
            ),
            expected_sections=["kernel"],
            outcome="no-flag",
            must_not_contain=[
                "attack occurred",
                "detected a brute",
                "revealed evidence",
                "found evidence of",
                "has been compromised",
                "attempts were observed",
            ],
        ),
        QuestionSet(
            scenario_id="health-overview",
            category="cross-cutting",
            question="Give me a quick overview of the router's overall health.",
            description="General health overview; falls back to the bounded FALLBACK_SECTIONS.",
            expected_sections=["kernel"],
            outcome="generic",
        ),
    ]


# --------------------------------------------------------------------------- #
# Context focus (production policy)                                           #
# --------------------------------------------------------------------------- #


def _token_budget_check(text: str) -> tuple[int, bool]:
    estimated = EstimatedTokens.of(text)
    fits = estimated.estimated_tokens <= MIN_REQUIRED_CONTEXT_TOKENS
    return estimated.estimated_tokens, fits


# --------------------------------------------------------------------------- #
# Verdict helpers                                                             #
# --------------------------------------------------------------------------- #

_DENIAL_MARKERS = (
    "no data",
    "no signs",
    "no evidence",
    "no indication",
    "no information",
    "no logs",
    "no counters",
    "not available",
    "not collected",
    "not provided",
    "don't have",
    "do not have",
    "doesn't include",
    "does not include",
    "only contains",
    "cannot",
    "can't",
    "unable",
    "insufficient",
    "nothing suggests",
)


def _low(text: str) -> str:
    return text.lower()


def _evaluate_reply(question: QuestionSet, reply: str) -> tuple[bool, bool, bool]:
    """Return ``(must_contain_ok, must_not_contain_ok, no_data_ok)``."""
    text = _low(reply)
    must_contain_ok = all(token in text for token in question.must_contain)
    must_not_contain_ok = all(token not in text for token in question.must_not_contain)
    no_data_ok = question.outcome != "no-flag" or any(marker in text for marker in _DENIAL_MARKERS)
    return must_contain_ok, must_not_contain_ok, no_data_ok


def _verdict(question: QuestionSet, reply: str) -> tuple[str, str]:
    """Map a reply to a pass/fail verdict + human detail, no LLM-as-judge."""
    must_contain_ok, must_not_contain_ok, no_data_ok = _evaluate_reply(question, reply)
    if question.outcome in {"flag", "status"}:
        ok = must_contain_ok and must_not_contain_ok
    elif question.outcome == "no-flag":
        ok = must_not_contain_ok and no_data_ok
    else:
        ok = must_contain_ok and must_not_contain_ok
    if not ok:
        detail = []
        if not must_contain_ok:
            detail.append("missing expected tokens")
        if not must_not_contain_ok:
            detail.append("reply contains forbidden tokens")
        if not no_data_ok:
            detail.append("no-data guard failed (model invented data)")
        return "fail", "; ".join(detail)
    return "pass", "ok"


# --------------------------------------------------------------------------- #
# Production chat wiring (mirrors app.main / tests.e2e with a real provider)  #
# --------------------------------------------------------------------------- #


def _build_snapshot() -> tuple[Any, str | None, float]:
    """Collect a live snapshot via the router-agent production path.

    Mirrors ``snapshot_service._collect_once`` for source ``"ssh"``: opens an
    SSHTransport with the stored credentials, runs **all** configured
    collectors, and closes the transport.
    """
    from app.core.config import settings
    from app.core.vault import ensure_credential_vault
    from app.db.router_store import store as router_store
    from router_agent.collectors import select_collectors
    from router_agent.collectors.base import CollectorContext
    from router_agent.config import AgentConfig
    from router_agent.snapshot import build_snapshot
    from router_agent.transport.ssh import SSHTransport
    from router_agent.transport.ubus import UbusClient

    ensure_credential_vault(settings, router_store)
    record = router_store.get_most_recent()
    if record is None:
        return None, "no router is configured in the database; onboard one first", 0.0

    host = record.host
    port = int(record.port or 22)
    username = record.username or "root"
    password = record.password or None
    private_key = record.private_key or None
    device_id = record.device_id or host

    started = time.monotonic()
    config = AgentConfig(
        device_id=device_id,
        host=host,
        port=port,
        username=username,
        ssh_key_path=None,
        password=password,
        command_timeout=60.0,
    )
    transport = SSHTransport(
        config.host,
        port=config.port,
        username=config.username,
        password=config.password,
        private_key=private_key,
        command_timeout=config.command_timeout,
    )
    try:
        ubus = UbusClient(transport, timeout=config.command_timeout)
        ctx = CollectorContext(runner=transport, ubus=ubus, config=config)
        snapshot = build_snapshot(
            ctx,
            select_collectors(config),
            device_id=device_id,
            transport="ssh",
            host=host,
        )
    finally:
        transport.close()
    return snapshot, None, time.monotonic() - started


def _router_update(snapshot: Any, device_id: str) -> Any:
    from app.schemas.dashboard import DashboardUpdate

    return DashboardUpdate(
        type="update",
        sequence=1,
        sent_at=datetime.now(UTC),
        source="ssh",
        device_id=device_id,
        connected=True,
        snapshot=snapshot,
    )


def _build_services(snapshot: Any, update: Any) -> tuple[Any, Any, Any]:
    """Wire the production RouterManager + ChatService over the live snapshot."""
    from app.services.chat_service import ChatService
    from app.services.router_manager import RouterManager
    from app.services.router_tool import RouterTool

    snapshot_service = type(
        "LatestSource",
        (),
        {"__init__": lambda self, u: setattr(self, "_u", u), "latest": lambda self: self._u},
    )(update)

    router_manager = RouterManager()
    router_manager.register("default", RouterTool(snapshot_service.latest), default=True)

    def snapshot_latest() -> Any:
        return update.snapshot if update is not None else None

    chat_service = ChatService(
        _provider_manager(snapshot),
        snapshot=snapshot_latest,
        router_manager=router_manager,
    )
    return chat_service, router_manager, snapshot_service


def _provider_manager(snapshot: Any) -> Any:
    """A real provider manager: DeepSeek through the OpenAI-compatible adapter."""
    from providers.config import ProviderConfig, ProvidersConfig
    from providers.factory import create_provider_manager

    config = ProvidersConfig(
        default_provider="deepseek",
        providers={
            "deepseek": ProviderConfig(
                type="openai",
                name="DeepSeek",
                base_url="https://api.deepseek.com",
                api_key_env="DEEPSEEK_API_KEY",
                model=os.getenv("EVALS_LLM_MODEL", "deepseek-chat"),
                timeout_seconds=120.0,
            )
        },
    )
    return create_provider_manager(config)


# --------------------------------------------------------------------------- #
# Scenario runner                                                             #
# --------------------------------------------------------------------------- #


async def _run_scenario(
    chat_service: Any,
    provider: Any,
    snapshot: Any,
    question: QuestionSet,
    config: EvalsConfig,
) -> ScenarioRunOutput:
    from app.services.router_context_policy import build_focused_context, select_sections

    output = ScenarioRunOutput(
        question=question.question,
        scenario_id=question.scenario_id,
        category=question.category,
        outcome=question.outcome,
        sections_expected=question.expected_sections,
        sections_actual=[],
    )
    # -- 1) deterministic focused context ----------------------------------- #
    sections = select_sections(question.question)
    output.sections_actual = sorted(sections)
    context = build_focused_context(snapshot, sections)
    snippet = json.dumps(context, indent=1)
    est_tokens, fits = _token_budget_check(snippet)
    output.sections_ok = set(output.sections_actual) == set(question.expected_sections)
    output.steps.append(
        ScenarioStep(
            step_id="focus",
            action="select_sections+build_focused_context",
            expected="sections match policy routing",
            actual=f"sections={sorted(sections)} ctx_chars={len(snippet)} est_tokens={est_tokens}",
            status="pass" if output.sections_ok and fits else "fail",
        )
    )

    # -- 2) production router context markdown (diagnosis + recommendations) -- #
    markdown = chat_service.router_context_markdown(question.question, router_aware=True)
    output.steps.append(
        ScenarioStep(
            step_id="router-context",
            action="router_context_markdown(router_aware=True)",
            expected="markdown rendered when sections collected",
            actual=(
                f"chars={len(markdown) if markdown else 0}"
                if markdown
                else "no markdown (no sections rendered)"
            ),
            status="pass",
        )
    )

    # -- 3) real LLM call through the provider interface -------------------- #
    request = chat_service.compose(
        message=question.question,
        history=[],
        model=config.llm_model,
        router_context=markdown,
    )
    request.max_tokens = config.llm_max_tokens
    started = time.monotonic()
    response = await chat_service.complete(provider, request)
    latency_ms = int((time.monotonic() - started) * 1000)
    reply = response.message.content if isinstance(response.message.content, str) else ""
    output.reply = reply
    output.reply_preview = reply[:220].replace("\n", " ")
    output.latency_ms = latency_ms
    output.prompt_tokens = response.usage.prompt_tokens
    output.completion_tokens = response.usage.completion_tokens

    # -- 3b) request/response dump for auditing ----------------------------- #
    dump_dir = Path(config.output_dir) / "requests"
    dump = {
        "scenario_id": question.scenario_id,
        "category": question.category,
        "outcome": question.outcome,
        "question": question.question,
        "model": config.llm_model,
        "max_tokens": config.llm_max_tokens,
        "request_messages": [
            {"role": m.role, "content": m.content} for m in request.messages
        ],
        "response": {
            "reply": reply,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "latency_ms": latency_ms,
        },
    }
    try:
        dump_dir.mkdir(parents=True, exist_ok=True)
        (dump_dir / f"{question.scenario_id}.json").write_text(
            json.dumps(dump, indent=2), encoding="utf-8"
        )
    except OSError as exc:  # pragma: no cover - best effort
        logger.warning("could not write reqresp dump: %s", exc)

    # -- 4) anomaly ground truth + final verdict ---------------------------- #
    payload = snapshot.model_dump(mode="json")
    for rule in question.anomalies:
        observed = rule.extract(payload)
        applies = rule.applies(payload)
        output.anomalies.append(
            AnomalyRunOutput(
                question=question.question,
                outcome=question.outcome,
                rules=[
                    RuleRunOutput(
                        rule_id=rule.label,
                        label=rule.label,
                        section=rule.section,
                        field=rule.field,
                        op=rule.op,
                        threshold=rule.threshold,
                        observed=observed,
                        applies=applies,
                        status="pass",
                        detail=rule.describe(),
                    )
                ],
                status="pass",
                detail=f"observed={observed} applies={applies}",
            )
        )

    status, detail = _verdict(question, reply)
    output.status = status
    output.detail = detail
    output.must_contain_ok, output.must_not_contain_ok, _ = _evaluate_reply(question, reply)
    return output


# --------------------------------------------------------------------------- #
# Preflight                                                                   #
# --------------------------------------------------------------------------- #

_PREFLIGHT_IMPORTS = (
    "app.services.chat_service",
    "app.services.router_context_policy",
    "app.services.router_manager",
    "app.services.router_tool",
    "providers.factory",
    "providers.config",
    "router_agent.transport.ssh",
    "router_agent.snapshot",
    "pydantic",
    "httpx",
    "cryptography",
)


def _preflight() -> list[ScenarioStep]:
    checks: list[ScenarioStep] = []
    version = sys.version_info
    checks.append(
        ScenarioStep(
            step_id="python",
            action="python version check",
            expected=f">= {MIN_PYTHON_AT_LEAST[0]}.{MIN_PYTHON_AT_LEAST[1]}",
            actual=f"{version.major}.{version.minor}.{version.micro}",
            status="pass" if version >= MIN_PYTHON_AT_LEAST else "fail",
        )
    )
    missing: list[str] = []
    for module in _PREFLIGHT_IMPORTS:
        try:
            __import__(module)
        except Exception:  # noqa: BLE001 - reported as a check result
            missing.append(module)
    checks.append(
        ScenarioStep(
            step_id="imports",
            action="required module imports",
            expected="all importable",
            actual="ok" if not missing else f"missing: {', '.join(missing)}",
            status="pass" if not missing else "fail",
        )
    )
    key = _resolve_deepseek_key()
    checks.append(
        ScenarioStep(
            step_id="llm-key",
            action="resolve DeepSeek API key",
            expected="non-empty key",
            actual=f"key={_masked(key)}",
            status="pass" if key else "fail",
        )
    )
    return checks


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #


def _load_config() -> EvalsConfig:
    scenarios = [s.strip() for s in os.getenv("EVALS_SCENARIOS", "").split(",") if s.strip()]
    return EvalsConfig(
        llm_provider=os.getenv("EVALS_LLM_PROVIDER", "deepseek"),
        llm_model=os.getenv("EVALS_LLM_MODEL", "deepseek-chat"),
        llm_max_tokens=int(os.getenv("EVALS_MAX_TOKENS", "1024")),
        llm_timeout_seconds=float(os.getenv("EVALS_LLM_TIMEOUT", "120")),
        output_dir=os.getenv("EVALS_OUTPUT_DIR", "./e2e_evals/outputs"),
        verbose=os.getenv("VERBOSE") in {"1", "true", "yes"},
        scenario_ids=scenarios,
    )


async def _run(config: EvalsConfig) -> RootRunOutputs:
    report = RootRunOutputs(run_id=config.run_id, status="running")
    report.preflight = _preflight()
    if any(check.status == "fail" for check in report.preflight):
        report.status = "preflight-failed"
        return report

    # -- snapshot collection (production path) ----------------------------- #
    snapshot, error, elapsed = _build_snapshot()
    report.dashboard = DashboardAppRunOutput(
        router_connected=snapshot is not None,
        host=None,
        snapshot_collected=snapshot is not None,
        collection_seconds=round(elapsed, 2),
        error=error,
    )
    if snapshot is None or error:
        report.status = "collection-failed"
        return report

    host = snapshot.meta.host or snapshot.meta.device_id
    report.dashboard.host = host if host != "unconfigured" else None
    if snapshot.kernel is not None:
        report.dashboard.device_id = snapshot.kernel.hostname

    # persist the raw snapshot for reuse by sibling shells/harnesses
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = snapshot.model_dump(mode="json")
    (output_dir / config.snapshot_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report.dashboard.sections = {
        name: "collected"
        for name, value in payload.items()
        if value not in (None, [], {}, "")
    }

    # -- chat wiring + real LLM -------------------------------------------- #
    os.environ.setdefault("DEEPSEEK_API_KEY", _resolve_deepseek_key() or "")
    update = _router_update(snapshot, report.dashboard.device_id or "demo-router")
    chat_service, router_manager, _ = _build_services(snapshot, update)
    provider = chat_service.provider_for("deepseek")

    scenarios = [
        q
        for q in _every_test_scenarios()
        if (not config.scenario_ids) or q.scenario_id in config.scenario_ids
    ]
    results: list[ScenarioRunOutput] = []
    total_latency = total_prompt = total_completion = 0
    passed = failed = 0
    for question in scenarios:
        result = await _run_scenario(chat_service, provider, snapshot, question, config)
        results.append(result)
        total_latency += result.latency_ms
        total_prompt += result.prompt_tokens
        total_completion += result.completion_tokens
        if result.status == "pass":
            passed += 1
        else:
            failed += 1
        print(
            f"  [{result.status.upper():4s}] {question.scenario_id:28s} "
            f"{result.latency_ms:>5}ms p={result.prompt_tokens} c={result.completion_tokens}"
            f"  (sections_ok={result.sections_ok}) {result.detail}"
        )

    report.chat_llm = ChatLLMRunOutput(
        provider=config.llm_provider,
        model=config.llm_model,
        total_requests=len(results),
        total_latency_ms=total_latency,
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        avg_latency_ms=round(total_latency / max(1, len(results))),
        passed=passed,
        failed=failed,
        skipped=0,
    )
    report.scenarios = results
    checked = [rule for scenario in results for rule in scenario.anomalies]
    report.anomaly = AnomalyRunOutput(
        question=",".join(
            scenario.scenario_id for scenario in results if scenario.anomalies
        ),
        outcome="flag" if checked else "no-flag",
        rules=[rule.rules[0] for rule in checked] if checked else [],
        status="pass" if all(result.status == "pass" for result in results) else "fail",
        detail=f"{len(checked)} anomaly rule(s) checked",
    )
    if len(results) == passed and failed == 0:
        report.status = "completed"
    else:
        report.status = "completed-with-failures"
    report.finished_at = datetime.now(UTC)
    return report


async def main() -> int:
    """Entry point: run every-test and print a summary; returns exit code."""
    logging.basicConfig(level=logging.WARNING)
    config = _load_config()
    print(f"== every-test harness ({config.run_id}) ==")
    print(f"   llm: {config.llm_provider}/{config.llm_model}")
    print("   preflight:")
    try:
        report = await _run(config)
    except Exception as exc:  # noqa: BLE001 - surfaced as a failed run
        logger.exception("every-test run failed")
        print(f"   FATAL: {exc}")
        return 2

    for check in report.preflight:
        print(f"     [{check.status.upper():4s}] {check.action}: {check.actual}")
    dash = report.dashboard
    print(f"   collection: connected={dash.router_connected} "
          f"collected={dash.snapshot_collected} in {dash.collection_seconds}s "
          f"error={dash.error or 'none'}")
    if report.status == "collection-failed":
        print("   no live snapshot; dashboard run failed. exiting 2.")
        return 2
    if report.status == "preflight-failed":
        print("   preflight failed. exiting 2.")
        return 2
    print(f"   llm: {report.chat_llm.passed} passed / {report.chat_llm.failed} failed "
          f"/ {report.chat_llm.total_requests} total, "
          f"avg {report.chat_llm.avg_latency_ms}ms, "
          f"tokens {report.chat_llm.total_prompt_tokens}+{report.chat_llm.total_completion_tokens}")
    preflight_failures = sum(1 for check in report.preflight if check.status != "pass")
    collection_failures = 0 if report.dashboard.snapshot_collected else 1
    scenario_failures = report.chat_llm.failed
    if scenario_failures or preflight_failures or collection_failures:
        exit_code = 1 if scenario_failures else 2
    else:
        exit_code = 0
    print(
        f"   summary: scenario_failures={scenario_failures} "
        f"preflight_failures={preflight_failures} "
        f"collection_failures={collection_failures} exit={exit_code}"
    )

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / config.report_path
    report_path.write_text(
        json.dumps(report.model_dump(mode="json", exclude_none=True), indent=2),
        encoding="utf-8",
    )
    print(f"   report: {report_path}")
    preflight_failures = sum(1 for check in report.preflight if check.status != "pass")
    clean = (
        report.dashboard.snapshot_collected
        and report.chat_llm.failed == 0
        and preflight_failures == 0
    )
    if clean:
        return 0
    if report.chat_llm.failed:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))