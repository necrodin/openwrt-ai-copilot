"""AI router diagnosis: deterministic health findings from a RouterSnapshot.

The engine analyzes an existing :class:`RouterSnapshot` and produces a
structured :class:`DiagnosisReport` of findings. It is fully deterministic —
no LLM reasoning and no external APIs. It never executes Router Tools; it only
reads the snapshot it is given.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.router_snapshot import RouterSnapshot
from router_agent.model import WAN_PROTOS

Severity = Literal["info", "warning", "critical"]

# Deterministic thresholds for utilization checks.
_CPU_WARNING = 75.0
_CPU_CRITICAL = 90.0
_MEMORY_WARNING = 75.0
_MEMORY_CRITICAL = 90.0
_STORAGE_WARNING = 85.0
_STORAGE_CRITICAL = 95.0
_LOAD_WARNING = 1.0  # load_1 at least equal to core count
_LOAD_CRITICAL = 2.0  # load_1 at least double the core count

#: Filesystem types that are inherently read-only firmware images. Their
#: capacity is fixed at build time, so reported usage sitting at ~100% is normal
#: and never means writable free-space exhaustion. Squashfs/erofs/romfs are only
#: used for the read-only firmware root on OpenWrt; the writable part lives on
#: the overlay (jffs2/ubifs/ext4/overlayfs), which stays monitored.
_READONLY_IMAGE_FS = frozenset({"squashfs", "erofs", "romfs"})

_CATEGORY = "router-health"


@dataclass(frozen=True)
class Finding:
    """A single structured health finding."""

    severity: Severity
    category: str
    title: str
    description: str
    recommendation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class DiagnosisReport:
    """Structured output of a router diagnosis."""

    router_id: str
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "router_id": self.router_id,
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def render_markdown(self) -> str | None:
        """Render the report as markdown (``None`` when there are no findings)."""
        if not self.findings:
            return None
        lines = ["## Router Diagnosis"]
        for finding in self.findings:
            lines.append(
                f"- **[{finding.severity.upper()}] {finding.title}** — {finding.description}"
            )
            lines.append(f"  - Recommendation: {finding.recommendation}")
        return "\n".join(lines)


class RouterDiagnosisEngine:
    """Analyzes a :class:`RouterSnapshot` and returns a structured report."""

    def diagnose(
        self,
        snapshot: RouterSnapshot,
        router_id: str = "default",
    ) -> DiagnosisReport:
        """Run all checks against ``snapshot`` and return the report."""
        findings: list[Finding] = []
        findings.extend(self._check_offline(snapshot))
        findings.extend(self._check_cpu(snapshot))
        findings.extend(self._check_memory(snapshot))
        findings.extend(self._check_storage(snapshot))
        findings.extend(self._check_high_load(snapshot))
        findings.extend(self._check_missing_wan(snapshot))
        findings.extend(self._check_missing_wifi(snapshot))
        findings.extend(self._check_unknown_values(snapshot))
        return DiagnosisReport(router_id=router_id, findings=findings)

    # ------------------------------------------------------------------ #
    # Checks                                                            #
    # ------------------------------------------------------------------ #

    def _check_offline(self, snapshot: RouterSnapshot) -> list[Finding]:
        sections = (
            snapshot.system,
            snapshot.cpu,
            snapshot.memory,
            snapshot.storage,
            snapshot.network,
            snapshot.wifi,
        )
        if any(section not in (None, [], {}) for section in sections):
            return []
        return [
            Finding(
                severity="critical",
                category=_CATEGORY,
                title="Router is offline",
                description="No router state is available; every snapshot section is "
                "empty or missing.",
                recommendation="Check the router's power and network link, and confirm "
                "the data feed is connected.",
            )
        ]

    def _check_cpu(self, snapshot: RouterSnapshot) -> list[Finding]:
        usage = _num(snapshot.cpu.get("usage_percent")) if snapshot.cpu else None
        if usage is None:
            return []
        if usage >= _CPU_CRITICAL:
            return [
                Finding(
                    severity="critical",
                    category=_CATEGORY,
                    title="Critical CPU utilization",
                    description=f"CPU usage is at {usage:.1f}%, which is above the "
                    f"{_CPU_CRITICAL:.0f}% critical threshold.",
                    recommendation="Inspect running processes and services; consider "
                    "reducing load or upgrading the router.",
                )
            ]
        if usage >= _CPU_WARNING:
            return [
                Finding(
                    severity="warning",
                    category=_CATEGORY,
                    title="High CPU utilization",
                    description=f"CPU usage is at {usage:.1f}%, which is above the "
                    f"{_CPU_WARNING:.0f}% warning threshold.",
                    recommendation="Monitor CPU usage and identify any long-running "
                    "tasks or misbehaving services.",
                )
            ]
        return []

    def _check_memory(self, snapshot: RouterSnapshot) -> list[Finding]:
        used_percent = _num(snapshot.memory.get("used_percent")) if snapshot.memory else None
        if used_percent is None:
            return []
        if used_percent >= _MEMORY_CRITICAL:
            return [
                Finding(
                    severity="critical",
                    category=_CATEGORY,
                    title="Critical memory utilization",
                    description=f"Memory usage is at {used_percent:.1f}%, which is "
                    f"above the {_MEMORY_CRITICAL:.0f}% critical threshold.",
                    recommendation="Review running services for memory leaks; consider "
                    "restarting memory-heavy services.",
                )
            ]
        if used_percent >= _MEMORY_WARNING:
            return [
                Finding(
                    severity="warning",
                    category=_CATEGORY,
                    title="High memory utilization",
                    description=f"Memory usage is at {used_percent:.1f}%, which is "
                    f"above the {_MEMORY_WARNING:.0f}% warning threshold.",
                    recommendation="Monitor memory trends and investigate what is consuming RAM.",
                )
            ]
        return []

    def _check_storage(self, snapshot: RouterSnapshot) -> list[Finding]:
        mounts = snapshot.storage or []
        findings: list[Finding] = []
        for mount in mounts:
            if _is_readonly_firmware_mount(mount):
                continue
            use_percent = _num(mount.get("use_percent"))
            mountpoint = mount.get("mountpoint") or "?"
            if use_percent is None:
                continue
            if use_percent >= _STORAGE_CRITICAL:
                findings.append(
                    Finding(
                        severity="critical",
                        category=_CATEGORY,
                        title="Critical storage utilization",
                        description=f"Filesystem {mountpoint} is at {use_percent:.1f}% "
                        f"capacity, above the {_STORAGE_CRITICAL:.0f}% critical threshold.",
                        recommendation="Free up space on the mount by removing logs or "
                        "unneeded packages.",
                    )
                )
            elif use_percent >= _STORAGE_WARNING:
                findings.append(
                    Finding(
                        severity="warning",
                        category=_CATEGORY,
                        title="High storage utilization",
                        description=f"Filesystem {mountpoint} is at {use_percent:.1f}% "
                        f"capacity, above the {_STORAGE_WARNING:.0f}% warning threshold.",
                        recommendation="Review disk usage and clean up logs or caches.",
                    )
                )
        return findings

    def _check_high_load(self, snapshot: RouterSnapshot) -> list[Finding]:
        if snapshot.cpu is None:
            return []
        cores = _num(snapshot.cpu.get("cores"))
        load_1 = _num(snapshot.cpu.get("load_1"))
        if not cores or load_1 is None:
            return []
        ratio = load_1 / cores
        if ratio >= _LOAD_CRITICAL:
            return [
                Finding(
                    severity="critical",
                    category=_CATEGORY,
                    title="Critically high load",
                    description=f"Load average is {load_1:.2f} on {cores:.0f} cores "
                    f"({ratio:.1f}x), indicating severe overloading.",
                    recommendation="Investigate processes causing the load and stop or "
                    "throttle them.",
                )
            ]
        if ratio >= _LOAD_WARNING:
            return [
                Finding(
                    severity="warning",
                    category=_CATEGORY,
                    title="High load average",
                    description=f"Load average is {load_1:.2f} on {cores:.0f} cores "
                    f"({ratio:.1f}x), at or above the core count.",
                    recommendation="Monitor the load and check for busy processes.",
                )
            ]
        return []

    def _check_missing_wan(self, snapshot: RouterSnapshot) -> list[Finding]:
        interfaces = snapshot.network or []
        if not interfaces:
            return []
        if any(_is_wan(iface) for iface in interfaces):
            return []
        return [
            Finding(
                severity="warning",
                category=_CATEGORY,
                title="Missing WAN interface",
                description="No WAN interface was found among the reported network interfaces.",
                recommendation="Check the router's WAN port, cable, and PPPoE/DHCP configuration.",
            )
        ]

    def _check_missing_wifi(self, snapshot: RouterSnapshot) -> list[Finding]:
        interfaces = snapshot.network or []
        if not interfaces:
            return []
        wifi = snapshot.wifi
        if wifi is not None and (wifi.get("radios") or wifi.get("client_count")):
            return []
        return [
            Finding(
                severity="warning",
                category=_CATEGORY,
                title="Missing WiFi",
                description="No WiFi radios were detected on this router.",
                recommendation="Check whether wireless is enabled and configured on the router.",
            )
        ]

    def _check_unknown_values(self, snapshot: RouterSnapshot) -> list[Finding]:
        unknown: list[str] = []
        if snapshot.system is not None:
            for key in ("hostname", "model", "firmware"):
                if not snapshot.system.get(key):
                    unknown.append(f"system.{key}")
        if snapshot.cpu is not None:
            for key in ("usage_percent", "cores"):
                if _num(snapshot.cpu.get(key)) is None:
                    unknown.append(f"cpu.{key}")
        if snapshot.memory is not None:
            for key in ("used_percent", "total_kb"):
                if _num(snapshot.memory.get(key)) is None:
                    unknown.append(f"memory.{key}")
        for index, mount in enumerate(snapshot.storage or []):
            if _num(mount.get("use_percent")) is None:
                unknown.append(f"storage[{index}].use_percent")
        if not unknown:
            return []
        return [
            Finding(
                severity="info",
                category=_CATEGORY,
                title="Unknown router values",
                description="The following values are missing or unknown: "
                + ", ".join(unknown)
                + ".",
                recommendation="Re-collect the router snapshot or verify the data "
                "feed is complete.",
            )
        ]


def _num(value: Any) -> float | None:
    """Return ``value`` as a float when it is numeric, else ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _is_readonly_firmware_mount(mount: dict) -> bool:
    """True for a read-only firmware image mount that must not be diagnosed.

    A read-only squashfs/erofs/romfs filesystem (e.g. ``/rom`` on OpenWrt) is a
    fixed-size image whose 100% usage is expected — there is no writable space
    to free. The check is based on the filesystem type/capability (and the
    well-known ``/rom`` firmware mountpoint), never on the device model.
    """
    fs_type = str(mount.get("filesystem") or "").lower()
    if fs_type in _READONLY_IMAGE_FS:
        return True
    mountpoint = str(mount.get("mountpoint") or "")
    return mountpoint == "/rom"


def _is_wan(iface: dict) -> bool:
    """True for an interface whose name or proto marks it as the uplink/WAN.

    Names vary across firmware (``wan``, ``eth0.2``, ``wwan0``…), so an
    interface with a WAN-class proto counts even when the name never says
    ``wan`` (e.g. a VLAN-tagged or cellular uplink).
    """
    name = (str(iface.get("name") or "")).lower()
    if name == "wan" or "wan" in name:
        return True
    proto = iface.get("proto")
    return isinstance(proto, str) and proto in WAN_PROTOS
