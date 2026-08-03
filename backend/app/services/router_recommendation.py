"""AI router recommendations: actionable recommendations from a DiagnosisReport.

The engine consumes an existing :class:`DiagnosisReport` and produces a
structured :class:`RecommendationReport` of actionable items. It is fully
deterministic — no LLM reasoning and no external APIs. It performs no router
analysis of its own and never executes Router Tools; it only reads the
diagnosis findings it is given. Related findings are merged into single
recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.router_diagnosis import DiagnosisReport, Finding

Priority = Literal["low", "medium", "high", "urgent"]

# Severity -> priority escalation for a group of findings.
_SEVERITY_PRIORITY: dict[str, Priority] = {
    "critical": "urgent",
    "warning": "high",
    "info": "medium",
}

_PRIORITY_WEIGHT: dict[Priority, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "urgent": 4,
}


@dataclass(frozen=True)
class _GroupDefinition:
    """Template for a merged recommendation group."""

    key: str
    titles: tuple[str, ...]
    category: str
    title: str
    description: str
    action: str
    impact: str


_GROUPS: tuple[_GroupDefinition, ...] = (
    _GroupDefinition(
        key="connectivity",
        titles=("Router is offline",),
        category="connectivity",
        title="Restore router connectivity",
        description="The router is unreachable or reporting no state.",
        action="Check power and the network link, confirm the data feed is "
        "connected, and restart the router if needed.",
        impact="Restores monitoring and the ability to act on further findings.",
    ),
    _GroupDefinition(
        key="cpu",
        titles=(
            "High CPU utilization",
            "Critical CPU utilization",
            "High load average",
            "Critically high load",
        ),
        category="cpu",
        title="Reduce CPU pressure",
        description="High CPU utilization or load was detected.",
        action="Inspect running processes and services; stop or throttle the "
        "heaviest consumers, or consider upgrading the hardware.",
        impact="Frees CPU capacity and improves responsiveness and stability.",
    ),
    _GroupDefinition(
        key="memory",
        titles=("High memory utilization", "Critical memory utilization"),
        category="memory",
        title="Optimize memory usage",
        description="Memory utilization is high.",
        action="Review running services for memory leaks and restart "
        "memory-heavy services, or reduce the number of active services.",
        impact="Reduces out-of-memory pressure and improves reliability.",
    ),
    _GroupDefinition(
        key="storage",
        titles=("High storage utilization", "Critical storage utilization"),
        category="storage",
        title="Free storage capacity",
        description="One or more filesystems are heavily utilized.",
        action="Remove logs, caches, and unneeded packages from the affected "
        "filesystems to free space.",
        impact="Prevents the router from running out of writable storage.",
    ),
    _GroupDefinition(
        key="wan",
        titles=("Missing WAN interface",),
        category="network",
        title="Restore WAN connectivity",
        description="No WAN interface was detected on the router.",
        action="Check the WAN port, cable, and the PPPoE/DHCP configuration.",
        impact="Restores internet connectivity for the network.",
    ),
    _GroupDefinition(
        key="wifi",
        titles=("Missing WiFi",),
        category="wifi",
        title="Enable WiFi radios",
        description="No WiFi radios were detected on the router.",
        action="Check whether wireless is enabled and configured on the router.",
        impact="Restores wireless access for clients.",
    ),
    _GroupDefinition(
        key="data-quality",
        titles=("Unknown router values",),
        category="data-quality",
        title="Improve data collection",
        description="Some router values are missing or unknown.",
        action="Re-collect the router snapshot or verify that the data feed is complete.",
        impact="Improves the accuracy of future diagnosis and recommendations.",
    ),
)


@dataclass(frozen=True)
class Recommendation:
    """A single actionable recommendation."""

    id: str
    priority: Priority
    category: str
    title: str
    description: str
    action: str
    impact: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "priority": self.priority,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "action": self.action,
            "impact": self.impact,
        }


@dataclass(frozen=True)
class RecommendationReport:
    """Structured output of the recommendation engine."""

    router_id: str
    recommendations: list[Recommendation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "router_id": self.router_id,
            "recommendations": [
                recommendation.to_dict() for recommendation in self.recommendations
            ],
        }

    def render_markdown(self) -> str | None:
        """Render the report as markdown (``None`` when there are no recommendations)."""
        if not self.recommendations:
            return None
        lines = ["## Recommendations"]
        for recommendation in self.recommendations:
            lines.append(
                f"- **[{recommendation.priority.upper()}] {recommendation.title}** — "
                f"{recommendation.description}"
            )
            lines.append(f"  - Action: {recommendation.action}")
            lines.append(f"  - Impact: {recommendation.impact}")
        return "\n".join(lines)


class RouterRecommendationEngine:
    """Generates deterministic recommendations from a :class:`DiagnosisReport`."""

    def generate(self, report: DiagnosisReport) -> RecommendationReport:
        """Turn ``report``'s findings into merged, prioritized recommendations."""
        grouped: dict[str, list[Finding]] = {group.key: [] for group in _GROUPS}
        unmatched: list[Finding] = []
        for finding in report.findings:
            group = self._group_for(finding.title)
            if group is None:
                unmatched.append(finding)
            else:
                grouped[group.key].append(finding)

        recommendations = [
            self._build(group, grouped[group.key]) for group in _GROUPS if grouped[group.key]
        ]
        recommendations.extend(self._generic(finding) for finding in unmatched)
        recommendations.sort(key=lambda rec: (-_PRIORITY_WEIGHT[rec.priority], rec.id))
        return RecommendationReport(
            router_id=report.router_id,
            recommendations=recommendations,
        )

    def _group_for(self, title: str) -> _GroupDefinition | None:
        for group in _GROUPS:
            if title in group.titles:
                return group
        return None

    def _build(self, group: _GroupDefinition, findings: list[Finding]) -> Recommendation:
        affected = ", ".join(finding.title for finding in findings)
        priority = _SEVERITY_PRIORITY[
            max((finding.severity for finding in findings), key=_severity_rank)
        ]
        return Recommendation(
            id=f"rec-{group.key}",
            priority=priority,
            category=group.category,
            title=group.title,
            description=f"{group.description} Affected findings: {affected}.",
            action=group.action,
            impact=group.impact,
        )

    def _generic(self, finding: Finding) -> Recommendation:
        return Recommendation(
            id=f"rec-{_slugify(finding.title)}",
            priority=_SEVERITY_PRIORITY.get(finding.severity, "medium"),
            category=finding.category,
            title=finding.title,
            description=finding.description,
            action=finding.recommendation,
            impact="Resolves the identified concern.",
        )


_SEVERITY_RANK: dict[str, int] = {"info": 1, "warning": 2, "critical": 3}


def _severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, 1)


def _slugify(title: str) -> str:
    cleaned = "".join(char if char.isalnum() else "-" for char in title.lower())
    return cleaned.strip("-")
