"""Router diagnosis tests: deterministic findings from a RouterSnapshot."""

from __future__ import annotations

from app.services.router_diagnosis import DiagnosisReport, Finding, RouterDiagnosisEngine
from app.services.router_snapshot import RouterSnapshot


def _engine() -> RouterDiagnosisEngine:
    return RouterDiagnosisEngine()


def _snapshot(**sections) -> RouterSnapshot:
    return RouterSnapshot(
        system=sections.get("system"),
        cpu=sections.get("cpu"),
        memory=sections.get("memory"),
        storage=sections.get("storage"),
        network=sections.get("network"),
        wifi=sections.get("wifi"),
    )


def test_healthy_snapshot_has_no_findings() -> None:
    report = _engine().diagnose(
        _snapshot(
            system={"hostname": "demo-router", "model": "RT-1", "firmware": "23.05"},
            cpu={"usage_percent": 12.0, "cores": 4, "load_1": 0.5},
            memory={"used_percent": 40.0, "total_kb": 262144},
            storage=[{"mountpoint": "/overlay", "use_percent": 30.0}],
            network=[{"name": "wan", "up": True, "proto": "dhcp"}],
            wifi={"radios": ["radio0"], "client_count": 3},
        )
    )
    assert isinstance(report, DiagnosisReport)
    assert report.findings == []


def test_report_structure() -> None:
    report = _engine().diagnose(_snapshot(cpu={"usage_percent": 80.0, "cores": 4}))
    assert report.router_id == "default"
    finding = report.findings[0]
    assert isinstance(finding, Finding)
    assert finding.severity == "warning"
    assert finding.category == "router-health"
    assert finding.title
    assert finding.description
    assert finding.recommendation


def test_report_to_dict_and_markdown() -> None:
    report = _engine().diagnose(_snapshot(cpu={"usage_percent": 80.0, "cores": 4}))
    as_dict = report.to_dict()
    assert as_dict["router_id"] == "default"
    assert as_dict["findings"][0]["severity"] == "warning"
    markdown = report.render_markdown()
    assert markdown is not None
    assert "## Router Diagnosis" in markdown
    assert "WARNING" in markdown


def test_empty_report_markdown_is_none() -> None:
    report = _engine().diagnose(
        _snapshot(
            system={"hostname": "demo-router", "model": "RT-1", "firmware": "23.05"},
            cpu={"usage_percent": 12.0, "cores": 4},
        )
    )
    assert report.render_markdown() is None


def test_cpu_utilization_thresholds() -> None:
    engine = _engine()
    assert engine.diagnose(_snapshot(cpu={"usage_percent": 74.9, "cores": 4})).findings == []
    warning = engine.diagnose(_snapshot(cpu={"usage_percent": 75.0, "cores": 4}))
    assert warning.findings[0].severity == "warning"
    assert warning.findings[0].title == "High CPU utilization"
    critical = engine.diagnose(_snapshot(cpu={"usage_percent": 90.0, "cores": 4}))
    assert critical.findings[0].severity == "critical"
    assert critical.findings[0].title == "Critical CPU utilization"


def test_memory_utilization_thresholds() -> None:
    engine = _engine()
    assert (
        engine.diagnose(_snapshot(memory={"used_percent": 74.9, "total_kb": 262144})).findings == []
    )
    warning = engine.diagnose(_snapshot(memory={"used_percent": 75.0, "total_kb": 262144}))
    assert warning.findings[0].severity == "warning"
    critical = engine.diagnose(_snapshot(memory={"used_percent": 90.0, "total_kb": 262144}))
    assert critical.findings[0].severity == "critical"


def test_storage_utilization_thresholds() -> None:
    engine = _engine()
    mounts = [{"mountpoint": "/overlay", "use_percent": 50.0}]
    assert engine.diagnose(_snapshot(storage=mounts)).findings == []
    warning = engine.diagnose(_snapshot(storage=[{"mountpoint": "/overlay", "use_percent": 85.0}]))
    assert warning.findings[0].severity == "warning"
    assert warning.findings[0].title == "High storage utilization"
    critical = engine.diagnose(_snapshot(storage=[{"mountpoint": "/overlay", "use_percent": 95.0}]))
    assert critical.findings[0].severity == "critical"


def test_offline_router_is_critical() -> None:
    report = _engine().diagnose(
        _snapshot(system=None, cpu=None, memory=None, storage=None, network=None, wifi=None)
    )
    finding = report.findings[0]
    assert finding.severity == "critical"
    assert finding.title == "Router is offline"


def test_high_load_thresholds() -> None:
    engine = _engine()
    assert (
        engine.diagnose(_snapshot(cpu={"usage_percent": 10.0, "cores": 4, "load_1": 3.0})).findings
        == []
    )
    warning = engine.diagnose(_snapshot(cpu={"usage_percent": 10.0, "cores": 4, "load_1": 4.0}))
    assert warning.findings[0].severity == "warning"
    assert warning.findings[0].title == "High load average"
    critical = engine.diagnose(_snapshot(cpu={"usage_percent": 10.0, "cores": 4, "load_1": 8.0}))
    assert critical.findings[0].severity == "critical"
    assert critical.findings[0].title == "Critically high load"


def test_missing_wan_interface() -> None:
    report = _engine().diagnose(
        _snapshot(
            network=[{"name": "br-lan", "up": True, "proto": "static"}],
            wifi={"radios": ["radio0"], "client_count": 2},
        )
    )
    finding = report.findings[0]
    assert finding.severity == "warning"
    assert finding.title == "Missing WAN interface"
    ok = _engine().diagnose(
        _snapshot(
            network=[{"name": "wan", "up": True}],
            wifi={"radios": ["radio0"], "client_count": 2},
        )
    )
    assert ok.findings == []


def test_missing_wifi() -> None:
    report = _engine().diagnose(
        _snapshot(
            network=[{"name": "wan", "up": True}],
            wifi=None,
        )
    )
    finding = report.findings[0]
    assert finding.severity == "warning"
    assert finding.title == "Missing WiFi"
    ok = _engine().diagnose(
        _snapshot(
            network=[{"name": "wan", "up": True}],
            wifi={"radios": ["radio0"], "client_count": 2},
        )
    )
    assert ok.findings == []


def test_unknown_values_report_info() -> None:
    report = _engine().diagnose(
        _snapshot(
            system={"hostname": "demo-router", "model": None, "firmware": ""},
            cpu={"usage_percent": "n/a", "cores": None},
        )
    )
    info = [f for f in report.findings if f.severity == "info"]
    assert info
    assert info[0].title == "Unknown router values"
    assert "system.model" in info[0].description
    assert "cpu.usage_percent" in info[0].description


def test_finding_to_dict() -> None:
    finding = Finding(
        severity="warning",
        category="router-health",
        title="High CPU utilization",
        description="CPU usage is high.",
        recommendation="Monitor CPU.",
    )
    assert finding.to_dict() == {
        "severity": "warning",
        "category": "router-health",
        "title": "High CPU utilization",
        "description": "CPU usage is high.",
        "recommendation": "Monitor CPU.",
    }
