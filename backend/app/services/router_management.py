"""Router management service: real administrative operations over SSH.

Provides the backend for Sprint 31's router console: package inventory with
upgrade detection (apk/opkg), ``logread``-based system logs, destructive and
restart actions with confirmation + progress, ``sysupgrade -b`` backups,
``sysupgrade -r`` restores, and a compressed diagnostic bundle.

Every operation opens its own short-lived SSH session built from the same
credentials the snapshot feed uses (``SnapshotService.active_connection`` or
the most recently saved router). Long-running operations run as background
jobs tracked by :class:`ManagementJobStore` so the API can report progress and
stream artifacts without blocking a request.
"""

from __future__ import annotations

import base64
import gzip
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.db.router_store import store as router_store
from app.services.router_action_guard import RouterActionGuard
from app.services.snapshot_service import RouterConnection
from router_agent.collectors.logs import parse_logread
from router_agent.transport.ssh import SSHTransport

logger = logging.getLogger(__name__)

# Short TTL for the package inventory so repeated page loads don't hammer SSH.
PACKAGE_CACHE_TTL_S = 30.0

# Many OpenWrt busy-box builds lack ``base64``/``od`` but ship ``hexdump`` and a
# multi-call ``printf``. Binary is therefore transferred as ``hexdump -C`` output
# for download and written back with ``printf '\xHH...'`` (in chunks) for upload.
_HEXDUMP_OFFSET_TOKENS = 4  # hexdump -C prefixes every line with an 8-digit offset.
# Per-``printf`` argument limit for the ``\xHH`` upload format (larger chunks are
# silently rejected by busy-box printf), expressed as hex characters.
_UPLOAD_CHUNK = 3_500

# Action name -> (shell command, dispatched in background?).
# Reboot/shutdown are dispatched as detached background jobs so the SSH channel
# is not torn down mid-command; restarts run inline and return when done.
_ASYNC_DISPATCH = True

ACTION_COMMANDS: dict[str, tuple[str, bool]] = {
    "reboot": ("reboot", _ASYNC_DISPATCH),
    "shutdown": ("poweroff || halt", _ASYNC_DISPATCH),
    "restart-network": ("/etc/init.d/network restart", False),
    "restart-wifi": ("/etc/init.d/wireless restart", False),
    "reload-wireless": ("/etc/init.d/wireless reload", False),
    "restart-firewall": ("/etc/init.d/firewall restart", False),
    "reload-firewall": ("/etc/init.d/firewall reload", False),
    "restart-dnsmasq": ("/etc/init.d/dnsmasq restart", False),
    "restart-dropbear": ("/etc/init.d/dropbear restart", False),
}

ACTION_LABELS: dict[str, str] = {
    "reboot": "Reboot",
    "shutdown": "Shutdown",
    "restart-network": "Restart Network",
    "restart-wifi": "Restart WiFi",
    "reload-wireless": "Reload Wireless",
    "restart-firewall": "Restart Firewall",
    "reload-firewall": "Reload Firewall",
    "restart-dnsmasq": "Restart DNSMasq",
    "restart-dropbear": "Restart Dropbear",
}

JobStatus = Literal["queued", "running", "succeeded", "failed"]
JobKind = Literal["action", "backup", "bundle", "restore"]

_EXIT_SENTINEL = "__AI_EXIT__="


class RouterManagementError(Exception):
    """No router connection is configured, or an operation could not run."""


@dataclass
class CommandResult:
    """Outcome of one remote shell command."""

    command: str
    ok: bool
    stdout: str = ""
    exit_code: int = 0
    duration_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "ok": self.ok,
            "stdout": self.stdout[:4000],
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


# --------------------------------------------------------------------------- #
# Job model                                                                   #
# --------------------------------------------------------------------------- #


@dataclass
class ManagementJob:
    """An in-flight management operation with progress + optional artifact."""

    id: str
    kind: JobKind
    status: JobStatus = "queued"
    message: str = "Queued"
    error: str | None = None
    result: dict[str, Any] | None = None
    pending_confirmation: bool = False
    artifact_name: str | None = None
    artifact_bytes: bytes | None = None
    artifact_media_type: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self, *, include_artifact: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "pending_confirmation": self.pending_confirmation,
            "created_at": self.created_at,
        }
        if include_artifact and self.artifact_name is not None:
            data["artifact"] = {
                "name": self.artifact_name,
                "media_type": self.artifact_media_type,
                "size": len(self.artifact_bytes) if self.artifact_bytes is not None else 0,
            }
        return data


