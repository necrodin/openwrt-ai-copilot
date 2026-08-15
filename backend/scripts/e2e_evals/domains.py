"""E2E every-test evals: domain models (Pydantic).

Typed records for a single end-to-end run of the copilot against a real router:

* :class:`EvalsConfig` — runtime configuration for the every-test harness.
* :class:`AnomalyRule` — a deterministic threshold rule over a snapshot field
  used to establish ground truth (`flag`, `no-flag`, or `clear`) for a fault /
  anomaly question without an LLM-as-judge.
* :class:`QuestionSet` / :class:`ScenarioStep` — the per-scenario test spec.
* :class:`RunOutputs` / :class:`RootRunOutputs` — the typed run report.

The models only describe data; they never reach out to a router or an LLM.
"""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

MIN_PYTHON = "3.12"
MIN_PYTHON_AT_LEAST = (3, 12)

#: The minimum input-token budget the every-test harness requires of the LLM.
#: The known-broken local Ollama profile (`qwen2.5-coder:14b`, 4096-token
#: context) is below this floor and is never used.
MIN_REQUIRED_CONTEXT_TOKENS = 8192


class EvalsConfig(BaseModel):
    """Runtime configuration for an every-test run."""

    run_id: str = Field(default_factory=lambda: datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    output_dir: str = "./e2e_evals/outputs"
    report_path: str = "e2e_report.json"
    snapshot_path: str = "snapshot.json"

    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    llm_max_tokens: int = 1024
    llm_timeout_seconds: float = 120.0

    scenario_ids: list[str] = Field(default_factory=list)
    verbose: bool = False


class LLMDefaults(BaseModel):
    """Default LLM facts the harness asserts against."""

    provider: str = "deepseek"
    model: str = "deepseek-chat"
    min_context_tokens: int = MIN_REQUIRED_CONTEXT_TOKENS
    forbidden_broken_path: str = (
        "the 4096-token local Ollama profile (qwen2.5-coder:14b) is a known "
        "broken path and is never selected by the every-test harness"
    )


class AnomalyRule(BaseModel):
    """Deterministic ground-truth rule over one numeric snapshot field."""

    label: str
    section: str
    field: str
    op: str = "gt"
    threshold: float | None = None

    _OPS = {
        "gt": operator.gt,
        "gte": operator.ge,
        "lt": operator.lt,
        "lte": operator.le,
        "eq": operator.eq,
        "ne": operator.ne,
    }

    def extract(self, snapshot: dict[str, Any]) -> Any:
        """Walk ``section.field`` through the (json-safe) snapshot dict."""
        value = snapshot.get(self.section)
        for part in self.field.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list):
                try:
                    value = value[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return value

    def applies(self, snapshot: dict[str, Any]) -> bool:
        """Return True when the embedded limit is exceeded by the snapshot."""
        if self.threshold is None:
            return False
        value = self.extract(snapshot)
        if not isinstance(value, (int, float)):
            return False
        return bool(self._OPS[self.op](value, self.threshold))

    def describe(self) -> str:
        return f"{self.section}.{self.field} {self.op} {self.threshold}"


class QuestionSet(BaseModel):
    """A single every-test scenario: question, expected sections, and rules."""

    scenario_id: str
    category: str = "generic"  # generic | fault | security | cross-cutting
    question: str
    description: str = ""
    expected_sections: list[str] = Field(default_factory=list)
    anomalies: list[AnomalyRule] = Field(default_factory=list)
    outcome: str = "generic"  # generic | flag | no-flag | status
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    enabled: bool = True


class ScenarioStep(BaseModel):
    """One recorded step of a scenario (collect / focus / llm / classify)."""

    step_id: str
    action: str
    expected: str | None = None
    actual: str | None = None
    status: str = "pending"  # pending | pass | fail | skip
    detail: str = ""


# --------------------------------------------------------------------------- #
# Run outputs                                                                 #
# --------------------------------------------------------------------------- #


class RuleRunOutput(BaseModel):
    """Result of evaluating one :class:`AnomalyRule` against the snapshot."""

    rule_id: str
    label: str
    section: str
    field: str
    op: str
    threshold: float | None
    observed: Any = None
    applies: bool = False
    status: str = "skip"
    detail: str = ""


class AnomalyRunOutput(BaseModel):
    """Ground truth + model answer verdict for one anomaly question."""

    question: str = ""
    outcome: str = "no-flag"
    rules: list[RuleRunOutput] = Field(default_factory=list)
    status: str = "pending"
    detail: str = ""


class ChatLLMRunOutput(BaseModel):
    """Aggregated metadata for the chat/LLM portion of the run."""

    provider: str = ""
    model: str = ""
    total_requests: int = 0
    total_latency_ms: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    avg_latency_ms: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0


class DashboardAppRunOutput(BaseModel):
    """Outcome of collecting a live router snapshot for the run."""

    router_connected: bool = False
    host: str | None = None
    port: int = 22
    device_id: str | None = None
    snapshot_collected: bool = False
    collection_seconds: float = 0.0
    sections: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ScenarioRunOutput(BaseModel):
    """Full per-scenario every-test record."""

    question: str
    scenario_id: str
    category: str
    outcome: str
    sections_expected: list[str] = Field(default_factory=list)
    sections_actual: list[str] = Field(default_factory=list)
    sections_ok: bool = False
    must_contain_ok: bool = False
    must_not_contain_ok: bool = False
    reply: str = ""
    reply_preview: str = ""
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    anomalies: list[AnomalyRunOutput] = Field(default_factory=list)
    steps: list[ScenarioStep] = Field(default_factory=list)
    status: str = "pending"
    detail: str = ""


class RootRunOutputs(BaseModel):
    """The typed every-test report for one run."""

    run_id: str = Field(default_factory=lambda: datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    status: str = "pending"
    dashboard: DashboardAppRunOutput = Field(default_factory=DashboardAppRunOutput)
    chat_llm: ChatLLMRunOutput = Field(default_factory=ChatLLMRunOutput)
    anomaly: AnomalyRunOutput = Field(default_factory=AnomalyRunOutput)
    scenarios: list[ScenarioRunOutput] = Field(default_factory=list)
    preflight: list[ScenarioStep] = Field(default_factory=list)
    detail: str = ""


class RunOutputs(BaseModel):
    """General run slot carrying the invocation inputs plus the report."""

    config: EvalsConfig = Field(default_factory=EvalsConfig)
    llm_defaults: LLMDefaults = Field(default_factory=LLMDefaults)
    outputs: RootRunOutputs = Field(default_factory=RootRunOutputs)
    app_runs: RootRunOutputs | None = None


__all__ = [
    "MIN_PYTHON",
    "MIN_PYTHON_AT_LEAST",
    "MIN_REQUIRED_CONTEXT_TOKENS",
    "AnomalyRunOutput",
    "AnomalyRule",
    "ChatLLMRunOutput",
    "DashboardAppRunOutput",
    "EvalsConfig",
    "LLMDefaults",
    "QuestionSet",
    "RootRunOutputs",
    "RuleRunOutput",
    "RunOutputs",
    "ScenarioRunOutput",
    "ScenarioStep",
]