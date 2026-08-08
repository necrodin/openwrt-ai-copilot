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
import ipaddress
import json
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
# ``opkg list`` is expensive; cache the raw output for searches.
PACKAGE_LIST_TTL_S = 120.0

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
    "reload-vpn": ("/etc/init.d/openvpn reload", False),
    "restart-vpn": ("/etc/init.d/openvpn restart", False),
    "reload-dhcp": ("/etc/init.d/dnsmasq reload", False),
    "restart-dhcp": ("/etc/init.d/dnsmasq restart", False),
    "reload-network": ("/etc/init.d/network reload", False),
    # Restart whichever monitoring daemon is installed and enabled (best-effort).
    "restart-monitoring": (
        "for s in netdata collectd telegraf zabbix_agentd monit; do "
        "[ -x /etc/init.d/$s ] && /etc/init.d/$s enabled >/dev/null 2>&1 && "
        "/etc/init.d/$s restart >/dev/null 2>&1; done; true",
        False,
    ),
    "restart-ntp": ("/etc/init.d/sysntpd restart", False),
    "sync-time": (
        "ntpd -q -n -p 1.openwrt.pool.ntp.org 2>/dev/null || "
        "ntpd -q -n 2>/dev/null; hwclock -s 2>/dev/null; true",
        _ASYNC_DISPATCH,
    ),
    # Erase the persisted /etc/config tree; the next boot re-generates factory
    # defaults. Dispatched in the background so the SSH channel survives.
    "factory-reset": (
        "for f in /etc/config/*; do [ -f \"$f\" ] && rm -f \"$f\"; done; "
        "sync; reboot",
        _ASYNC_DISPATCH,
    ),
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
    "reload-vpn": "Reload VPN",
    "restart-vpn": "Restart VPN",
    "reload-dhcp": "Reload DHCP",
    "restart-dhcp": "Restart DHCP",
    "reload-network": "Reload Network",
    "restart-monitoring": "Restart Monitoring",
    "restart-ntp": "Restart NTP",
    "sync-time": "Sync Time",
    "factory-reset": "Factory Reset",
}