class ManagementJobStore:
    """In-memory store of management jobs (no persistence)."""

    def __init__(self) -> None:
        self._jobs: dict[str, ManagementJob] = {}
        self._lock = threading.Lock()

    def create(self, kind: JobKind, *, message: str = "Queued") -> ManagementJob:
        job = ManagementJob(id=uuid.uuid4().hex[:12], kind=kind, message=message)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> ManagementJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def transition(
        self,
        job_id: str,
        status: JobStatus,
        *,
        message: str | None = None,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> ManagementJob:
        job = self.get(job_id)
        if job is None:
            raise RouterManagementError(f"unknown job: {job_id}")
        with self._lock:
            job.status = status
            if message is not None:
                job.message = message
            if error is not None:
                job.error = error
            if result is not None:
                job.result = result
        return job

    def attach_artifact(
        self,
        job_id: str,
        *,
        name: str,
        data: bytes,
        media_type: str,
    ) -> ManagementJob:
        job = self.get(job_id)
        if job is None:
            raise RouterManagementError(f"unknown job: {job_id}")
        with self._lock:
            job.artifact_name = name
            job.artifact_bytes = data
            job.artifact_media_type = media_type
        return job

    def mark_pending(self, job_id: str, *, message: str) -> ManagementJob:
        job = self.get(job_id)
        if job is None:
            raise RouterManagementError(f"unknown job: {job_id}")
        with self._lock:
            job.pending_confirmation = True
            job.message = message
        return job


# --------------------------------------------------------------------------- #
# Service                                                                    #
# --------------------------------------------------------------------------- #


class RouterManagementService:
    """Executes router management operations over SSH with progress reporting."""

    def __init__(
        self,
        *,
        resolve_connection: Any | None = None,
        job_store: ManagementJobStore | None = None,
    ) -> None:
        self._resolve_connection = resolve_connection or (lambda: None)
        self._jobs = job_store if job_store is not None else ManagementJobStore()
        self._guard = RouterActionGuard()
        self._packages_cache: dict[str, Any] = {}
        self._packages_cache_at: float = 0.0

    @property
    def job_store(self) -> ManagementJobStore:
        """The job store backing this service."""
        return self._jobs

    # -- connection -------------------------------------------------------- #

    def connection(self) -> RouterConnection:
        """Resolve the active router connection or raise a friendly error."""
        connection = self._resolve_connection()
        if connection is not None:
            return connection
        record = router_store.get_most_recent()
        if record is not None:
            return RouterConnection(
                host=record.host,
                port=record.port,
                username=record.username,
                password=record.password,
                private_key=record.private_key,
                device_id=record.device_id,
            )
        raise RouterManagementError(
            "No router is connected. Save a router from the onboarding wizard first."
        )

    def open(self) -> SSHTransport:
        """Open a fresh SSH session to the configured router."""
        conn = self.connection()
        return SSHTransport(
            conn.host,
            port=conn.port,
            username=conn.username,
            password=conn.password or None,
            private_key=conn.private_key or None,
            host_key_policy="auto",
            command_timeout=60.0,
        )

    # -- command runner ---------------------------------------------------- #

    def run(
        self,
        transport: SSHTransport,
        command: str,
        *,
        timeout: float | None = None,
    ) -> CommandResult:
        """Run a command, capturing merged stdout/stderr and the exit code."""
        started = time.monotonic()
        wrapped = f"( {command} ) 2>&1; echo; echo {_EXIT_SENTINEL}$?"
        try:
            output = transport.run(wrapped, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - surfaced as a command failure
            duration_ms = int((time.monotonic() - started) * 1000)
            return CommandResult(
                command=command,
                ok=False,
                stdout="",
                exit_code=1,
                duration_ms=duration_ms,
                error=str(exc),
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        lines = output.splitlines()
        exit_code = 0
        stdout = output
        if lines and lines[-1].startswith(_EXIT_SENTINEL):
            try:
                exit_code = int(lines[-1].split("=", 1)[1])
            except ValueError:
                exit_code = 1
            stdout = "\n".join(lines[:-1])
        return CommandResult(
            command=command,
            ok=exit_code == 0,
            stdout=stdout,
            exit_code=exit_code,
            duration_ms=duration_ms,
        )

    # -- packages ---------------------------------------------------------- #

    def detect_package_manager(self, transport: SSHTransport) -> str:
        """Return ``"apk"``, ``"opkg"``, or ``"unknown"`` for the device."""
        if self.run(transport, "command -v apk").ok:
            return "apk"
        if self.run(transport, "command -v opkg").ok:
            return "opkg"
        return "unknown"

    @staticmethod
    def _split_apk_pkgid(pkgid: str) -> tuple[str, str]:
        """Split an apk package id ``name-version`` (version starts with a digit)."""
        parts = pkgid.split("-")
        for index in range(1, len(parts)):
            if parts[index][:1].isdigit():
                return "-".join(parts[:index]), "-".join(parts[index:])
        return pkgid, ""

    @staticmethod
    def _parse_apk_installed(text: str) -> list[tuple[str, str]]:
        packages: list[tuple[str, str]] = []
        for line in text.splitlines():
            pkgid = line.strip().split()[0] if line.strip() else ""
            if not pkgid:
                continue
            name, version = RouterManagementService._split_apk_pkgid(pkgid)
            if name:
                packages.append((name, version))
        return packages

    @staticmethod
    def _parse_apk_upgradable(text: str) -> dict[str, str]:
        """Map package name -> available version for ``apk list --upgradable``."""
        upgrades: dict[str, str] = {}
        match_braces = re.compile(r"\{([^{}]+)\}")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            pkgid = line.split()[0]
            name, _ = RouterManagementService._split_apk_pkgid(pkgid)
            if not name:
                continue
            found = match_braces.search(line)
            if found:
                upgrades[name] = found.group(1).strip()
        return upgrades

    @staticmethod
    def _parse_opkg_installed(text: str) -> list[tuple[str, str]]:
        packages: list[tuple[str, str]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            name, sep, rest = line.partition(" - ")
            if not sep:
                continue
            version = rest.partition(" - ")[0].strip()
            packages.append((name.strip(), version))
        return packages

    @staticmethod
    def _parse_opkg_upgradable(text: str) -> dict[str, tuple[str, str]]:
        """Map package name -> (installed, available) for ``opkg list-upgradable``."""
        upgrades: dict[str, tuple[str, str]] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split(" - ")]
            if len(parts) >= 3:
                upgrades[parts[0]] = (parts[1], parts[2])
            elif len(parts) == 2:
                upgrades[parts[0]] = (parts[0], parts[1])
        return upgrades

    def _collect_packages(self) -> dict[str, Any]:
        transport = self.open()
        try:
            manager = self.detect_package_manager(transport)
            if manager == "apk":
                installed = self._parse_apk_installed(
                    self.run(transport, "apk list --installed").stdout
                )
                upgrades = self._parse_apk_upgradable(
                    self.run(transport, "apk list --upgradable").stdout
                )
            elif manager == "opkg":
                installed = self._parse_opkg_installed(
                    self.run(transport, "opkg list-installed").stdout
                )
                opkg_upgrades = self._parse_opkg_upgradable(
                    self.run(transport, "opkg list-upgradable").stdout
                )
                upgrades = {name: available for name, (_i, available) in opkg_upgrades.items()}
            else:
                installed, upgrades = [], {}
            packages = [
                {"name": name, "version": version, "upgrade": upgrades.get(name)}
                for name, version in installed
            ]
            packages.sort(key=lambda pkg: pkg["name"].lower())
            return {
                "manager": manager,
                "count": len(packages),
                "upgrades_available": sum(1 for pkg in packages if pkg["upgrade"]),
                "generated_at": datetime.now(UTC).isoformat(),
                "packages": packages,
            }
        finally:
            transport.close()

    def packages(self, *, refresh: bool = False) -> dict[str, Any]:
        """Return the package inventory, using a short TTL cache unless refreshing."""
        now = time.monotonic()
        cached_fresh = (
            self._packages_cache and (now - self._packages_cache_at) < PACKAGE_CACHE_TTL_S
        )
        if not refresh and cached_fresh:
            return dict(self._packages_cache)
        data = self._collect_packages()
        self._packages_cache = data
        self._packages_cache_at = time.monotonic()
        return data

    # -- logs -------------------------------------------------------------- #

    def read_logs(self, lines: int = 500) -> dict[str, Any]:
        """Read recent ``logread`` entries from the router."""
        transport = self.open()
        try:
            n = max(1, min(5000, int(lines)))
            result = self.run(transport, f"logread -l {n}")
            if not result.ok:
                raise RouterManagementError(f"logread failed (exit {result.exit_code})")
            entries = [
                {
                    "raw": entry.raw,
                    "timestamp": entry.timestamp,
                    "facility": entry.facility,
                    "priority": entry.priority,
                    "ident": entry.ident,
                    "message": entry.message,
                }
                for entry in parse_logread(result.stdout)
            ]
            return {"logs": entries, "generated_at": datetime.now(UTC).isoformat()}
        finally:
            transport.close()

    # -- actions ----------------------------------------------------------- #

    def action(self, action_name: str) -> dict[str, Any]:
        """Execute a management action and return a structured result."""
        if action_name not in ACTION_COMMANDS:
            raise RouterManagementError(f"unknown action: {action_name}")
        command, async_dispatch = ACTION_COMMANDS[action_name]
        decision = self._guard.evaluate(action_name)
        transport = self.open()
        try:
            full = f"( sleep 1; {command} ) >/dev/null 2>&1 &" if async_dispatch else command
            result = self.run(transport, full, timeout=45.0 if async_dispatch else 90.0)
            label = ACTION_LABELS.get(action_name, action_name)
            if async_dispatch:
                return {
                    "action": action_name,
                    "label": label,
                    "ok": True,
                    "message": f"{label} dispatched to the router.",
                    "detail": result.to_dict(),
                    "risk": decision.risk,
                }
            if not result.ok:
                return {
                    "action": action_name,
                    "label": label,
                    "ok": False,
                    "message": f"{label} failed (exit {result.exit_code}).",
                    "detail": result.to_dict(),
                    "risk": decision.risk,
                }
            return {
                "action": action_name,
                "label": label,
                "ok": True,
                "message": f"{label} completed successfully.",
                "detail": result.to_dict(),
                "risk": decision.risk,
            }
        finally:
            transport.close()

    # -- firewall -------------------------------------------------------- #

    _SECTION_PATTERN = re.compile(r"^[A-Za-z0-9_@.\-]+$")

    def toggle_firewall_rule(self, *, section: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable one UCI firewall section and reload the service."""
        if not section or not self._SECTION_PATTERN.match(section):
            raise RouterManagementError("Invalid firewall section identifier.")
        value = "1" if enabled else "0"
        command = (
            f"uci set firewall.{section}.enabled='{value}' && "
            "uci commit firewall && /etc/init.d/firewall reload"
        )
        transport = self.open()
        try:
            result = self.run(transport, command, timeout=90.0)
            label = "Enable" if enabled else "Disable"
            if not result.ok:
                return {
                    "ok": False,
                    "label": label,
                    "message": f"{label} failed (exit {result.exit_code}).",
                    "detail": result.to_dict(),
                }
            return {
                "ok": True,
                "label": label,
                "message": f"Firewall rule {label}d and reloaded.",
                "detail": result.to_dict(),
            }
        finally:
            transport.close()

    def run_firewall_toggle_job(
        self,
        job_id: str,
        *,
        section: str,
        enabled: bool,
    ) -> ManagementJob:
        """Execute a firewall rule toggle inside a tracked job."""
        action_label = "Enable" if enabled else "Disable"
        self._jobs.transition(job_id, "running", message=f"{action_label}ing firewall rule…")
        try:
            result = self.toggle_firewall_rule(section=section, enabled=enabled)
            self._jobs.transition(job_id, "succeeded", message=result["message"], result=result)
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Firewall rule toggle failed for %r", section)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"Firewall rule could not be {action_label.lower()}d.",
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    # -- wireless -------------------------------------------------------- #

    def toggle_wireless_ssid(self, *, section: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable one UCI ``wifi-iface`` section and reload wireless."""
        if not section or not self._SECTION_PATTERN.match(section):
            raise RouterManagementError("Invalid wireless section identifier.")
        value = "1" if not enabled else "0"
        command = (
            f"uci set wireless.{section}.disabled='{value}' && "
            "uci commit wireless && /etc/init.d/wireless reload"
        )
        transport = self.open()
        try:
            result = self.run(transport, command, timeout=90.0)
            label = "Enable" if enabled else "Disable"
            if not result.ok:
                return {
                    "ok": False,
                    "label": label,
                    "message": f"{label} failed (exit {result.exit_code}).",
                    "detail": result.to_dict(),
                }
            return {
                "ok": True,
                "label": label,
                "message": f"SSID {label}d and wireless reloaded.",
                "detail": result.to_dict(),
            }
        finally:
            transport.close()

    def run_wireless_toggle_job(
        self,
        job_id: str,
        *,
        section: str,
        enabled: bool,
    ) -> ManagementJob:
        """Execute a wireless SSID enable/disable inside a tracked job."""
        action_label = "Enable" if enabled else "Disable"
        self._jobs.transition(job_id, "running", message=f"{action_label}ing SSID…")
        try:
            result = self.toggle_wireless_ssid(section=section, enabled=enabled)
            self._jobs.transition(job_id, "succeeded", message=result["message"], result=result)
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Wireless SSID toggle failed for %r", section)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"SSID could not be {action_label.lower()}d.",
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    # -- backup ------------------------------------------------------------ #

    @staticmethod
    def _parse_hexdump(text: str) -> bytes:
        """Reconstruct bytes from ``hexdump -C`` output (offsets + ``|ascii|``)."""
        chunks: list[bytes] = []
        for line in text.splitlines():
            if "|" not in line:
                continue
            left = line.split("|", 1)[0]
            tokens = re.findall(r"[0-9a-f]{2}", left)
            tokens = tokens[_HEXDUMP_OFFSET_TOKENS:]
            if tokens:
                chunks.append(bytes(int(tok, 16) for tok in tokens))
        return b"".join(chunks)

    @staticmethod
    def _binary_to_printf_hex(data: bytes) -> str:
        """Render bytes as a busy-box ``printf`` ``\\xHH``format argument."""
        return "".join(f"\\x{b:02x}" for b in data)

    def router_hostname(self, transport: SSHTransport) -> str:
        """Best-effort hostname, only ever from a clean stdout read."""
        out = self.run(
            transport,
            "cat /etc/hostname 2>/dev/null "
            "|| uci get system.@system[0].hostname 2>/dev/null "
            "|| echo router",
        ).stdout.strip()
        return out.splitlines()[0].strip() if out else "router"

    def build_backup(self) -> tuple[str, bytes]:
        """Create a ``sysupgrade -b`` backup archive (fallback: /etc/config tar)."""
        transport = self.open()
        try:
            hostname = self.router_hostname(transport)
            ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            filename = f"openwrt-{hostname}-backup-{ts}.tar.gz"
            probe = self.run(transport, "command -v sysupgrade")
            if probe.ok:
                remote = "/tmp/ai-sysupgrade-backup.tar.gz"
                step = self.run(
                    transport,
                    f"sysupgrade -b {remote} && echo '__AI_BYTES__='$(wc -c < {remote}) "
                    f"&& hexdump -C {remote} && rm -f {remote}",
                    timeout=120.0,
                )
                if not step.ok or not re.search(r"__AI_BYTES__=\d+", step.stdout):
                    raise RouterManagementError("sysupgrade -b produced no backup archive.")
                data = self._parse_hexdump(step.stdout)
            else:
                remote = "/tmp/ai-config-backup.tar.gz"
                step = self.run(
                    transport,
                    f"tar -czf {remote} /etc/config && echo '__AI_BYTES__='$(wc -c < {remote}) "
                    f"&& hexdump -C {remote} && rm -f {remote}",
                    timeout=120.0,
                )
                if not step.ok or not re.search(r"__AI_BYTES__=\d+", step.stdout):
                    raise RouterManagementError("backup generation failed on the router.")
                data = self._parse_hexdump(step.stdout)
            if not data:
                raise RouterManagementError("The backup archive came back empty.")
            return filename, data
        finally:
            transport.close()

    # -- restore ----------------------------------------------------------- #

    def stage_restore(self, *, filename: str, content_b64: str) -> tuple[str, bytes]:
        """Validate an uploaded backup and stage it for an explicit restore."""
        try:
            data = base64.b64decode(content_b64)
        except Exception as exc:  # noqa: BLE001
            raise RouterManagementError("The uploaded file is not valid base64.") from exc
        if not data.startswith(b"\x1f\x8b"):
            raise RouterManagementError(
                "The uploaded file is not a gzip archive — sysupgrade backups are .tar.gz files."
            )
        safe_name = Path(filename).name or "restore.tar.gz"
        return safe_name, data

    def execute_restore(self, *, filename: str, data: bytes) -> dict[str, Any]:
        """Push a staged backup to the router and start ``sysupgrade -r``."""
        transport = self.open()
        try:
            remote = "/tmp/ai-restore-backup.tar.gz"
            if not self.run(transport, f"rm -f {remote}").ok:
                raise RouterManagementError("Could not clear a previous upload on the router.")
            hexes = RouterManagementService._binary_to_printf_hex(data)
            for index in range(0, len(hexes), _UPLOAD_CHUNK):
                chunk = hexes[index : index + _UPLOAD_CHUNK]
                op = ">" if index == 0 else ">>"
                step = self.run(
                    transport,
                    f"printf '{chunk}' {op} {remote}",
                    timeout=120.0,
                )
                if not step.ok:
                    raise RouterManagementError(
                        f"Could not upload the backup to the router (exit {step.exit_code})."
                    )
            check = self.run(transport, "wc -c < " + remote)
            if not check.ok or check.stdout.split()[0] != str(len(data)):
                raise RouterManagementError(
                    "The uploaded backup size does not match — restore aborted."
                )
            if not self.run(transport, f"gzip -t {remote}").ok:
                raise RouterManagementError(
                    "The uploaded backup is not a valid gzip archive — restore aborted."
                )
            probe = self.run(transport, "command -v sysupgrade")
            if not probe.ok:
                raise RouterManagementError(
                    "sysupgrade is not available on this device; restore cannot run."
                )
            dispatch = self.run(
                transport,
                f"( sleep 1; sysupgrade -r {remote} ) >/dev/null 2>&1 &",
                timeout=45.0,
            )
            return {
                "ok": dispatch.ok,
                "message": (
                    "Restore initiated — the router will reboot with the uploaded configuration."
                ),
                "detail": dispatch.to_dict(),
                "filename": filename,
            }
        finally:
            transport.close()

    # -- diagnostic bundle -------------------------------------------------- #

    def build_bundle(self) -> tuple[str, bytes]:
        """Collect a diagnostics text bundle and gzip it for download."""
        transport = self.open()
        try:
            hostname = self.router_hostname(transport)
            ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            filename = f"diagnostics-{hostname}-{ts}.txt.gz"
            sections: list[tuple[str, str]] = [
                ("System Information", "cat /etc/openwrt_release; echo; uname -a; echo; uptime"),
                ("Boot Messages (dmesg)", "dmesg"),
                ("Filesystems (df)", "df -h"),
                ("Memory (free)", "free"),
                ("Network (ip addr)", "ip addr"),
                ("Ubus", "ubus list 2>&1; echo; ubus -S call system board 2>&1"),
                ("UCI Configuration", "uci export"),
                ("Installed Packages", "apk list --installed 2>/dev/null || opkg list-installed"),
                ("System Log (logread)", "logread -l 1000"),
            ]
            body: list[str] = []
            for title, command in sections:
                body.append("=" * 64)
                body.append(f"### {title}")
                body.append("=" * 64)
                result = self.run(transport, command, timeout=90.0)
                body.append(result.stdout.strip() or "(no output / command failed)")
                body.append("")
            text = "\n".join(body)
            return filename, gzip.compress(text.encode("utf-8"), mtime=0)
        finally:
            transport.close()

    # -- job wrappers ------------------------------------------------------ #

    def run_action_job(self, job_id: str, action_name: str) -> ManagementJob:
        """Execute a management action inside a tracked job."""
        label = ACTION_LABELS.get(action_name, action_name)
        self._jobs.transition(job_id, "running", message=f"Executing {label}…")
        try:
            result = self.action(action_name)
            self._jobs.transition(job_id, "succeeded", message=result["message"], result=result)
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Management action %r failed", action_name)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"{label} could not be executed.",
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    def run_backup_job(self, job_id: str) -> ManagementJob:
        """Create a backup archive and attach it to the job."""
        self._jobs.transition(job_id, "running", message="Creating configuration backup…")
        try:
            filename, data = self.build_backup()
            self._jobs.attach_artifact(
                job_id, name=filename, data=data, media_type="application/gzip"
            )
            self._jobs.transition(
                job_id,
                "succeeded",
                message=f"Backup ready ({len(data)} bytes).",
                result={"filename": filename, "size": len(data)},
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Backup job failed")
            self._jobs.transition(
                job_id, "failed", error=str(exc), message="Backup generation failed."
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    def run_bundle_job(self, job_id: str) -> ManagementJob:
        """Build the diagnostic bundle and attach it to the job."""
        self._jobs.transition(job_id, "running", message="Collecting diagnostics…")
        try:
            filename, data = self.build_bundle()
            self._jobs.attach_artifact(
                job_id, name=filename, data=data, media_type="application/gzip"
            )
            self._jobs.transition(
                job_id,
                "succeeded",
                message=f"Diagnostic bundle ready ({len(data)} bytes).",
                result={"filename": filename, "size": len(data)},
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Diagnostic bundle job failed")
            self._jobs.transition(
                job_id, "failed", error=str(exc), message="Diagnostic bundle generation failed."
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    def confirm_restore_job(self, job_id: str) -> ManagementJob:
        """Execute a staged restore (writes the file, starts ``sysupgrade -r``)."""
        job = self._jobs.get(job_id)
        if job is None:
            raise RouterManagementError(f"unknown job: {job_id}")
        if not job.pending_confirmation:
            raise RouterManagementError("This restore job is not awaiting confirmation.")
        staged_filename = (job.result or {}).get("staged_filename") or "restore.tar.gz"
        staged_b64 = (job.result or {}).get("staged_b64") or ""
        self._jobs.transition(job_id, "running", message="Uploading backup and starting restore…")
        try:
            data = base64.b64decode(staged_b64)
            result = self.execute_restore(filename=staged_filename, data=data)
            self._jobs.transition(
                job_id,
                "succeeded",
                message=result["message"],
                result={"filename": staged_filename, **result},
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Restore job failed")
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message="Restore could not be executed.",
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    def stage_restore_job(
        self,
        job_id: str,
        *,
        filename: str,
        content_b64: str,
    ) -> ManagementJob:
        """Validate an uploaded backup and hold it pending explicit confirmation."""
        safe_name, data = self.stage_restore(filename=filename, content_b64=content_b64)
        self._jobs.transition(
            job_id,
            "running",
            message="Staging backup for restore…",
            result={
                "staged_filename": safe_name,
                "staged_b64": content_b64,
                "size": len(data),
            },
        )
        self._jobs.mark_pending(
            job_id,
            message="Backup uploaded and validated. Confirm to restore the router.",
        )
        return self._jobs.get(job_id)  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Module-level singleton                                                      #
# --------------------------------------------------------------------------- #

_service: RouterManagementService | None = None
_service_lock = threading.Lock()


def get_management_service() -> RouterManagementService:
    """Return the shared management service instance."""
    global _service
    with _service_lock:
        if _service is None:
            _service = RouterManagementService()
        return _service


__all__ = [
    "ManagementJob",
    "ManagementJobStore",
    "RouterManagementError",
    "RouterManagementService",
    "get_management_service",
]
