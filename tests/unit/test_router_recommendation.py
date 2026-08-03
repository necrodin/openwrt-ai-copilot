"""Router recommendation tests: deterministic recommendations from a DiagnosisReport."""

from __future__ import annotations

from app.services.router_diagnosis import DiagnosisReport, Finding
from app.services.router_recommendation import (
    Recommendation,
    RecommendationReport,
    RouterRecommendationEngine,
)


def _finding(severity: str, title: str) -> Finding:
    return Finding(
        severity=severity,
        category="router-health",
        title=title,
        description=f"{title} description.",
        recommendation=f"Recommendation for {title}.",
    )


def _report(*findings: Finding) -> DiagnosisReport:
    return DiagnosisReport(router_id="default", findings=list(findings))


def _engine() -> RouterRecommendationEngine:
    return RouterRecommendationEngine()


def test_empty_report_has_no_recommendations() -> None:
    report = _engine().generate(_report())
    assert isinstance(report, RecommendationReport)
    assert report.recommendations == []
    assert report.render_markdown() is None


def test_report_structure() -> None:
    report = _engine().generate(_report(_finding("critical", "Router is offline")))
    assert report.router_id == "default"
    recommendation = report.recommendations[0]
    assert isinstance(recommendation, Recommendation)
    assert recommendation.id
    assert recommendation.priority == "urgent"
    assert recommendation.category
    assert recommendation.title
    assert recommendation.description
    assert recommendation.action
    assert recommendation.impact


def test_report_to_dict_and_markdown() -> None:
    report = _engine().generate(_report(_finding("critical", "Router is offline")))
    as_dict = report.to_dict()
    assert as_dict["router_id"] == "default"
    assert as_dict["recommendations"][0]["priority"] == "urgent"
    markdown = report.render_markdown()
    assert markdown is not None
    assert "## Recommendations" in markdown
    assert "URGENT" in markdown
    assert "Action:" in markdown
    assert "Impact:" in markdown


def test_offline_finding_is_urgent_connectivity() -> None:
    recommendation = (
        _engine().generate(_report(_finding("critical", "Router is offline"))).recommendations[0]
    )
    assert recommendation.id == "rec-connectivity"
    assert recommendation.priority == "urgent"
    assert recommendation.category == "connectivity"


def test_priority_mapping_from_severity() -> None:
    engine = _engine()
    assert (
        engine.generate(_report(_finding("critical", "Critical CPU utilization")))
        .recommendations[0]
        .priority
        == "urgent"
    )
    assert (
        engine.generate(_report(_finding("warning", "High CPU utilization")))
        .recommendations[0]
        .priority
        == "high"
    )
    assert (
        engine.generate(_report(_finding("info", "Unknown router values")))
        .recommendations[0]
        .priority
        == "medium"
    )


def test_related_findings_are_merged() -> None:
    report = _engine().generate(
        _report(
            _finding("warning", "High CPU utilization"),
            _finding("critical", "Critically high load"),
        )
    )
    assert len(report.recommendations) == 1
    recommendation = report.recommendations[0]
    assert recommendation.id == "rec-cpu"
    assert recommendation.priority == "urgent"
    assert "High CPU utilization" in recommendation.description
    assert "Critically high load" in recommendation.description


def test_multiple_storage_findings_merge_into_one() -> None:
    report = _engine().generate(
        _report(
            _finding("warning", "High storage utilization"),
            _finding("critical", "Critical storage utilization"),
        )
    )
    assert len(report.recommendations) == 1
    assert report.recommendations[0].id == "rec-storage"
    assert report.recommendations[0].priority == "urgent"


def test_generic_fallback_for_unknown_title() -> None:
    recommendation = (
        _engine().generate(_report(_finding("warning", "Unrecognized anomaly"))).recommendations[0]
    )
    assert recommendation.id == "rec-unrecognized-anomaly"
    assert recommendation.priority == "high"
    assert recommendation.category == "router-health"
    assert recommendation.action == "Recommendation for Unrecognized anomaly."


def test_recommendations_sorted_by_priority() -> None:
    report = _engine().generate(
        _report(
            _finding("warning", "High memory utilization"),
            _finding("critical", "Router is offline"),
            _finding("info", "Unknown router values"),
        )
    )
    priorities = [rec.priority for rec in report.recommendations]
    assert priorities == ["urgent", "high", "medium"]


def test_recommendation_to_dict() -> None:
    recommendation = Recommendation(
        id="rec-wan",
        priority="high",
        category="network",
        title="Restore WAN connectivity",
        description="No WAN interface was detected.",
        action="Check the WAN port and configuration.",
        impact="Restores internet connectivity.",
    )
    assert recommendation.to_dict() == {
        "id": "rec-wan",
        "priority": "high",
        "category": "network",
        "title": "Restore WAN connectivity",
        "description": "No WAN interface was detected.",
        "action": "Check the WAN port and configuration.",
        "impact": "Restores internet connectivity.",
    }


def test_wifi_and_wan_findings_each_yield_a_recommendation() -> None:
    report = _engine().generate(
        _report(
            _finding("warning", "Missing WAN interface"),
            _finding("warning", "Missing WiFi"),
        )
    )
    ids = [rec.id for rec in report.recommendations]
    assert ids == ["rec-wan", "rec-wifi"]