JobStatus = Literal["queued", "running", "succeeded", "failed"]
JobKind = Literal[
    "action",
    "backup",
    "bundle",
    "restore",
    "firewall",
    "wireless",
    "vpn",
    "dhcp",
    "dns",
    "network",
    "system",
    "packages",
    "storage",
    "services",
]

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
        self._opkg_list_text: str = ""
        self._opkg_list_at: float = 0.0

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
                status: dict[str, dict[str, Any]] = {}
            elif manager == "opkg":
                installed = self._parse_opkg_installed(
                    self.run(transport, "opkg list-installed").stdout
                )
                opkg_upgrades = self._parse_opkg_upgradable(
                    self.run(transport, "opkg list-upgradable").stdout
                )
                upgrades = {name: available for name, (_i, available) in opkg_upgrades.items()}
                status = self._parse_opkg_status(
                    self.run(
                        transport,
                        "opkg status 2>/dev/null || cat /usr/lib/opkg/status 2>/dev/null",
                    ).stdout
                )
            else:
                installed, upgrades, status = [], {}, {}
            packages: list[dict[str, Any]] = []
            for name, version in installed:
                details = status.get(name, {})
                packages.append(
                    {
                        "name": name,
                        "version": details.get("version") or version,
                        "upgrade": upgrades.get(name),
                        "size": details.get("size"),
                        "architecture": details.get("architecture"),
                        "description": details.get("description"),
                        "depends": details.get("depends", []),
                    }
                )
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

    @staticmethod
    def _parse_opkg_stanzas(text: str) -> list[dict[str, str]]:
        """Parse ``opkg status``/``opkg info`` stanzas into key/value dicts."""
        stanzas: list[dict[str, str]] = []
        current: dict[str, str] = {}
        last_key: str | None = None
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                if current:
                    stanzas.append(current)
                    current = {}
                last_key = None
                continue
            if line[:1] in (" ", "\t"):
                if last_key is not None and last_key in current:
                    current[last_key] = f"{current[last_key]} {line.strip()}"
                continue
            key, sep, value = line.partition(":")
            if not sep:
                continue
            last_key = key
            current[key] = value.strip()
        if current:
            stanzas.append(current)
        return stanzas

    @staticmethod
    def _parse_opkg_status(text: str) -> dict[str, dict[str, Any]]:
        """Map package name -> {version, architecture, size, depends, description}."""
        result: dict[str, dict[str, Any]] = {}
        for stanza in RouterManagementService._parse_opkg_stanzas(text):
            name = stanza.get("Package", "")
            if not name:
                continue
            size_raw = stanza.get("Installed-Size", "")
            result[name] = {
                "version": stanza.get("Version", ""),
                "architecture": stanza.get("Architecture", ""),
                "size": int(size_raw) if size_raw.isdigit() else None,
                "depends": [
                    dep.strip() for dep in stanza.get("Depends", "").split(",") if dep.strip()
                ],
                "description": stanza.get("Description", ""),
                "section": stanza.get("Section", ""),
            }
        return result

    @staticmethod
    def _sh_quote(value: str) -> str:
        """Single-quote a shell argument safely."""
        return "'" + value.replace("'", "'\\''") + "'"

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    _PKG_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._+@~/-]{1,128}$")

    def _pkg_run(self, command: str, timeout: float = 300.0) -> CommandResult:
        transport = self.open()
        try:
            return self.run(transport, command, timeout=timeout)
        finally:
            transport.close()

    def _pkg_manager(self) -> str:
        transport = self.open()
        try:
            return self.detect_package_manager(transport)
        finally:
            transport.close()

    def feeds(self) -> dict[str, Any]:
        """Return the configured package feeds and the last list-update time."""
        manager = self._pkg_manager()
        feeds: list[dict[str, str]] = []
        last_update: int | None = None
        if manager == "opkg":
            for path in ("/etc/opkg/distfeeds.conf", "/etc/opkg/customfeeds.conf"):
                text = self._pkg_run(f"cat {path} 2>/dev/null", timeout=30.0).stdout
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) >= 3:
                        feeds.append(
                            {
                                "type": parts[0],
                                "name": parts[1],
                                "url": parts[2],
                                "source": path,
                            }
                        )
            marker = self._pkg_run(
                "ls -1t /var/opkg-lists/* 2>/dev/null | head -1",
                timeout=30.0,
            ).stdout.strip()
            if marker:
                mtime = self._pkg_run(
                    f"stat -c %Y {self._sh_quote(marker)} 2>/dev/null",
                    timeout=30.0,
                ).stdout.strip()
                if mtime.isdigit():
                    last_update = int(mtime)
        elif manager == "apk":
            text = self._pkg_run("cat /etc/apk/repositories 2>/dev/null", timeout=30.0).stdout
            for index, line in enumerate(text.splitlines()):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                feeds.append(
                    {
                        "type": "src",
                        "name": f"repo{index}",
                        "url": line,
                        "source": "/etc/apk/repositories",
                    }
                )
            marker = self._pkg_run(
                "ls -1t /var/cache/apk/*APKINDEX* 2>/dev/null | head -1",
                timeout=30.0,
            ).stdout.strip()
            if marker:
                mtime = self._pkg_run(
                    f"stat -c %Y {self._sh_quote(marker)} 2>/dev/null",
                    timeout=30.0,
                ).stdout.strip()
                if mtime.isdigit():
                    last_update = int(mtime)
        else:
            raise RouterManagementError("No supported package manager found.")
        return {
            "manager": manager,
            "count": len(feeds),
            "last_update": last_update,
            "feeds": feeds,
        }

    def update_feeds(self) -> dict[str, Any]:
        """Refresh the package index lists from all configured feeds."""
        manager = self._pkg_manager()
        if manager == "apk":
            result = self._pkg_run("apk update", timeout=600.0)
        elif manager == "opkg":
            result = self._pkg_run("opkg update", timeout=600.0)
        else:
            raise RouterManagementError("No supported package manager found.")
        self._opkg_list_text = ""
        self._opkg_list_at = 0.0
        return {
            "ok": result.ok,
            "message": (
                "Package lists updated."
                if result.ok
                else "Package lists could not be updated."
            ),
            "detail": result.to_dict(),
        }

    def search_packages(self, query: str, limit: int = 200) -> dict[str, Any]:
        """Search the repository for available packages by name or description."""
        needle = query.strip()
        if not needle:
            raise RouterManagementError("A search query is required.")
        manager = self._pkg_manager()
        results: list[dict[str, Any]] = []
        if manager == "apk":
            text = self._pkg_run(
                f"apk search -v -q {self._sh_quote(needle)}",
                timeout=60.0,
            ).stdout
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                name, version = RouterManagementService._split_apk_pkgid(line.split()[0])
                results.append({"name": name, "version": version, "description": ""})
        elif manager == "opkg":
            now = time.monotonic()
            if not self._opkg_list_text or (now - self._opkg_list_at) >= PACKAGE_LIST_TTL_S:
                self._opkg_list_text = self._pkg_run("opkg list", timeout=300.0).stdout
                self._opkg_list_at = time.monotonic()
            haystack = needle.lower()
            for line in self._opkg_list_text.splitlines():
                name, sep, rest = line.partition(" - ")
                if not sep:
                    continue
                name = name.strip()
                version = rest.partition(" - ")[0].strip()
                description = rest.partition(" - ")[2].strip()
                if haystack in name.lower() or haystack in description.lower():
                    results.append(
                        {"name": name, "version": version, "description": description}
                    )
        else:
            raise RouterManagementError("No supported package manager found.")
        return {
            "query": needle,
            "manager": manager,
            "count": len(results[:limit]),
            "results": results[:limit],
        }

    @staticmethod
    def _parse_apk_info(text: str, name: str) -> dict[str, Any]:
        """Best-effort parse of ``apk info -a <name>`` output."""
        version = ""
        description = ""
        installed_size: int | None = None
        download_size: int | None = None
        depends: list[str] = []
        pending: str | None = None
        for raw in text.splitlines():
            line = raw.rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Installed:"):
                value = stripped.partition(":")[2].strip()
                if value.isdigit():
                    installed_size = int(value)
                pending = None
                continue
            if stripped.startswith("Size:"):
                value = stripped.partition(":")[2].strip()
                if value.isdigit():
                    download_size = int(value)
                pending = None
                continue
            if line[:1] in (" ", "\t"):
                if pending == "description":
                    description = f"{description} {stripped}".strip()
                elif pending == "depends" and not stripped.startswith(("so:", "pc:", "rr:")):
                    depends.append(stripped)
                continue
            if stripped.endswith("description:"):
                pending = "description"
                header = stripped.rpartition(":")[0].strip()
                if header:
                    candidate, parsed_version = RouterManagementService._split_apk_pkgid(header)
                    if candidate == name and not version:
                        version = parsed_version
            elif stripped.endswith("depends:"):
                pending = "depends"
                value = stripped.rpartition(":")[2].strip()
                if value:
                    depends.append(value)
            else:
                pending = None
        return {
            "version": version,
            "architecture": "",
            "description": description,
            "homepage": "",
            "maintainer": "",
            "license": "",
            "depends": [dep for dep in depends if dep],
            "section": None,
            "installed_size": installed_size,
            "download_size": download_size,
        }

    def package_details(self, name: str) -> dict[str, Any]:
        """Return detailed metadata for a single package."""
        if not self._PKG_NAME_PATTERN.match(name):
            raise RouterManagementError("Invalid package name.")
        manager = self._pkg_manager()
        if manager == "opkg":
            text = self._pkg_run(f"opkg info {self._sh_quote(name)}", timeout=60.0).stdout
            for stanza in self._parse_opkg_stanzas(text):
                if stanza.get("Package") != name:
                    continue
                size_raw = stanza.get("Size", "")
                installed_raw = stanza.get("Installed-Size", "")
                return {
                    "name": name,
                    "version": stanza.get("Version", ""),
                    "architecture": stanza.get("Architecture", ""),
                    "description": stanza.get("Description", ""),
                    "homepage": stanza.get("Homepage", ""),
                    "maintainer": stanza.get("Maintainer", ""),
                    "license": stanza.get("License", ""),
                    "depends": [
                        dep.strip()
                        for dep in stanza.get("Depends", "").split(",")
                        if dep.strip()
                    ],
                    "section": stanza.get("Section", ""),
                    "installed_size": (
                        int(installed_raw) if installed_raw.isdigit() else None
                    ),
                    "download_size": int(size_raw) if size_raw.isdigit() else None,
                }
            raise RouterManagementError(f"Package '{name}' was not found.")
        if manager == "apk":
            text = self._pkg_run(f"apk info -a {self._sh_quote(name)}", timeout=60.0).stdout
            if not text.strip():
                raise RouterManagementError(f"Package '{name}' was not found.")
            return self._parse_apk_info(text, name)
        raise RouterManagementError("No supported package manager found.")

    def package_install(self, name: str) -> dict[str, Any]:
        return self._pkg_mutate("installed", name, "opkg install", "apk add")

    def package_remove(self, name: str) -> dict[str, Any]:
        return self._pkg_mutate("removed", name, "opkg remove", "apk del")

    def package_upgrade(self, name: str) -> dict[str, Any]:
        return self._pkg_mutate("upgraded", name, "opkg upgrade", "apk upgrade")

    def package_reinstall(self, name: str) -> dict[str, Any]:
        return self._pkg_mutate("reinstalled", name, "opkg install --force-reinstall", "apk fix")

    def _pkg_mutate(self, verb: str, name: str, opkg_cmd: str, apk_cmd: str) -> dict[str, Any]:
        """Run a package mutation and bust the inventory cache on success."""
        if not self._PKG_NAME_PATTERN.match(name):
            raise RouterManagementError("Invalid package name.")
        manager = self._pkg_manager()
        if manager == "opkg":
            result = self._pkg_run(f"{opkg_cmd} {self._sh_quote(name)}", timeout=600.0)
        elif manager == "apk":
            result = self._pkg_run(f"{apk_cmd} {self._sh_quote(name)}", timeout=600.0)
        else:
            raise RouterManagementError("No supported package manager found.")
        if result.ok:
            self._packages_cache = {}
            self._packages_cache_at = 0.0
        return {
            "ok": result.ok,
            "message": (
                f"Package '{name}' {verb}."
                if result.ok
                else f"Package '{name}' could not be {verb}."
            ),
            "detail": result.to_dict(),
        }

    def run_packages_job(
        self,
        job_id: str,
        *,
        action: str,
        name: str | None = None,
    ) -> ManagementJob:
        """Execute a package operation inside a tracked job."""
        self._jobs.transition(job_id, "running", message="Running package operation…")
        try:
            if action == "install":
                result = self.package_install(name or "")
            elif action == "remove":
                result = self.package_remove(name or "")
            elif action == "upgrade":
                result = self.package_upgrade(name or "")
            elif action == "reinstall":
                result = self.package_reinstall(name or "")
            elif action == "update-feeds":
                result = self.update_feeds()
            else:
                raise RouterManagementError(f"Unsupported package action: {action}")
            self._jobs.transition(job_id, "succeeded", message=result["message"], result=result)
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Package action %r failed", action)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"Package operation failed: {exc}",
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    # -- storage ----------------------------------------------------------- #

    # One-shot gather of block devices (sector counts, so no 32-bit overflow),
    # ``df``-derived usage and ``/proc/mounts`` details, tagged for parsing.
    _STORAGE_GATHER_CMD = (
        "for d in /sys/block/*; do "
        "[ -e \"$d/size\" ] || continue; "
        "n=${d##*/}; "
        "s=$(cat \"$d/size\" 2>/dev/null); "
        "[ -n \"$s\" ] || s=0; "
        "t=$(cat \"$d/device/type\" 2>/dev/null); "
        "r=$(cat \"$d/removable\" 2>/dev/null); "
        "dd=$(cat \"$d/dev\" 2>/dev/null); "
        "v=$(cat \"$d/device/vendor\" 2>/dev/null); "
        "m=$(cat \"$d/device/model\" 2>/dev/null); "
        "printf '__AI_BLOCK__ %s|%s|%s|%s|%s|%s|%s\\n' "
        "\"$n\" \"$s\" \"$t\" \"$r\" \"$dd\" \"$v\" \"$m\"; "
        "done; "
        "printf '__AI_DF__\\n'; "
        "df -k 2>/dev/null; "
        "printf '__AI_MOUNT__\\n'; "
        "cat /proc/mounts 2>/dev/null"
    )

    @staticmethod
    def _parse_df_row(line: str) -> dict[str, Any] | None:
        """Parse a busy-box ``df -k`` data row into usage fields (bytes)."""
        cols = line.split()
        if len(cols) < 6:
            return None

        def _int(value: str) -> int | None:
            return int(value) if value.isdigit() else None
        percent: int | None = None
        if cols[4].endswith("%"):
            raw = cols[4][:-1]
            percent = int(raw) if raw.isdigit() else None
        return {
            "device": cols[0],
            "total_bytes": (_int(cols[1]) or 0) * 1024,
            "used_bytes": (_int(cols[2]) or 0) * 1024,
            "available_bytes": (_int(cols[3]) or 0) * 1024,
            "use_percent": percent,
            "mountpoint": " ".join(cols[5:]),
        }

    def storage(self) -> dict[str, Any]:
        """Collect block devices, filesystem usage and mount options from the router."""
        output = self._pkg_run(self._STORAGE_GATHER_CMD, timeout=60.0).stdout

        blocks: list[dict[str, Any]] = []
        df_rows: list[dict[str, Any]] = []
        mounts_proc: list[dict[str, str]] = []
        section = "block"
        for line in output.splitlines():
            stripped = line.rstrip("\r").strip()
            if stripped == "__AI_DF__":
                section = "df"
                continue
            if stripped == "__AI_MOUNT__":
                section = "mount"
                continue
            if stripped.startswith("__AI_BLOCK__ "):
                fields = stripped[len("__AI_BLOCK__ "):].split("|")
                if len(fields) >= 7:
                    blocks.append(
                        {
                            "name": fields[0],
                            "sectors": fields[1] if fields[1].isdigit() else "0",
                            "devtype": fields[2],
                            "removable": fields[3] == "1",
                            "devnodes": fields[4],
                            "vendor": fields[5].strip(),
                            "model": fields[6].strip(),
                        }
                    )
                continue
            if section == "df":
                row = self._parse_df_row(stripped)
                if row is not None:
                    df_rows.append(row)
            elif section == "mount":
                parts = stripped.split(None, 4)
                if len(parts) >= 4:
                    mounts_proc.append(
                        {
                            "device": parts[0],
                            "mountpoint": parts[1],
                            "filesystem": parts[2],
                            "options": parts[3],
                        }
                    )

        mount_lookup: dict[str, dict[str, str]] = {}
        for m in mounts_proc:
            mount_lookup.setdefault(m["mountpoint"], m)

        mounts: list[dict[str, Any]] = []
        for row in df_rows:
            mp = row["mountpoint"]
            info = mount_lookup.get(mp, {})
            devices = row["device"]
            mounts.append(
                {
                    "device": row["device"],
                    "mountpoint": mp,
                    "filesystem": info.get("filesystem", ""),
                    "options": info.get("options", ""),
                    "total_bytes": row["total_bytes"],
                    "used_bytes": row["used_bytes"],
                    "available_bytes": row["available_bytes"],
                    "use_percent": row["use_percent"],
                    "overlay": "/" in devices and "overlay" in devices.lower()
                    or info.get("filesystem") == "overlay"
                    or mp == "/overlay",
                    "rootfs": mp == "/" or info.get("filesystem") == "rootfs",
                }
            )

        # Physical devices with a human-friendly type + capacity.
        devices: list[dict[str, Any]] = []
        for blk in blocks:
            sectors = int(blk["sectors"])
            size = sectors * 512
            name = blk["name"]
            if name.startswith("mmcblk"):
                dtype = "eMMC / SD"
            elif blk["removable"]:
                dtype = "USB storage"
            else:
                dtype = "Disk"
            devices.append(
                {
                    "name": name,
                    "type": dtype,
                    "vendor": blk["vendor"],
                    "model": blk["model"],
                    "size": size,
                    "status": "mounted" if self._device_mounted(mounts, name) else "online",
                }
            )

        # USB storage = removable block devices with capacity and mount state.
        mounted_names = self._device_mount_map(mounts)
        usb: list[dict[str, Any]] = []
        for blk in blocks:
            if not blk["removable"]:
                continue
            sectors = int(blk["sectors"])
            mounted = any(mp.startswith("/dev/" + blk["name"]) for mp in mounted_names)
            usb.append(
                {
                    "device": blk["name"],
                    "vendor": blk["vendor"],
                    "model": blk["model"],
                    "capacity": sectors * 512,
                    "mounted": mounted,
                    "mountpoint": self._mounted_mountpoint(mounts, blk["name"]),
                }
            )

        root = next((m for m in mounts if m["rootfs"]), None)
        overlay = next((m for m in mounts if m["overlay"]), None)

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "devices": devices,
            "mounts": mounts,
            "usb": usb,
            "rootfs": root,
            "overlayfs": overlay,
            "total_bytes": root["total_bytes"] if root else None,
            "used_bytes": root["used_bytes"] if root else None,
            "available_bytes": root["available_bytes"] if root else None,
            "use_percent": root["use_percent"] if root else None,
        }

    @staticmethod
    def _device_mount_map(mounts: list[dict[str, Any]]) -> set[str]:
        return {m["device"] for m in mounts}

    @classmethod
    def _device_mounted(cls, mounts: list[dict[str, Any]], name: str) -> bool:
        prefix = f"/dev/{name}"
        return any(dev.startswith(prefix) for dev in cls._device_mount_map(mounts))

    @staticmethod
    def _mounted_mountpoint(mounts: list[dict[str, Any]], name: str) -> str | None:
        prefix = f"/dev/{name}"
        for m in mounts:
            if m["device"].startswith(prefix):
                return m["mountpoint"]
        return None

    def run_storage_job(
        self,
        job_id: str,
        *,
        action: str,
        target: str,
    ) -> ManagementJob:
        """Run a filesystem action (mount / unmount / remount) inside a job."""
        self._jobs.transition(job_id, "running", message=f"Working on {target}…")
        try:
            quoted = self._sh_quote(target)
            if action == "unmount":
                command = f"umount {quoted}"
            elif action == "remount":
                command = f"mount -o remount {quoted}"
            elif action == "mount":
                command = f"mount {quoted}"
            else:
                raise RouterManagementError(f"Unsupported storage action: {action}")
            result = self._pkg_run(command, timeout=120.0)
            message = (
                f"Volume '{target}' {action}ed."
                if result.ok
                else f"Could not {action} '{target}'."
            )
            self._jobs.transition(
                job_id,
                "succeeded" if result.ok else "failed",
                message=message,
                result={
                    "ok": result.ok,
                    "detail": result.to_dict(),
                    "action": action,
                    "target": target,
                },
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Storage action %r failed", action)
            self._jobs.transition(job_id, "failed", error=str(exc))
        return self._jobs.get(job_id)  # type: ignore[return-value]

    # -- services ---------------------------------------------------------- #

    # Descriptions for the most common OpenWrt services shown in the console;
    # anything else falls back to a generic "managed service" label.
    _SERVICE_DESCRIPTIONS: dict[str, str] = {
        "boot": "System boot sequence",
        "cwmp": "TR-069 remote management agent",
        "dnsmasq": "DNS forwarder and DHCP server",
        "dropbear": "SSH server for remote access",
        "firewall": "Stateful packet filter",
        "gpsd": "GPS daemon for location services",
        "hostapd": "802.11 access point daemon",
        "httpd": "Embedded HTTP server",
        "led": "LED state configuration",
        "log": "System logging configuration",
        "monit": "Process supervision and monitoring",
        "mwan3": "Multi-WAN load balancing and failover",
        "network": "Network interface configuration",
        "odhcpd": "DHCPv6 and Router Advertisement daemon",
        "openvpn": "OpenVPN tunnel service",
        "pbr": "Policy-based routing rules",
        "qmi": "3G/4G modem routing",
        "rpcd": "OpenWrt ubus RPC daemon",
        "smartd": "S.M.A.R.T. disk monitoring daemon",
        "sqm": "Smart Queue Management",
        "sysntpd": "NTP-based system clock",
        "tailscaled": "Tailscale mesh VPN daemon",
        "uhttpd": "Lightweight HTTP server (LuCI)",
        "ucod": "UCI data model daemon",
        "upnpd": "UPnP reachability service",
        "wireless": "Wireless configuration",
        "wsdd": "Web Services Dynamic Discovery daemon",
    }

    _SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
    _SERVICE_ACTIONS = frozenset({"start", "stop", "restart", "enable", "disable"})

    # One-shot gather of the procd ubus service registry (JSON), the per-service
    # boot-enable state reported by the rc common layer, and a readable /proc
    # process table used as the BusyBox fallback when ubus is unavailable.
    _SERVICES_GATHER_CMD = (
        "ubus call service list 2>/dev/null; "
        "printf '__AI_ENABLED__\\n'; "
        "for s in /etc/init.d/*; do "
        "[ -x \"$s\" ] || continue; "
        "n=${s##*/}; "
        "printf '__AI_EN__ %s|%s\\n' \"$n\" \"$(/etc/init.d/\"$n\" enabled 2>/dev/null)\"; "
        "done; "
        "printf '__AI_PROC__\\n'; "
        "for p in /proc/[0-9]*; do "
        "[ -r \"$p/cmdline\" ] || continue; "
        "c=$(tr '\\0' ' ' < \"$p/cmdline\" 2>/dev/null); "
        "[ -z \"$c\" ] && continue; "
        "printf '__AI_PROCESS__ %s|%s\\n' \"${p##*/}\" \"$c\"; "
        "done"
    )

    @staticmethod
    def _first_matching_pid(procs: list[tuple[str, str]], name: str) -> int | None:
        """First process whose executable basename matches the service name."""
        for pid, command in procs:
            parts = command.split()
            if parts and parts[0].rsplit("/", 1)[-1] == name:
                return int(pid) if pid.isdigit() else None
        return None

    def services(self) -> dict[str, Any]:
        """Collect all OpenWrt services with state from procd/ubus (or init.d).

        When procd responds, process identity and uptime come from ``ubus call
        service list``; otherwise a BusyBox fallback matches each init script
        against the running ``/proc`` command lines.
        """
        output = self._pkg_run(self._SERVICES_GATHER_CMD, timeout=60.0).stdout

        ubus_text: list[str] = []
        enabled: dict[str, bool] = {}
        procs: list[tuple[str, str]] = []
        section = "ubus"
        for line in output.splitlines():
            stripped = line.rstrip("\r").strip()
            if stripped == "__AI_ENABLED__":
                section = "enabled"
                continue
            if stripped == "__AI_PROC__":
                section = "proc"
                continue
            if section == "ubus":
                if stripped:
                    ubus_text.append(stripped)
            elif section == "enabled":
                if stripped.startswith("__AI_EN__ "):
                    name, _, state = stripped[len("__AI_EN__ "):].partition("|")
                    enabled[name.strip()] = state.strip() == "enabled"
            elif section == "proc" and stripped.startswith("__AI_PROCESS__ "):
                pid, _, command = stripped[len("__AI_PROCESS__ "):].partition("|")
                procs.append((pid.strip(), command.strip()))

        ubus_data: dict[str, Any] = {}
        if ubus_text:
            try:
                parsed = json.loads("\n".join(ubus_text))
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                ubus_data = parsed

        probes: dict[str, bool] = {}
        pids: dict[str, int | None] = {}
        uptimes: dict[str, int | None] = {}
        instance_counts: dict[str, int] = {}
        for name, meta in ubus_data.items():
            if not isinstance(meta, dict):
                continue
            instances = meta.get("instances", {})
            if not isinstance(instances, dict):
                instances = {}
            is_running = meta.get("running") is True
            pid: int | None = None
            uptime: int | None = None
            instance_count = 0
            for instance in instances.values():
                if not isinstance(instance, dict):
                    continue
                instance_count += 1
                if instance.get("running") is True:
                    is_running = True
                if pid is None and isinstance(instance.get("pid"), int) and instance["pid"] > 0:
                    pid = instance["pid"]
                if uptime is None and isinstance(instance.get("uptime"), int):
                    uptime = instance["uptime"]
            probes[name] = is_running
            pids[name] = pid
            uptimes[name] = uptime
            instance_counts[name] = instance_count

        services: list[dict[str, Any]] = []
        names = set(enabled) | set(probes)
        for name in sorted(names):
            ubus_known = name in probes
            if ubus_known:
                running = probes[name]
                pid = pids[name]
                uptime = uptimes[name]
                instances = max(instance_counts[name], 1 if running else 0)
            else:
                pid = self._first_matching_pid(procs, name)
                running = pid is not None
                uptime = None
                instances = 1 if running else 0
            services.append(
                {
                    "name": name,
                    "description": self._SERVICE_DESCRIPTIONS.get(
                        name,
                        f"Managed OpenWrt service '{name}'",
                    ),
                    "running": running,
                    "enabled": enabled.get(name),
                    "pid": pid,
                    "uptime": uptime,
                    "restart_count": None,
                    "instances": instances,
                }
            )

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "count": len(services),
            "running_count": sum(1 for entry in services if entry["running"]),
            "enabled_count": sum(1 for entry in services if entry["enabled"]),
            "ubus": bool(ubus_data),
            "services": services,
        }

    def run_services_job(
        self,
        job_id: str,
        *,
        action: str,
        service: str,
    ) -> ManagementJob:
        """Run a service action (start / stop / restart / enable / disable)."""
        self._jobs.transition(job_id, "running", message=f"{action.capitalize()} '{service}'…")
        try:
            if not self._SERVICE_NAME_PATTERN.match(service):
                raise RouterManagementError("Invalid service name.")
            if action not in self._SERVICE_ACTIONS:
                raise RouterManagementError(f"Unsupported service action: {action}")
            quoted = self._sh_quote(service)
            result = self._pkg_run(f"/etc/init.d/{quoted} {action}", timeout=120.0)
            message = (
                f"Service '{service}' {action}ed."
                if result.ok
                else f"Could not {action} '{service}'."
            )
            self._jobs.transition(
                job_id,
                "succeeded" if result.ok else "failed",
                message=message,
                result={
                    "ok": result.ok,
                    "detail": result.to_dict(),
                    "action": action,
                    "service": service,
                },
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Service action %r failed", action)
            self._jobs.transition(job_id, "failed", error=str(exc))
        return self._jobs.get(job_id)  # type: ignore[return-value]

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
        """Execute a firewall rule toggle inside a single job."""
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

    # ---- firewall management job ----------------------------------------- #
    #
    # The full management surface: restart / reload / enable / disable the
    # service and enable or disable individual zones, traffic rules and
    # forwarding sections. Every mutation commits through ``uci`` and reloads
    # the live firewall, and runs inside the tracked :class:`ManagementJob`.

    # One-shot gather of the UCI firewall config, the ubus interface table
    # (used to report which interfaces a zone covers), runtime status and the
    # connection-tracking utilization. Tagged so the parser can attribute
    # output unambiguously.
    _FIREWALL_GATHER_CMD = (
        "printf '__AI_FW_CONFIG__\\n'; "
        "uci show firewall 2>/dev/null; "
        "printf '__AI_FW_INTERFACES__\\n'; "
        "ubus call network.interface dump 2>/dev/null; "
        "printf '__AI_FW_STATUS__\\n'; "
        "if [ -f /var/run/fw4.state ] || [ -f /tmp/fw4.state ] "
        "|| pgrep -x fw4 >/dev/null 2>&1; then echo running; else echo stopped; fi; "
        "ls /etc/rc.d/S*firewall >/dev/null 2>&1 && echo boot-enabled || echo boot-disabled; "
        "fw4 -v 2>/dev/null | head -1 || fw3 -v 2>/dev/null | head -1; "
        "printf '__AI_FW_CONNTRACK__\\n'; "
        "printf 'count=%s\\n' \"$(cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null)\"; "
        "printf 'max=%s\\n' \"$(cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null)\"; "
        "printf '__AI_FW_IPSET__\\n'; "
        "if command -v ipset >/dev/null 2>&1; then echo available; else echo missing; fi; "
        "echo __AI_FW_DONE__"
    )

    _FW_SECTION_RE = re.compile(r"^firewall\.(?P<key>[^=]+)=(?P<type>\w+)$")
    _FW_OPTION_RE = re.compile(
        r"^firewall\.(?P<key>[^=]+)\.(?P<opt>[A-Za-z0-9_]+)='(?P<value>[^']*)'$"
    )

    @staticmethod
    def _fw_bool(value: str | None) -> bool:
        return bool(value and value.lower() in {"1", "yes", "true", "on"})

    @staticmethod
    def _fw_int(value: str | None) -> int | None:
        return int(value) if value and value.isdigit() else None

    @classmethod
    def _fw_section_enabled(cls, opt: dict[str, Any]) -> bool:
        """UCI firewall enabled semantics: ``enabled '0'`` / ``disabled '1'``."""
        if "disabled" in opt:
            return not cls._fw_bool(opt["disabled"])
        if "enabled" in opt:
            return opt["enabled"] != "0"
        return True

    def _firewall_set_section_enabled(self, *, section: str, enabled: bool) -> dict[str, Any]:
        """Set the ``enabled`` option of a firewall section and reload."""
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
            label = "enabled" if enabled else "disabled"
            if not result.ok:
                return {
                    "ok": False,
                    "label": label,
                    "message": f"Firewall section could not be {label} (exit {result.exit_code}).",
                    "detail": result.to_dict(),
                }
            return {
                "ok": True,
                "label": label,
                "message": f"Firewall section {label} and reloaded.",
                "detail": result.to_dict(),
            }
        finally:
            transport.close()

    def firewall_set_enabled(self, *, enabled: bool) -> dict[str, Any]:
        """Enable or disable the whole firewall (defaults toggle + restart)."""
        base = "uci delete firewall.@defaults[0].enabled" if enabled else (
            "uci set firewall.@defaults[0].enabled='0'"
        )
        command = f"{base} && uci commit firewall && /etc/init.d/firewall restart"
        transport = self.open()
        try:
            result = self.run(transport, command, timeout=90.0)
            label = "enabled" if enabled else "disabled"
            if not result.ok:
                return {
                    "ok": False,
                    "message": f"Firewall could not be {label} (exit {result.exit_code}).",
                    "detail": result.to_dict(),
                }
            return {
                "ok": True,
                "message": f"Firewall {label} and restarted.",
                "detail": result.to_dict(),
            }
        finally:
            transport.close()

    def firewall(self) -> dict[str, Any]:
        """Collect the complete firewall configuration via UCI/ubus.

        Returns zones, traffic rules, port-forwards (redirects), zone-to-zone
        forwarding, custom includes and ipsets (when the extra package is
        installed), plus global defaults, runtime status and connection
        tracking utilization. Pick nothing — the collector is read-only.
        """
        output = self._pkg_run(self._FIREWALL_GATHER_CMD, timeout=60.0).stdout

        sections: dict[str, dict[str, Any]] = {}
        state = ""
        config_lines: list[str] = []
        interfaces_raw = ""
        status_lines: list[str] = []
        conntrack_lines: list[str] = []
        ipset_lines: list[str] = []
        for line in output.splitlines():
            stripped = line.rstrip("\r").strip()
            if not stripped:
                continue
            if stripped.startswith("__AI_FW_"):
                if stripped == "__AI_FW_CONFIG__":
                    state = "config"
                elif stripped == "__AI_FW_INTERFACES__":
                    state = "interfaces"
                elif stripped == "__AI_FW_STATUS__":
                    state = "status"
                elif stripped == "__AI_FW_CONNTRACK__":
                    state = "conntrack"
                elif stripped == "__AI_FW_IPSET__":
                    state = "ipset"
                elif stripped == "__AI_FW_DONE__":
                    state = ""
                continue
            if state == "config":
                config_lines.append(stripped)
            elif state == "interfaces":
                interfaces_raw = f"{interfaces_raw}\n{stripped}"
            elif state == "status":
                status_lines.append(stripped)
            elif state == "conntrack":
                conntrack_lines.append(stripped)
            elif state == "ipset":
                ipset_lines.append(stripped)

        for line in config_lines:
            match = self._FW_OPTION_RE.match(line)
            if match:
                key, opt, value = match.group("key"), match.group("opt"), match.group("value")
                section = sections.setdefault(key, {})
                existing = section.get(opt)
                if existing is None:
                    section[opt] = value
                elif isinstance(existing, list):
                    existing.append(value)
                else:
                    section[opt] = [existing, value]
                continue
            match = self._FW_SECTION_RE.match(line)
            if match:
                sections.setdefault(match.group("key"), {"_type": match.group("type")})

        defaults: dict[str, Any] | None = None
        zones: list[dict[str, Any]] = []
        rules: list[dict[str, Any]] = []
        port_forwards: list[dict[str, Any]] = []
        forwardings: list[dict[str, Any]] = []
        nat: list[dict[str, Any]] = []
        includes: list[dict[str, Any]] = []
        ipsets: list[dict[str, Any]] = []

        for key, section in sections.items():
            stype = section.get("_type")
            if stype == "defaults":
                defaults = {
                    "input": section.get("input"),
                    "output": section.get("output"),
                    "forward": section.get("forward"),
                    "masquerade": self._fw_bool(section.get("masq")),
                    "syn_flood": self._fw_bool(
                        section.get("synflood_protect") or section.get("syn_flood")
                    ),
                    "osf": self._fw_bool(section.get("osf")),
                    "mtu": RouterManagementService._fw_int(section.get("mtu")),
                }
            elif stype == "zone":
                network = section.get("network")
                zones.append(
                    {
                        "name": section.get("name", ""),
                        "section": key,
                        "enabled": self._fw_section_enabled(section),
                        "family": section.get("family"),
                        "input": section.get("input"),
                        "output": section.get("output"),
                        "forward": section.get("forward"),
                        "masquerade": self._fw_bool(section.get("masq")),
                        "mtu_fix": self._fw_bool(section.get("mtu_fix")),
                        "network": network,
                    }
                )
            elif stype == "rule":
                rules.append(
                    {
                        "name": section.get("name", ""),
                        "src": section.get("src"),
                        "dest": section.get("dest"),
                        "proto": section.get("proto"),
                        "target": section.get("target"),
                        "family": section.get("family"),
                        "src_port": section.get("src_port"),
                        "dest_port": section.get("dest_port"),
                        "enabled": self._fw_section_enabled(section),
                        "section": key,
                    }
                )
            elif stype == "redirect":
                port_forwards.append(
                    {
                        "name": section.get("name", ""),
                        "src": section.get("src"),
                        "src_dport": section.get("src_dport") or section.get("dport"),
                        "src_ip": section.get("src_ip"),
                        "dest": section.get("dest"),
                        "dest_ip": section.get("dest_ip"),
                        "dest_port": section.get("dest_port"),
                        "proto": section.get("proto"),
                        "target": section.get("target", "DNAT"),
                        "family": section.get("family"),
                        "enabled": self._fw_section_enabled(section),
                        "section": key,
                    }
                )
            elif stype == "forwarding":
                forwardings.append(
                    {
                        "name": section.get("name", ""),
                        "src": section.get("src"),
                        "dest": section.get("dest"),
                        "family": section.get("family"),
                        "enabled": self._fw_section_enabled(section),
                        "section": key,
                    }
                )
            elif stype == "nat":
                nat.append(
                    {
                        "name": section.get("name", ""),
                        "src": section.get("src"),
                        "dest": section.get("dest"),
                        "src_dport": section.get("src_dport"),
                        "dest_ip": section.get("dest_ip"),
                        "dest_port": section.get("dest_port"),
                        "proto": section.get("proto"),
                        "target": section.get("target"),
                        "family": section.get("family"),
                        "enabled": self._fw_section_enabled(section),
                        "section": key,
                    }
                )
            elif stype == "include":
                includes.append(
                    {
                        "name": section.get("name", ""),
                        "path": section.get("path"),
                        "type": section.get("_type"),
                        "enabled": self._fw_section_enabled(section),
                        "section": key,
                    }
                )
            elif stype == "ipset" and ipset_lines:
                entries = section.get("entries")
                entries_list = list(entries) if isinstance(entries, list) else (
                    [entries] if entries else []
                )
                ipsets.append(
                    {
                        "name": section.get("name", ""),
                        "section": key,
                        "family": section.get("family"),
                        "match": section.get("match"),
                        "enabled": self._fw_section_enabled(section),
                        "entries": entries_list,
                        "count": len(entries_list),
                    }
                )

        # Runtime state.
        running = any(line.strip().lower() == "running" for line in status_lines)
        boot_enabled = any(line.strip().lower() == "boot-enabled" for line in status_lines)
        _status_tokens = {"running", "stopped", "boot-enabled", "boot-disabled"}
        version = next(
            (line.strip() for line in status_lines if line.strip().lower() not in _status_tokens),
            None,
        )
        conntrack: dict[str, Any] | None = None
        count_raw = ""
        max_raw = ""
        for line in conntrack_lines:
            if line.startswith("count="):
                count_raw = line.split("=", 1)[1].strip()
            elif line.startswith("max="):
                max_raw = line.split("=", 1)[1].strip()
        if count_raw or max_raw:
            conntrack = {
                "count": int(count_raw) if count_raw.isdigit() else None,
                "max": int(max_raw) if max_raw.isdigit() else None,
            }

        # Interfaces seen through ubus (reported for zone->interface mapping).
        interfaces: list[dict[str, Any]] = []
        if interfaces_raw.strip():
            try:
                parsed = json.loads(interfaces_raw)
                for entry in (parsed.get("interface") or []):
                    if not isinstance(entry, dict):
                        continue
                    interfaces.append(
                        {
                            "name": entry.get("interface", ""),
                            "device": entry.get("l3_device") or entry.get("device", ""),
                            "up": entry.get("up") is True,
                            "proto": entry.get("proto"),
                        }
                    )
            except json.JSONDecodeError:
                interfaces = []

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "enabled": boot_enabled,
            "running": running,
            "version": version,
            "defaults": defaults,
            "zones": zones,
            "rules": rules,
            "port_forwards": port_forwards,
            "forwardings": forwardings,
            "nat": nat,
            "includes": includes,
            "ipsets": ipsets,
            "ipsets_available": bool(ipset_lines and "available" in (ipset_lines[0] or "")),
            "interfaces": interfaces,
            "conntrack": conntrack,
            "counts": {
                "zones": len(zones),
                "rules": len(rules),
                "port_forwards": len(port_forwards),
                "forwardings": len(forwardings),
                "nat": len(nat),
                "includes": len(includes),
                "ipsets": len(ipsets),
            },
        }

    def run_firewall_job(
        self,
        job_id: str,
        *,
        action: str,
        section: str | None = None,
        enabled: bool | None = None,
    ) -> ManagementJob:
        """Execute a firewall management action inside a tracked job.

        Supported actions: ``restart``, ``reload``, ``enable``, ``disable``
        (whole service) or section toggles ``enable-zone``/``disable-zone``,
        ``enable-rule``/``disable-rule`` and
        ``enable-forwarding``/``disable-forwarding``.
        """
        self._jobs.transition(job_id, "running", message="Applying firewall change…")
        try:
            if action == "restart":
                result = self.action("restart-firewall")
            elif action == "reload":
                result = self.action("reload-firewall")
            elif action == "enable":
                result = self.firewall_set_enabled(enabled=True)
            elif action == "disable":
                result = self.firewall_set_enabled(enabled=False)
            elif action in ("enable-zone", "disable-zone"):
                result = self._firewall_set_section_enabled(
                    section=section or "", enabled=(action == "enable-zone")
                )
            elif action in ("enable-forwarding", "disable-forwarding"):
                result = self._firewall_set_section_enabled(
                    section=section or "", enabled=(action == "enable-forwarding")
                )
            elif action in ("enable-rule", "disable-rule"):
                result = self.toggle_firewall_rule(
                    section=section or "", enabled=(action == "enable-rule")
                )
            else:
                raise RouterManagementError(f"Unsupported firewall action: {action}")
            self._jobs.transition(
                job_id,
                "succeeded" if result.get("ok") else "failed",
                message=result.get("message", "Firewall change completed."),
                result=result,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Firewall action %r failed", action)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"Firewall change failed: {exc}",
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

    # Radiodevice UCI keys whose ``disabled`` option controls the whole radio.
    _WIFI_DEVICE_RE = re.compile(r"^wireless\.(?P<key>[^=]+)=(?P<type>\w+)$")
    _WIFI_OPTION_RE = re.compile(
        r"^wireless\.(?P<key>[^=]+)\.(?P<opt>[A-Za-z0-9_]+)='(?P<value>[^']*)'$"
    )
    _WIFI_STATUS_STATION = re.compile(r"^\s*Station\s+([0-9a-f:]{17})", re.IGNORECASE)

    # One-shot gather: the UCI wireless tree, the live ``ubus wifi status`` view,
    # per-interface carrier/station counts via ``iw``, and the DHCP lease file to
    # merge hostnames/IPs onto associated stations. Tagged for the parser.
    _WIRELESS_GATHER_CMD = (
        "printf '__AI_WIFI_UCI__\\n'; "
        "uci show wireless 2>/dev/null; "
        "printf '__AI_WIFI_STATUS__\\n'; "
        "ubus call wifi status 2>/dev/null; "
        "printf '__AI_WIFI_IFACES__\\n'; "
        "for i in /sys/class/net/*; do "
        "n=${i##*/}; [ -d /sys/class/net/$n/wireless ] || continue; "
        "c=$(cat /sys/class/net/$n/carrier 2>/dev/null); "
        "s=$(iw dev $n station dump 2>/dev/null | grep -c '^Station '); "
        "echo \"$n|${c:-0}|${s:-0}\"; "
        "done; "
        "printf '__AI_WIFI_LEASES__\\n'; "
        "cat /tmp/dhcp.leases 2>/dev/null; "
        "printf '__AI_WIFI_DONE__\\n'"
    )

    @staticmethod
    def _wifi_band(hwmode: str | None, frequency: int | None) -> str | None:
        if frequency is not None:
            return "5GHz" if frequency >= 5000 else "2.4GHz"
        if hwmode:
            mode = hwmode.lower()
            if "a" in mode:
                return "5GHz"
            if "b" in mode or "g" in mode:
                return "2.4GHz"
            if "ax" in mode or "ac" in mode:
                return "unknown"
        return None

    @staticmethod
    def _wifi_width_mhz(htmode: str | None, hwmode: str | None) -> int | None:
        """Derive channel width in MHz from an HT/VHT/HE/EHT mode string."""
        if not htmode:
            if hwmode and "n" in hwmode.lower():
                return 20
            return None
        match = re.search(r"(20|40|80|160|320)", htmode)
        if match:
            return int(match.group(1))
        return None

    def wireless(self) -> dict[str, Any]:
        """Collect the full wireless view: radios, SSIDs and associated stations.

        Combines the configured ``uci`` wireless tree with the live ``ubus wifi
        status`` radio state (band, channel, width, station metrics) and the
        per-interface station counts gathered via ``iw``. Station hostnames and
        IPs are merged from the dnsmasq lease file when the MAC matches.
        Read-only — nothing is changed on the router.
        """
        output = self._pkg_run(self._WIRELESS_GATHER_CMD, timeout=60.0).stdout

        # Divert the output into per-section buffers.
        uci_lines: list[str] = []
        status_raw = ""
        iface_lines: list[str] = []
        lease_lines: list[str] = []
        state = ""
        for line in output.splitlines():
            stripped = line.rstrip("\r").strip()
            if not stripped:
                continue
            if stripped.startswith("__AI_WIFI_"):
                if stripped == "__AI_WIFI_UCI__":
                    state = "uci"
                elif stripped == "__AI_WIFI_STATUS__":
                    state = "status"
                elif stripped == "__AI_WIFI_IFACES__":
                    state = "ifaces"
                elif stripped == "__AI_WIFI_LEASES__":
                    state = "leases"
                elif stripped == "__AI_WIFI_DONE__":
                    state = ""
                continue
            if state == "uci":
                uci_lines.append(stripped)
            elif state == "status":
                status_raw = f"{status_raw}\n{stripped}"
            elif state == "ifaces":
                iface_lines.append(stripped)
            elif state == "leases":
                lease_lines.append(stripped)

        # Runtime status from ubus.
        stations_by_iface: dict[str, list[dict[str, Any]]] = {}
        radio_meta: dict[str, dict[str, Any]] = {}
        if status_raw.strip():
            try:
                status = json.loads(status_raw)
                if isinstance(status, dict):
                    for radio_name, radio in status.items():
                        if not isinstance(radio, dict):
                            continue
                        radio_meta[radio_name] = radio
                        for iface in radio.get("interfaces") or []:
                            if not isinstance(iface, dict):
                                continue
                            cfg = iface.get("config") or {}
                            ifname = cfg.get("ifname")
                            if not ifname:
                                continue
                            for mac, station in (radio.get("stations") or {}).items():
                                if isinstance(station, dict):
                                    stations_by_iface.setdefault(ifname, []).append(
                                        {"mac": mac, **station}
                                    )
            except json.JSONDecodeError:
                radio_meta = {}

        # Per-interface carrier + station count gathered via iw.
        iface_state: dict[str, dict[str, Any]] = {}
        for line in iface_lines:
            name, _, rest = line.partition("|")
            carrier, _, count = rest.partition("|")
            iface_state[name] = {"up": carrier == "1", "stations": int(count) if count else 0}

        # Active lease map for hostname/IP enrichment.
        leases: dict[str, dict[str, str]] = {}
        for line in lease_lines:
            parts = line.split()
            if len(parts) >= 4:
                mac, ip, hostname = parts[1], parts[2], parts[3]
                leases[mac.lower()] = {"hostname": hostname, "ip": ip}

        # Config tree: devices (radios) and interfaces (SSIDs) from UCI.
        sections: dict[str, dict[str, Any]] = {}
        for line in uci_lines:
            match = self._WIFI_OPTION_RE.match(line)
            if match:
                key, opt, value = match.group("key"), match.group("opt"), match.group("value")
                sections.setdefault(key, {})[opt] = value
                continue
            match = self._WIFI_DEVICE_RE.match(line)
            if match:
                sections.setdefault(match.group("key"), {"_type": match.group("type")})

        wifi_devices: list[dict[str, Any]] = []
        wifi_ifaces: list[dict[str, Any]] = []
        for key, section in sections.items():
            stype = section.get("_type")
            if stype == "wifi-device":
                wifi_devices.append({"name": section.get("name", key), "section": key, **section})
            elif stype == "wifi-iface":
                wifi_ifaces.append({"section": key, **section})

        radios: list[dict[str, Any]] = []
        networks: list[dict[str, Any]] = []
        clients: list[dict[str, Any]] = []

        for device in wifi_devices:
            name = device["name"]
            runtime = radio_meta.get(name) or {}
            config = runtime.get("config") or {}
            hwmode = device.get("hwmode") or config.get("hwmode")
            htmode = device.get("htmode") or config.get("htmode")
            frequency = self._as_int(config.get("frequency"))
            channel = self._as_int(device.get("channel") or config.get("channel"))
            tx_power = self._as_int(device.get("txpower") or config.get("txpower"))
            station_count = 0
            for iface_cfg in runtime.get("interfaces") or []:
                if not isinstance(iface_cfg, dict):
                    continue
                station_count += len(iface_cfg.get("stations") or {}) if isinstance(
                    iface_cfg.get("stations"), dict
                ) else 0
            radios.append(
                {
                    "name": name,
                    "section": device["section"],
                    "up": bool(runtime.get("up", False)),
                    "mode": config.get("mode"),
                    "band": self._wifi_band(hwmode, frequency),
                    "channel": channel,
                    "frequency_mhz": frequency,
                    "tx_power": tx_power,
                    "ssid": (
                        next(
                            (
                                (c.get("config") or {}).get("ssid")
                                for c in runtime.get("interfaces") or []
                                if isinstance(c, dict) and (c.get("config") or {}).get("ssid")
                            ),
                            None,
                        )
                    ),
                    "hwmode": hwmode,
                    "width_mhz": self._wifi_width_mhz(htmode, hwmode),
                    "station_count": station_count,
                    "country": device.get("country") or config.get("country"),
                    "hardware": device.get("path"),
                    "enabled": device.get("disabled") != "1",
                    "guest": device.get("guest") == "1",
                }
            )

        for iface in sorted(wifi_ifaces, key=lambda item: item.get("ssid", "")):
            ssid = iface.get("ssid", "")
            device = iface.get("device", "")
            ifname = iface.get("ifname")
            state = iface_state.get(ifname or "") or {}
            stations = stations_by_iface.get(ifname or "", [])
            networks.append(
                {
                    "ssid": ssid,
                    "radio": device,
                    "interface": ifname,
                    "mode": iface.get("mode"),
                    "encryption": iface.get("encryption"),
                    "hidden": iface.get("hidden") == "1",
                    "enabled": iface.get("disabled") != "1",
                    "network": iface.get("network"),
                    "client_count": len(stations) or state.get("stations", 0),
                    "section": iface.get("section"),
                    "guest": iface.get("guest") == "1",
                }
            )
            for station in stations:
                mac = (station.get("mac") or "").lower()
                lease = leases.get(mac) if station.get("mac") else None
                clients.append(
                    {
                        "mac": station.get("mac"),
                        "ssid": ssid,
                        "hostname": (lease or {}).get("hostname") or None,
                        "ip": (lease or {}).get("ip") or None,
                        "signal_dbm": self._as_int(station.get("signal")),
                        "noise": self._as_int(station.get("noise")),
                        "rx_rate": self._as_int(station.get("rx_rate")),
                        "tx_rate": self._as_int(station.get("tx_rate")),
                        "tx_bytes": self._as_int(station.get("txbytes")),
                        "rx_bytes": self._as_int(station.get("rxbytes")),
                        "connected_time": self._as_int(station.get("connected_time")),
                        "interface": ifname,
                    }
                )

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "running": any(r["up"] for r in radios),
            "enabled": any(r["enabled"] for r in radios),
            "radios": radios,
            "networks": networks,
            "clients": clients,
            "counts": {
                "radios": len(radios),
                "networks": len(networks),
                "clients": len(clients),
            },
        }

    def toggle_wireless_radio(self, *, section: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable one UCI ``wifi-device`` (radio) and reload wireless."""
        if not section or not self._SECTION_PATTERN.match(section):
            raise RouterManagementError("Invalid wireless radio section identifier.")
        base = (
            f"uci delete wireless.{section}.disabled"
            if enabled
            else f"uci set wireless.{section}.disabled='1'"
        )
        command = f"{base} && uci commit wireless && /etc/init.d/wireless reload"
        transport = self.open()
        try:
            result = self.run(transport, command, timeout=90.0)
            label = "enabled" if enabled else "disabled"
            if not result.ok:
                return {
                    "ok": False,
                    "label": label,
                    "message": f"Radio could not be {label} (exit {result.exit_code}).",
                    "detail": result.to_dict(),
                }
            return {
                "ok": True,
                "label": label,
                "message": f"Radio {label} and wireless reloaded.",
                "detail": result.to_dict(),
            }
        finally:
            transport.close()

    def run_wireless_job(
        self,
        job_id: str,
        *,
        action: str,
        section: str | None = None,
        enabled: bool = False,
    ) -> ManagementJob:
        """Execute a wireless action inside a tracked job.

        Actions: ``restart`` / ``reload`` (the whole service) or section toggles
        ``enable-ssid`` / ``disable-ssid``, ``enable-radio`` / ``disable-radio``.
        """
        self._jobs.transition(job_id, "running", message="Applying wireless change…")
        try:
            if action in ("restart", "reload"):
                result = self.action(
                    "restart-wifi" if action == "restart" else "reload-wireless"
                )
            elif action in ("enable-ssid", "disable-ssid"):
                result = self.toggle_wireless_ssid(
                    section=section or "", enabled=(action == "enable-ssid")
                )
            elif action in ("enable-radio", "disable-radio"):
                result = self.toggle_wireless_radio(
                    section=section or "", enabled=(action == "enable-radio")
                )
            else:
                raise RouterManagementError(f"Unsupported wireless action: {action}")
            self._jobs.transition(
                job_id,
                "succeeded" if result.get("ok") else "failed",
                message=result.get("message", "Wireless change completed."),
                result=result,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("Wireless action %r failed", action)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"Wireless change failed: {exc}",
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    # -- vpn --------------------------------------------------------------- #

    def toggle_vpn_instance(self, *, section: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable one UCI ``openvpn`` instance and reload the service."""
        if not section or not self._SECTION_PATTERN.match(section):
            raise RouterManagementError("Invalid VPN section identifier.")
        value = "1" if enabled else "0"
        command = (
            f"uci set openvpn.{section}.enabled='{value}' && "
            "uci commit openvpn && /etc/init.d/openvpn reload"
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
                "message": f"VPN instance {label}d and OpenVPN reloaded.",
                "detail": result.to_dict(),
            }
        finally:
            transport.close()

    def run_vpn_toggle_job(
        self,
        job_id: str,
        *,
        section: str,
        enabled: bool,
    ) -> ManagementJob:
        """Execute an OpenVPN instance enable/disable inside a tracked job."""
        action_label = "Enable" if enabled else "Disable"
        self._jobs.transition(job_id, "running", message=f"{action_label}ing VPN…")
        try:
            result = self.toggle_vpn_instance(section=section, enabled=enabled)
            self._jobs.transition(job_id, "succeeded", message=result["message"], result=result)
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("VPN instance toggle failed for %r", section)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"VPN instance could not be {action_label.lower()}d.",
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    # -- DHCP -------------------------------------------------------------- #

    _DHCP_SECTION_PATTERN = re.compile(r"^@?[A-Za-z0-9_@.\-]+(\[\d+\])?$")

    @staticmethod
    def _shell_single(value: str) -> str:
        """Wrap a value in single quotes, escaping embedded quotes safely."""
        return "'" + value.replace("'", "'\\''") + "'"

    def _validate_static(self, *, hostname: str, ip: str, mac: str) -> None:
        if not hostname or not ip or not mac:
            raise RouterManagementError("Hostname, IP and MAC are all required.")
        if len(hostname) > 63 or not re.fullmatch(r"[A-Za-z0-9_.\-]+", hostname):
            raise RouterManagementError("Invalid hostname.")
        try:
            address = ipaddress.ip_address(ip)
        except ValueError as exc:
            raise RouterManagementError("Invalid IP address.") from exc
        if address.version != 4:
            raise RouterManagementError("Only IPv4 static leases are supported.")
        if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", mac):
            raise RouterManagementError("Invalid MAC address.")

    def _dhcp_run(self, command: str) -> tuple[bool, str]:
        transport = self.open()
        try:
            result = self.run(transport, command, timeout=90.0)
            return result.ok, result.stdout
        finally:
            transport.close()

    def collect_dhcp(self) -> dict[str, Any]:
        """Gather the dnsmasq status plus UCI DHCP configuration."""
        script = (
            "uci show dhcp; echo __AI_SEP__; "
            "/etc/init.d/dnsmasq running; echo '$?'; "
            "echo 'enable_dnsmasq='; uci get dhcp.@dnsmasq[0].enable_dnsmasq 2>/dev/null; "
            "echo '__AI_SEP__'; cat /tmp/dhcp.leases 2>/dev/null"
        )
        transport = self.open()
        try:
            result = self.run(transport, script, timeout=90.0)
        finally:
            transport.close()

        status: dict[str, Any] = {
            "service": {"name": "dnsmasq", "running": False, "enabled": True, "configured": True},
            "settings": {},
            "hosts": [],
            "leases": [],
        }
        if not result.ok:
            status["error"] = result.stderr or "Cannot reach router."
            return status

        parts = result.stdout.split("__AI_SEP__")
        settings: dict[str, Any] = {}
        hosts = []
        if parts:
            for line in parts[0].rstrip("\r").splitlines():
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, _, raw_value = line.partition("=")
                value = raw_value.strip().strip("'\"").strip()
                if key.startswith("@host"):
                    idx = key.split(".", 1)
                    option = idx[1] if len(idx) > 1 else None
                    hostname = idx[0]
                    entry = next(
                        (h for h in hosts if h["section"] == hostname), None
                    )
                    if entry is None:
                        entry = {
                            "section": hostname,
                            "name": "",
                            "ip": "",
                            "mac": "",
                            "enabled": True,
                        }
                        hosts.append(entry)
                    if option in ("name", "ip", "mac"):
                        entry[option] = value
                    elif option == "enabled":
                        entry["enabled"] = value != "0"
                else:
                    fields = key.split(".")
                    if len(fields) == 2 and fields[0] == "dnsmasq":
                        settings[fields[1]] = value if value not in ("", "0") else (value == "0")
                        if fields[1] == "enable_dnsmasq":
                            status["service"]["enabled"] = value != "0"
        status["settings"] = settings
        status["hosts"] = hosts

        if len(parts) > 1:
            running = parts[1]
            if "running" in running:
                status["service"]["running"] = True
            elif "not running" in running:
                status["service"]["running"] = False
            try:
                rc = int(running.split()[-1].strip())
                status["service"]["running"] = rc == 0
            except (ValueError, IndexError):
                pass

        if len(parts) > 2:
            for line in parts[2].rstrip("\r").splitlines():
                line = line.strip()
                if not line:
                    continue
                fields = line.split()
                if len(fields) >= 4:
                    status["leases"].append(
                        {
                            "time": fields[0],
                            "mac": fields[1],
                            "ip": fields[2],
                            "hostname": fields[3] if len(fields) > 3 else "",
                        }
                    )
        return status

    def dhcp_set_enabled(self, *, enabled: bool) -> dict[str, Any]:
        """Enable or disable the whole dnsmasq DHCP server."""
        value = "1" if enabled else "0"
        ok, _ = self._dhcp_run(
            f"uci set dhcp.@dnsmasq[0].enable_dnsmasq='{value}' && "
            "uci commit dhcp && /etc/init.d/dnsmasq restart"
        )
        label = "Enabled" if enabled else "Disabled"
        if not ok:
            return {"ok": False, "message": f"Could not {label.lower()} the DHCP server."}
        return {"ok": True, "message": f"DHCP server {label.lower()}."}

    def dhcp_add_host(self, *, hostname: str, ip: str, mac: str) -> dict[str, Any]:
        """Create a new ``dhcp.@host`` static lease."""
        self._validate_static(hostname=hostname, ip=ip, mac=mac)
        command = (
            "sid=$(uci add dhcp host) && "
            f"uci set dhcp.$sid.name={self._shell_single(hostname)} && "
            f"uci set dhcp.$sid.ip={self._shell_single(ip)} && "
            f"uci set dhcp.$sid.mac={self._shell_single(mac)} && "
            "uci commit dhcp && /etc/init.d/dnsmasq reload && printf '%s' \"$sid\""
        )
        ok, stdout = self._dhcp_run(command)
        if not ok:
            return {"ok": False, "message": "Could not add the static lease."}
        section = stdout.strip().splitlines()[-1].strip() if stdout.strip() else None
        return {
            "ok": True,
            "section": section,
            "message": f"Static lease for {hostname} added.",
        }

    def dhcp_edit_host(self, *, section: str, hostname: str, ip: str, mac: str) -> dict[str, Any]:
        """Update an existing ``dhcp.@host`` static lease."""
        if not section or not self._DHCP_SECTION_PATTERN.match(section):
            raise RouterManagementError("Invalid static lease section identifier.")
        self._validate_static(hostname=hostname, ip=ip, mac=mac)
        command = (
            f"uci set dhcp.{section}.name={self._shell_single(hostname)} && "
            f"uci set dhcp.{section}.ip={self._shell_single(ip)} && "
            f"uci set dhcp.{section}.mac={self._shell_single(mac)} && "
            "uci commit dhcp && /etc/init.d/dnsmasq reload"
        )
        ok, _ = self._dhcp_run(command)
        if not ok:
            return {"ok": False, "message": f"Could not update the static lease for {hostname}."}
        return {"ok": True, "message": f"Static lease for {hostname} updated."}

    def dhcp_delete_host(self, *, section: str) -> dict[str, Any]:
        """Delete a ``dhcp.@host`` static lease."""
        if not section or not self._DHCP_SECTION_PATTERN.match(section):
            raise RouterManagementError("Invalid static lease section identifier.")
        ok, _ = self._dhcp_run(
            f"uci delete dhcp.{section} && uci commit dhcp && /etc/init.d/dnsmasq reload"
        )
        if not ok:
            return {"ok": False, "message": "Could not delete the static lease."}
        return {"ok": True, "message": "Static lease deleted."}

    def dhcp_toggle_host(self, *, section: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable a ``dhcp.@host`` static lease."""
        if not section or not self._DHCP_SECTION_PATTERN.match(section):
            raise RouterManagementError("Invalid static lease section identifier.")
        if enabled:
            command = f"uci delete dhcp.{section}.enabled && uci commit dhcp"
        else:
            command = f"uci set dhcp.{section}.enabled='0' && uci commit dhcp"
        ok, _ = self._dhcp_run(command)
        if not ok:
            return {"ok": False, "message": "Could not change the static lease state."}
        label = "Enabled" if enabled else "Disabled"
        return {"ok": True, "message": f"Static lease {label.lower()}."}

    def run_dhcp_job(
        self,
        job_id: str,
        *,
        action: str,
        section: str | None,
        enabled: bool,
        hostname: str | None,
        ip: str | None,
        mac: str | None,
    ) -> ManagementJob:
        """Execute a DHCP change inside a tracked job.

        Actions: ``reload`` / ``restart`` (the dnsmasq service),
        ``set-enabled``, or host CRUD (``host-add`` / ``host-edit`` /
        ``host-delete`` / ``host-toggle``).
        """
        self._jobs.transition(job_id, "running", message="Applying DHCP change…")
        try:
            if action in ("reload", "restart"):
                result = self.action("reload-dhcp" if action == "reload" else "restart-dhcp")
                result["message"] = (
                    "DHCP server reloaded."
                    if action == "reload"
                    else "DHCP server restarted."
                )
            elif action == "set-enabled":
                result = self.dhcp_set_enabled(enabled=enabled)
            elif action == "host-add":
                result = self.dhcp_add_host(hostname=hostname or "", ip=ip or "", mac=mac or "")
            elif action == "host-edit":
                result = self.dhcp_edit_host(
                    section=section or "",
                    hostname=hostname or "",
                    ip=ip or "",
                    mac=mac or "",
                )
            elif action == "host-delete":
                result = self.dhcp_delete_host(section=section or "")
            elif action == "host-toggle":
                result = self.dhcp_toggle_host(section=section or "", enabled=enabled)
            else:
                raise RouterManagementError(f"Unsupported DHCP action: {action}")
            self._jobs.transition(job_id, "succeeded", message=result["message"], result=result)
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("DHCP action %r failed", action)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"DHCP change failed: {exc}",
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    # -- DNS --------------------------------------------------------------- #

    _DNS_SERVER_PATTERN = re.compile(r"^[A-Za-z0-9_.:\-]{1,253}$")
    _DNS_NAMESERVER_PATTERN = re.compile(r"^\s*nameserver\s+(\S+)\s*$")
    _DNS_HOST_LINE = re.compile(r"^\s*([^\s#]+)\s+([^\s#]+)")
    _DNS_HOSTNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{1,63}$")

    @staticmethod
    def _validate_dns_host(*, hostname: str, ip: str) -> None:
        if not hostname or not ip:
            raise RouterManagementError("Hostname and IP are both required.")
        if not RouterManagementService._DNS_HOSTNAME_PATTERN.fullmatch(hostname):
            raise RouterManagementError("Invalid hostname.")
        try:
            ipaddress.ip_address(ip)
        except ValueError as exc:
            raise RouterManagementError("Invalid IP address.") from exc

    def _dns_run(self, command: str) -> CommandResult:
        transport = self.open()
        try:
            return self.run(transport, command, timeout=90.0)
        finally:
            transport.close()

    def collect_dns(self) -> dict[str, Any]:
        """Gather the DNS/forwarder state: upstream servers, local hosts and the
        dnsmasq service status. Read-only — nothing is changed on the router.
        """
        script = (
            "uci show dhcp 2>/dev/null; echo '__AI_SEP__'; "
            "cat /etc/resolv.conf 2>/dev/null; echo '__AI_SEP__'; "
            "cat /etc/hosts 2>/dev/null; echo '__AI_SEP__'; "
            "/etc/init.d/dnsmasq running >/dev/null 2>&1 && echo running || echo stopped"
        )
        transport = self.open()
        try:
            result = self.run(transport, script, timeout=90.0)
        finally:
            transport.close()

        status: dict[str, Any] = {
            "service": {"name": "dnsmasq", "running": False, "enabled": True, "configured": True},
            "upstream": [],
            "servers": [],
            "domain": None,
            "hosts": [],
            "counts": {"servers": 0, "hosts": 0},
        }
        if not result.ok:
            status["error"] = result.stderr or "Cannot reach router."
            return status

        parts = result.stdout.split("__AI_SEP__")
        # UCI dnsmasq config (upstream override + local domain).
        for raw in (parts[0] or "").splitlines():
            line = raw.rstrip("\r").strip()
            if not line or "=" not in line or not line.startswith("dhcp."):
                continue
            key, _, raw_value = line.partition("=")
            value = raw_value.strip().strip("'\"").strip()
            if key == "dhcp.dnsmasq" or key.startswith("dhcp.dnsmasq["):
                continue
            if key.startswith("dhcp.dnsmasq"):
                option = key.rsplit(".", 1)[-1]
                if option == "server" and value not in status["servers"]:
                    status["servers"].append(value)
                elif option == "domain" and value:
                    status["domain"] = value

        # Upstream nameservers from resolv.conf.
        for raw in (parts[1] or "").splitlines():
            match = self._DNS_NAMESERVER_PATTERN.match(raw)
            if match and match.group(1) not in status["upstream"]:
                status["upstream"].append(match.group(1))

        # Static /etc/hosts entries (ip -> first hostname).
        for raw in (parts[2] or "").splitlines():
            match = self._DNS_HOST_LINE.match(raw)
            if not match:
                continue
            ip, hostname = match.group(1), match.group(2)
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                continue
            if hostname.startswith("#"):
                continue
            status["hosts"].append({"ip": ip, "hostname": hostname})

        run_state = (parts[3] or "").strip() if len(parts) > 3 else ""
        status["service"]["running"] = run_state == "running"
        if run_state == "stopped":
            status["service"]["enabled"] = False
        status["counts"]["servers"] = len(status["servers"])
        status["counts"]["hosts"] = len(status["hosts"])
        return status

    def dns_set_enabled(self, *, enabled: bool) -> dict[str, Any]:
        """Enable or disable the dnsmasq DNS forwarder."""
        value = "1" if enabled else "0"
        ok, _ = self._dns_run(
            f"uci set dhcp.@dnsmasq[0].enable_dnsmasq='{value}' && "
            "uci commit dhcp && /etc/init.d/dnsmasq restart"
        )
        label = "Enabled" if enabled else "Disabled"
        if not ok:
            return {"ok": False, "message": f"Could not {label.lower()} the DNS server."}
        return {"ok": True, "message": f"DNS server {label.lower()}."}

    def dns_add_server(self, *, server: str) -> dict[str, Any]:
        """Add an upstream DNS server to the dnsmasq ``server`` list."""
        if not server or not self._DNS_SERVER_PATTERN.match(server):
            raise RouterManagementError("Invalid DNS server address.")
        ok, _ = self._dns_run(
            f"uci add_list dhcp.@dnsmasq[0].server={self._shell_single(server)} && "
            "uci commit dhcp && /etc/init.d/dnsmasq reload"
        )
        if not ok:
            return {"ok": False, "message": f"Could not add upstream server {server}."}
        return {"ok": True, "message": f"Added upstream server {server}."}

    def dns_remove_server(self, *, server: str) -> dict[str, Any]:
        """Remove an upstream DNS server from the dnsmasq ``server`` list."""
        if not server or not self._DNS_SERVER_PATTERN.match(server):
            raise RouterManagementError("Invalid DNS server address.")
        ok, _ = self._dns_run(
            f"uci del_list dhcp.@dnsmasq[0].server={self._shell_single(server)} && "
            "uci commit dhcp && /etc/init.d/dnsmasq reload"
        )
        if not ok:
            return {"ok": False, "message": f"Could not remove upstream server {server}."}
        return {"ok": True, "message": f"Removed upstream server {server}."}

    def dns_add_host(self, *, hostname: str, ip: str) -> dict[str, Any]:
        """Append an ``ip hostname`` entry to ``/etc/hosts`` (safe add)."""
        self._validate_dns_host(hostname=hostname, ip=ip)
        ok, _ = self._dns_run(
            f"grep -q -e {self._shell_single(hostname)} /etc/hosts || "
            f"printf '%s\\t%s\\n' {self._shell_single(ip)} "
            f"{self._shell_single(hostname)} >> /etc/hosts"
        )
        if not ok:
            return {"ok": False, "message": f"Could not add host entry for {hostname}."}
        return {"ok": True, "message": f"Host entry for {hostname} added."}

    def dns_remove_host(self, *, hostname: str, ip: str) -> dict[str, Any]:
        """Remove a matching ``ip hostname`` line from ``/etc/hosts``."""
        self._validate_dns_host(hostname=hostname, ip=ip)
        escaped = re.escape(self._shell_single(hostname))
        ok, _ = self._dns_run(
            f"sed -i -e {self._shell_single(f'/{escaped}/d')} /etc/hosts"
        )
        if not ok:
            return {"ok": False, "message": f"Could not remove host entry for {hostname}."}
        return {"ok": True, "message": f"Host entry for {hostname} removed."}

    def run_dns_job(
        self,
        job_id: str,
        *,
        action: str,
        server: str | None,
        hostname: str | None,
        ip: str | None,
        enabled: bool,
    ) -> ManagementJob:
        """Execute a DNS change inside a tracked job.

        Actions: ``reload`` / ``restart`` (dnsmasq), ``set-enabled``,
        ``add-server`` / ``remove-server``, ``add-host`` / ``remove-host``.
        """
        self._jobs.transition(job_id, "running", message="Applying DNS change…")
        try:
            if action in ("reload", "restart"):
                result = self.action("reload-dhcp" if action == "reload" else "restart-dnsmasq")
                result["message"] = (
                    "DNS reloaded." if action == "reload" else "DNS server restarted."
                )
            elif action == "set-enabled":
                result = self.dns_set_enabled(enabled=enabled)
            elif action == "add-server":
                result = self.dns_add_server(server=server or "")
            elif action == "remove-server":
                result = self.dns_remove_server(server=server or "")
            elif action == "add-host":
                result = self.dns_add_host(hostname=hostname or "", ip=ip or "")
            elif action == "remove-host":
                result = self.dns_remove_host(hostname=hostname or "", ip=ip or "")
            else:
                raise RouterManagementError(f"Unsupported DNS action: {action}")
            self._jobs.transition(job_id, "succeeded", message=result["message"], result=result)
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("DNS action %r failed", action)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"DNS change failed: {exc}",
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    # -- network ----------------------------------------------------------- #

    _IFACE_PATTERN = re.compile(r"^[A-Za-z0-9_@.\-]+$")

    def _net_run(self, command: str) -> CommandResult:
        transport = self.open()
        try:
            return self.run(transport, command, timeout=90.0)
        finally:
            transport.close()

    def net_interface_restart(self, *, section: str) -> dict[str, Any]:
        """Restart one network interface (ifdown + ifup)."""
        if not section or not self._IFACE_PATTERN.match(section):
            raise RouterManagementError("Invalid interface name.")
        result = self._net_run(f"ifdown {section} 2>/dev/null; ifup {section}; true")
        return {
            "ok": result.ok,
            "message": (
                f"Interface {section} restarted."
                if result.ok
                else f"Interface {section} could not be restarted."
            ),
            "detail": result.to_dict(),
        }

    def net_interface_renew(self, *, section: str) -> dict[str, Any]:
        """Renew the DHCP lease on an interface."""
        if not section or not self._IFACE_PATTERN.match(section):
            raise RouterManagementError("Invalid interface name.")
        result = self._net_run(f"ifdown {section} 2>/dev/null; ifup {section}; true")
        return {
            "ok": result.ok,
            "message": (
                f"DHCP lease on {section} renewed."
                if result.ok
                else f"DHCP lease on {section} could not be renewed."
            ),
            "detail": result.to_dict(),
        }

    def net_interface_release(self, *, section: str) -> dict[str, Any]:
        """Release the DHCP lease and bring the interface down."""
        if not section or not self._IFACE_PATTERN.match(section):
            raise RouterManagementError("Invalid interface name.")
        result = self._net_run(f"ifdown {section}; true")
        return {
            "ok": result.ok,
            "message": (
                f"DHCP lease on {section} released."
                if result.ok
                else f"DHCP lease on {section} could not be released."
            ),
            "detail": result.to_dict(),
        }

    def net_interface_set_enabled(self, *, section: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable a persistent ``network`` interface and reload the network."""
        if not section or not self._IFACE_PATTERN.match(section):
            raise RouterManagementError("Invalid interface name.")
        base = (
            f"uci delete network.{section}.disabled"
            if enabled
            else f"uci set network.{section}.disabled='1'"
        )
        result = self._net_run(f"{base} && uci commit network && /etc/init.d/network reload")
        label = "enabled" if enabled else "disabled"
        return {
            "ok": result.ok,
            "message": (
                f"Interface {section} {label} and the network was reloaded."
                if result.ok
                else f"Interface {section} could not be {label}."
            ),
            "detail": result.to_dict(),
        }

    def run_network_job(
        self,
        job_id: str,
        *,
        action: str,
        section: str | None,
        enabled: bool = False,
    ) -> ManagementJob:
        """Execute a network interface operation inside a tracked job."""
        self._jobs.transition(job_id, "running", message="Applying network change…")
        try:
            if action == "interface-restart":
                result = self.net_interface_restart(section=section or "")
            elif action == "interface-renew":
                result = self.net_interface_renew(section=section or "")
            elif action == "interface-release":
                result = self.net_interface_release(section=section or "")
            elif action == "interface-enable":
                result = self.net_interface_set_enabled(section=section or "", enabled=True)
            elif action == "interface-disable":
                result = self.net_interface_set_enabled(section=section or "", enabled=False)
            else:
                raise RouterManagementError(f"Unsupported network action: {action}")
            self._jobs.transition(job_id, "succeeded", message=result["message"], result=result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Network action %r failed", action)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"Network command failed: {exc}",
            )
        return self._jobs.get(job_id)  # type: ignore[return-value]

    # -- processes --------------------------------------------------------- #

    # Emits "__AI_CPU_TOTAL__ <jiffies>", "__AI_MEM_TOTAL_KB__ <kb>", and one
    # "<uid>|__AI_UIDSEP__|<stat>|__AI_CMDSEP__|<cmdline>" line per process where
    # <stat> is the raw /proc/<pid>/stat line (its comm already wrapped in parens),
    # <cmdline> is the NUL-joined argv, and <uid> comes from /proc/<pid>/status.

    _PROCS_SCRIPT = (
        "tot=$(awk '{s=0;for(i=2;i<=NF;i++)s+=$i}END{print s}' /proc/stat 2>/dev/null); "
        "printf '__AI_CPU_TOTAL__ %s\\n' \"$tot\"; "
        "mem=$(awk '/^MemTotal:/{print $2}' /proc/meminfo 2>/dev/null); "
        "printf '__AI_MEM_TOTAL_KB__ %s\\n' \"$mem\"; "
        "for d in /proc/[0-9]*; do "
        "[ -r \"$d/stat\" ] || continue; "
        "p=${d#/proc/}; "
        "s=$(cat \"$d/stat\" 2>/dev/null) || continue; "
        "u=$(awk '/^Uid:/{print $2}' \"$d/status\" 2>/dev/null); "
        "c=$(cat \"$d/cmdline\" 2>/dev/null | tr '\\0' ' '); "
        "[ -n \"$u\" ] || u=0; "
        "printf '%s|__AI_UIDSEP__|%s|__AI_CMDSEP__|%s\\n' \"$u\" \"$s\" \"$c\"; "
        "done"
    )

    @staticmethod
    def _parse_proc_stat(stat: str) -> tuple[int, int, int, int] | None:
        """Return ``(utime, stime, vsize, rss_pages)`` from ``/proc/<pid>/stat``.

        Offsets are relative to the fields *after* the closing paren of the comm
        wrapping: state(0) ppid(1) pgrp(2) session(3) tty(4) tpgid(5) flags(6)
        minflt(7) cminflt(8) majflt(9) cmajflt(10) utime(11) stime(12) cutime(13)
        cstime(14) priority(15) nice(16) num_threads(17) itrealvalue(18)
        starttime(19) vsize(20) rss(21).
        """
        try:
            _pid, _, rest = stat.partition(")")
            cols = rest.split()
            if len(cols) < 22:
                return None
            return (int(cols[11]), int(cols[12]), int(cols[20]), int(cols[21]))
        except (ValueError, IndexError):
            return None

    def _collect_process_rows(
        self, transport: SSHTransport
    ) -> tuple[int, int, dict[str, dict[str, Any]]]:
        """Run the /proc sampler, returning (cpu_jiffies, mem_kb, pid -> row).

        Each row carries ``utime``/``stime`` ticks, ``vsz`` bytes, ``rss_pages``,
        the process's real-user d UID, its comm name, and its argv command line.
        """
        result = self.run(transport, self._PROCS_SCRIPT, timeout=30.0)
        cpu_total = 0
        mem_kb = 0
        rows: dict[str, dict[str, Any]] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("__AI_CPU_TOTAL__ "):
                token = line.split(None, 2)[1]
                if token.isdigit():
                    cpu_total = int(token)
            elif line.startswith("__AI_MEM_TOTAL_KB__ "):
                token = line.split(None, 3)[2]
                if token.isdigit():
                    mem_kb = int(token)
            elif "__AI_CMDSEP__" in line:
                uid, _, rest = line.partition("|__AI_UIDSEP__|")
                stat, _, cmdline = rest.partition("|__AI_CMDSEP__|")
                parsed = self._parse_proc_stat(stat)
                if parsed is None:
                    continue
                utime, stime, vsz, rss_pages = parsed
                tokens = stat.split()
                pid = tokens[0]
                comm = tokens[1] if len(tokens) > 1 else ""
                rows[pid] = {
                    "comm": comm.strip("()$"),
                    "cmd": cmdline.strip(),
                    "user": self._uid_name(int(uid)),
                    "utime": utime,
                    "stime": stime,
                    "vsz": vsz,
                    "rss_pages": rss_pages,
                }
        return cpu_total, mem_kb, rows

    @staticmethod
    def _uid_name(uid: int) -> str:
        """Map a numeric UID to a short account name (numeric fallback)."""
        return {
            0: "root",
            1: "daemon",
            2: "bin",
            3: "sys",
            4: "adm",
            7: "lp",
            8: "mail",
            13: "uucp",
            65: "nobody",
            1000: "www",
            65534: "nobody",
        }.get(uid, str(uid))

    def processes(self) -> dict[str, Any]:
        """Return a live process table with CPU and memory percentages."""
        transport = self.open()
        try:
            cpu_a, mem_total, a = self._collect_process_rows(transport)
            time.sleep(1.0)
            cpu_b, _, b = self._collect_process_rows(transport)
            cpus = int(
                self.run(
                    transport,
                    "grep -c '^processor' /proc/cpuinfo 2>/dev/null",
                    timeout=20.0,
                ).stdout.strip()
                or 1
            )
            cpus = max(1, cpus)
            cpu_delta = cpu_b - cpu_a
            elapsed_jiffies = max(cpu_delta, 1)
            mem_bytes = mem_total * 1024

            entries: list[dict[str, Any]] = []
            for pid, latest in b.items():
                prev = a.get(pid, latest)
                proc_delta = (latest["utime"] + latest["stime"]) - (
                    prev["utime"] + prev["stime"]
                )
                rss_bytes = latest["rss_pages"] * 4096
                cpu_pct = max(0.0, (proc_delta / elapsed_jiffies) * cpus * 100.0)
                mem_pct = (rss_bytes / mem_bytes * 100.0) if mem_bytes else None
                command = latest["cmd"] or latest["comm"]
                entries.append(
                    {
                        "pid": int(pid),
                        "cpu": round(cpu_pct, 1),
                        "mem": round(mem_pct, 1) if mem_pct is not None else None,
                        "rss": rss_bytes,
                        "vsz": latest["vsz"] or None,
                        "user": latest["user"],
                        "name": latest["comm"],
                        "command": command,
                    }
                )

            entries.sort(key=lambda entry: entry["pid"])
            return {
                "count": len(entries),
                "generated_at": datetime.now(UTC).isoformat(),
                "processes": entries,
            }
        finally:
            transport.close()

    def kill_process(self, pid: int) -> dict[str, Any]:
        """Send ``SIGTERM`` to a process and confirm termination."""
        if pid <= 0 or pid > 4_194_304:
            raise RouterManagementError("Invalid process id.")
        transport = self.open()
        try:
            result = self.run(transport, f"kill {pid}; wait {pid} 2>/dev/null; true", timeout=30.0)
            if not result.ok:
                return {
                    "ok": False,
                    "pid": pid,
                    "message": f"Could not signal process {pid} (exit {result.exit_code}).",
                    "detail": result.to_dict(),
                }
            return {
                "ok": True,
                "pid": pid,
                "message": f"SIGTERM sent to process {pid}.",
                "detail": result.to_dict(),
            }
        finally:
            transport.close()

    # -- system ------------------------------------------------------------ #

    # Collect every read-only system field in one SSH round trip, tagging each
    # block so the parser can attribute output unambiguously.
    _SYSTEM_GATHER_CMD = (
        "echo '==release=='; cat /etc/openwrt_release 2>/dev/null; "
        "echo '==boardjson=='; cat /etc/board.json 2>/dev/null; "
        "echo '==hostname=='; uci get system.@system[0].hostname 2>/dev/null "
        "|| hostname 2>/dev/null; "
        "echo '==timezone=='; uci get system.@system[0].timezone 2>/dev/null; "
        "echo '==zonename=='; uci get system.@system[0].zonename 2>/dev/null; "
        "echo '==language=='; uci get system.@system[0].language 2>/dev/null; "
        "echo '==notes=='; uci get system.@system[0].notes 2>/dev/null; "
        "echo '==localtime=='; date '+%Y-%m-%dT%H:%M:%S %z'; "
        "echo '==epoch=='; date +%s; "
        "echo '==uptime=='; cat /proc/uptime 2>/dev/null | cut -d' ' -f1; "
        "echo '==endian=='; printf '\\x01\\x00' | od -An -tx2 | tr -d ' \\n'; echo; "
        "echo '==mtd=='; cat /proc/mtd 2>/dev/null; "
        "echo '==mounts=='; cat /proc/mounts 2>/dev/null; "
        "echo '==dtnode=='; cat /proc/device-tree/model 2>/dev/null; "
        "echo '==uname=='; uname -s -r -m 2>/dev/null; "
        "echo '==ntpen=='; uci get system.ntp.enabled 2>/dev/null; "
        "echo '==ntpsrv=='; uci get system.ntp.server 2>/dev/null; "
        "echo '==ntpinfo=='; ubus call system ntpinfo 2>/dev/null; "
        "true"
    )

    _SYSTEM_MARKERS = frozenset(
        {
            "release", "boardjson", "hostname", "timezone", "zonename",
            "language", "notes", "localtime", "epoch", "uptime", "endian",
            "mtd", "mounts", "dtnode", "uname", "ntpen", "ntpsrv", "ntpinfo",
        }
    )

    def _system_gather(self, transport: SSHTransport) -> dict[str, str]:
        """Run the system gather command and split stdout into tagged blocks."""
        result = self.run(transport, self._SYSTEM_GATHER_CMD, timeout=60.0)
        sections: dict[str, str] = {}
        current: str | None = None
        buffer: list[str] = []
        for line in result.stdout.splitlines():
            marker = line[2:-2] if line.startswith("==") and line.endswith("==") else None
            if marker in self._SYSTEM_MARKERS:
                if current is not None:
                    sections[current] = "\n".join(buffer).strip()
                current = marker
                buffer = []
            elif current is not None:
                buffer.append(line)
        if current is not None:
            sections[current] = "\n".join(buffer).strip()
        return sections

    @staticmethod
    def _release_fields(text: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for line in text.splitlines():
            match = re.match(r"^([A-Z_]+)='?([^']*)'?", line)
            if match:
                fields[match.group(1)] = match.group(2)
        return fields

    def system_info(self) -> dict[str, Any]:
        """Return a read-only snapshot of the router's system configuration."""
        transport = self.open()
        try:
            gathered = self._system_gather(transport)

            release = self._release_fields(gathered.get("release", ""))
            board: dict[str, Any] = {}
            board_text = gathered.get("boardjson", "")
            if board_text:
                try:
                    board = json.loads(board_text)
                except json.JSONDecodeError:
                    board = {}
            board_release = board.get("release") or {}

            hostname = gathered.get("hostname", "").splitlines()[0].strip() or ""
            architecture = release.get("DISTRIB_ARCH") or ""
            target = release.get("DISTRIB_TARGET") or ""

            epoch_raw = gathered.get("epoch", "").strip()
            uptime_raw = gathered.get("uptime", "").strip()
            epoch = int(epoch_raw) if epoch_raw.isdigit() else None
            uptime = float(uptime_raw) if uptime_raw else None

            endian_raw = gathered.get("endian", "").strip()
            if endian_raw == "0001":
                endianness = "little"
            elif endian_raw == "0100":
                endianness = "big"
            else:
                endianness = None

            flash_bytes: int | None = None
            for line in gathered.get("mtd", "").splitlines():
                parts = line.split(":")
                if len(parts) >= 3:
                    try:
                        flash_bytes = (flash_bytes or 0) + int(parts[1].strip(), 16)
                    except ValueError:
                        continue

            root_fs: str | None = None
            overlay_fs: str | None = None
            for line in gathered.get("mounts", "").splitlines():
                tokens = line.split()
                if len(tokens) >= 3:
                    mountpoint, filesystem = tokens[1], tokens[2]
                    if mountpoint == "/":
                        root_fs = filesystem
                    elif mountpoint == "/overlay":
                        overlay_fs = filesystem

            ntp_servers = [line for line in gathered.get("ntpsrv", "").splitlines() if line.strip()]
            ntp_offset: float | None = None
            ntp_text = gathered.get("ntpinfo", "").strip()
            if ntp_text:
                try:
                    ntp_data = json.loads(ntp_text)
                    raw_offset = ntp_data.get("offset")
                    if isinstance(raw_offset, (int, float)):
                        ntp_offset = float(raw_offset)
                except json.JSONDecodeError:
                    ntp_offset = None

            firmware = release.get("DISTRIB_DESCRIPTION") or ""
            version = release.get("DISTRIB_REVISION") or board_release.get("revision") or ""

            now = datetime.now(UTC)
            return {
                "hostname": hostname,
                "model": (
                    board.get("model", {}).get("name")
                    or board.get("model", {}).get("id")
                    or ""
                ),
                "board": (
                    board.get("board", {}).get("name")
                    or board.get("board_name")
                    or ""
                ),
                "vendor": board.get("system") or "",
                "architecture": architecture,
                "target": target,
                "firmware": firmware,
                "release": (
                    release.get("DISTRIB_RELEASE")
                    or board_release.get("version")
                    or ""
                ),
                "revision": version,
                "build_date": board_release.get("builddate") or "",
                "kernel": board.get("kernel") or "".join(
                    gathered.get("uname", "").splitlines()[0].split()[1:2]
                ),
                "machine": (
                    " ".join(gathered.get("uname", "").splitlines()[0].split()[1:])
                    if gathered.get("uname")
                    else ""
                ),
                "device_tree": gathered.get("dtnode", "").splitlines()[0].strip() or "",
                "endianness": endianness,
                "flash_bytes": flash_bytes,
                "root_filesystem": root_fs,
                "overlay_filesystem": overlay_fs,
                "timezone": gathered.get("timezone", "").splitlines()[0].strip() or "",
                "zonename": gathered.get("zonename", "").splitlines()[0].strip() or "",
                "language": gathered.get("language", "").splitlines()[0].strip() or "",
                "notes": gathered.get("notes", "").strip() or "",
                "local_time": gathered.get("localtime", "").splitlines()[0].strip() or "",
                "epoch": epoch,
                "uptime_seconds": uptime,
                "boot_time": (epoch - uptime) if epoch is not None and uptime is not None else None,
                "ntp": {
                    "enabled": gathered.get("ntpen", "").strip() in ("1", "yes", "true"),
                    "servers": ntp_servers,
                    "offset": ntp_offset,
                },
                "generated_at": now.isoformat(),
            }
        finally:
            transport.close()

    _HOSTNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{1,63}$")
    _TIMEZONE_PATTERN = re.compile(r"^[A-Za-z0-9_+./\-]{1,64}$")

    def system_set_config(
        self,
        *,
        hostname: str | None,
        timezone: str | None,
        language: str | None,
        notes: str | None,
    ) -> dict[str, Any]:
        """Apply hostname/timezone/language/notes via ``uci`` and commit."""
        if hostname is not None and not self._HOSTNAME_PATTERN.match(hostname):
            raise RouterManagementError("Invalid hostname.")
        if timezone is not None and not self._TIMEZONE_PATTERN.match(timezone):
            raise RouterManagementError("Invalid timezone.")

        commands: list[str] = []
        hostname_value: str | None = None
        if hostname is not None:
            commands.append(f"uci set system.@system[0].hostname='{hostname}'")
            hostname_value = hostname
        if timezone is not None:
            commands.append(f"uci set system.@system[0].timezone='{timezone}'")
        if language is not None:
            commands.append(f"uci set system.@system[0].language='{language}'")
        if notes is not None:
            if notes:
                commands.append(f"uci set system.@system[0].notes='{notes}'")
            else:
                commands.append("uci delete system.@system[0].notes")

        if not commands:
            return {"ok": True, "message": "No changes provided.", "detail": None}

        if hostname_value is not None:
            commands.append(f"echo '{hostname_value}' > /proc/sys/kernel/hostname")
        commands.append("uci commit system")
        commands.append("/etc/init.d/sysntpd restart")

        transport = self.open()
        try:
            script = " && ".join(commands) + " || true"
            result = self.run(transport, script, timeout=90.0)
            return {
                "ok": result.ok,
                "message": (
                    "System settings saved and applied."
                    if result.ok
                    else "System settings could not be saved."
                ),
                "detail": result.to_dict(),
            }
        finally:
            transport.close()

    def run_system_job(
        self,
        job_id: str,
        *,
        action: str,
        hostname: str | None = None,
        timezone: str | None = None,
        language: str | None = None,
        notes: str | None = None,
    ) -> ManagementJob:
        """Execute a system configuration change inside a tracked job."""
        self._jobs.transition(job_id, "running", message="Applying system settings…")
        try:
            if action != "save-config":
                raise RouterManagementError(f"Unsupported system action: {action}")
            result = self.system_set_config(
                hostname=hostname,
                timezone=timezone,
                language=language,
                notes=notes,
            )
            self._jobs.transition(job_id, "succeeded", message=result["message"], result=result)
        except Exception as exc:  # noqa: BLE001 - surfaced as a job failure
            logger.exception("System action %r failed", action)
            self._jobs.transition(
                job_id,
                "failed",
                error=str(exc),
                message=f"System settings could not be saved: {exc}",
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
