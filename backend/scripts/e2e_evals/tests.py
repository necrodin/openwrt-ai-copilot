"""E2E every-test evals: scenario models and interpreters (Pydantic).

Typed graph / interpretation layer over the every-test scenario set:

* :class:`StepTypes` and :class:`AllStepTypes` — the fixed step vocabulary.
* :class:`EveryTestAction` — a single test action bound to a step type.
* :class:`ActionRule` — maps an observation back to a step-of-run status.
* :class:`EveryTestScenario` — a scenario made of actions plus rules.
* :class:`ScenarioRules` — the answer-quality + anomaly rules for a question.
* :class:`ScenarioSelector` / :class:`TestFilter` — choose which scenarios run.
* :func:`iter_steps` / :func:`interpret` — tiny interpreters over the model.

The models are pure data; the interpreters only combine precomputed
observations (replies, snapshot values, section sets) into status verdicts.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import StrEnum

from pydantic import BaseModel, Field

from e2e_evals.domains import AnomalyRule, QuestionSet

# --------------------------------------------------------------------------- #
# Step vocabulary                                                             #
# --------------------------------------------------------------------------- #


class StepTypes(StrEnum):
    """The fixed step types in the every-test flow."""

    COLLECT = "collect"  # collect the live router snapshot
    FOCUS = "focus"  # deterministic focused-context selection
    LLM = "llm"  # real LLM call with the focused context
    CLASSIFY = "classify"  # verdict on the model reply
    REPORT = "report"  # final report aggregation


#: All step types (frozen view over :class:`StepTypes`).
AllStepTypes: frozenset[str] = frozenset(item.value for item in StepTypes)


# --------------------------------------------------------------------------- #
# Actions and rules                                                           #
# --------------------------------------------------------------------------- #


class EveryTestAction(BaseModel):
    """A single directed action with an expected outcome."""

    action_id: str
    step: StepTypes
    target: str = ""
    expected: str | None = None
    status: str = "pending"  # pending | pass | fail | skip
    detail: str = ""


class ActionRule(BaseModel):
    """Interpret an observation into a status for the owning action."""

    condition: str  # e.g. "must_contain", "must_not_contain", "sections_ok"
    implied_status: str = "pass"
    detail: str = ""

    def evaluate(self, observations: dict) -> str | None:
        """Return ``implied_status`` when ``observations`` key is truthy."""
        if observations.get(self.condition):
            return self.implied_status
        return None


class EveryTestScenario(BaseModel):
    """A scenario: ordered actions plus the rules interpreting their outcome."""

    scenario_id: str
    category: str = "generic"
    question: str
    description: str = ""
    steps: list[EveryTestAction] = Field(default_factory=list)
    rules: list[ActionRule] = Field(default_factory=list)


class ScenarioRules(BaseModel):
    """Answer-quality spec for one question's model reply."""

    question: str
    outcome: str = "generic"  # generic | flag | no-flag | status
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    anomalies: list[AnomalyRule] = Field(default_factory=list)

    @classmethod
    def from_question(cls, question: QuestionSet) -> ScenarioRules:
        return cls(
            question=question.question,
            outcome=question.outcome,
            must_contain=list(question.must_contain),
            must_not_contain=list(question.must_not_contain),
            anomalies=list(question.anomalies),
        )


# --------------------------------------------------------------------------- #
# Selection                                                                   #
# --------------------------------------------------------------------------- #


class TestFilter(BaseModel):
    """Select scenarios by category and/or id (empty sets = no restriction)."""

    categories: set[str] = Field(default_factory=set)
    ids: set[str] = Field(default_factory=set)

    def matches(self, scenario: QuestionSet) -> bool:
        if self.ids and scenario.scenario_id not in self.ids:
            return False
        if self.categories and scenario.category not in self.categories:
            return False
        return scenario.enabled


class ScenarioSelector:
    """Filter a scenario list once, keeping the original order."""

    def __init__(self, scenarios: Iterable[QuestionSet]) -> None:
        self._scenarios = list(scenarios)

    def select(self, filter_: TestFilter | None = None) -> list[QuestionSet]:
        if filter_ is None:
            return [s for s in self._scenarios if s.enabled]
        return [s for s in self._scenarios if filter_.matches(s)]


# --------------------------------------------------------------------------- #
# Interpreters                                                                #
# --------------------------------------------------------------------------- #


def iter_steps(scenarios: Iterable[EveryTestScenario]) -> list[EveryTestAction]:
    """Flatten every step across scenarios, in scenario order."""
    steps: list[EveryTestAction] = []
    for scenario in scenarios:
        steps.extend(scenario.steps)
    return steps


def interpret(action_rules: Iterable[ActionRule], observations: dict) -> list[str]:
    """Apply rules to observations; return the statuses they imply."""
    statuses: list[str] = []
    for rule in action_rules:
        status = rule.evaluate(observations)
        if status is not None:
            statuses.append(status)
    return statuses


#: Convenience typed aliases used by callers.
FilterFunc = Callable[[QuestionSet], bool]

__all__ = [
    "ActionRule",
    "AllStepTypes",
    "EveryTestAction",
    "EveryTestScenario",
    "FilterFunc",
    "ScenarioRules",
    "ScenarioSelector",
    "StepTypes",
    "TestFilter",
    "interpret",
    "iter_steps",
]