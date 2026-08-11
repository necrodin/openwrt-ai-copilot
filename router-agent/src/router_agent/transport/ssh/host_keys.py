"""Persisted SSH host-key trust store (known_hosts equivalent).

Replaces the previous ``host_key_policy="auto"`` behavior that disabled host-key
verification entirely. Both SSH backends now route every host-key decision
through :func:`verify_host_key` and a :class:`HostKeyStore`, so verification is
identical regardless of the backend in use.

Trust model
-----------
* ``auto`` (default) — trust-on-first-use (TOFU). The first host key seen for a
  given ``(host, port)`` is recorded and trusted; a later *different* key for
  the same host/port is rejected (fail closed). This preserves first-time
  onboarding usability while ensuring a changed host key is never silently
  accepted.
* ``reject`` — strict. Unknown hosts are rejected; a recorded key is required.
* ``system`` / an explicit ``known_hosts`` path — strict verification handled by
  the SSH library against the OpenSSH known_hosts file.

Router IP changes keep working because trust is keyed by the configured
``(host, port)`` string. Re-onboarding after an IP change simply records the new
host/port the first time the router connects under its new address; the same
host key keeps verifying if the address is unchanged.

Default location
----------------
The store file defaults to ``data/known_hosts`` (resolved against the working
directory, matching the SQLite database default) and can be overridden with the
``OPENWRT_AI_KNOWN_HOSTS`` environment variable or by passing an explicit
``known_hosts`` path to the transport/``SSHConfig``.

Format
------
One entry per line: ``<host> <port> <key_type> <base64_key_blob>``. Lines
starting with ``#`` are ignored. Writes are atomic (temp file + rename) and the
file is created with ``0600`` permissions.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from router_agent.transport.ssh.config import SSHConfig

logger = logging.getLogger(__name__)

#: Default store path (CWD-relative, mirroring the default SQLite database).
DEFAULT_KNOWN_HOSTS = "data/known_hosts"

#: Environment variable that overrides the default store path.
KNOWN_HOSTS_ENV = "OPENWRT_AI_KNOWN_HOSTS"

#: Outcomes of a :meth:`HostKeyStore.check` call.
TRUSTED = "trusted"
UNKNOWN = "unknown"
MISMATCH = "mismatch"

#: Guards all file access so concurrent transports sharing one store stay safe.
_STORE_LOCK = threading.Lock()


@dataclass(frozen=True)
class HostKeyRecord:
    """One persisted ``(host, port) -> host key`` entry."""

    host: str
    port: int
    key_type: str
    #: Base64-encoded raw public key material (no algorithm prefix).
    key_blob: str


def default_known_hosts_path() -> Path:
    """Return the default known_hosts store path for this process."""
    env = os.environ.get(KNOWN_HOSTS_ENV)
    if env:
        return Path(env)
    return Path(DEFAULT_KNOWN_HOSTS)


class HostKeyStore:
    """A thread-safe, file-backed host-key trust store."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._records: dict[tuple[str, int], list[HostKeyRecord]] | None = None

    # -- public API --------------------------------------------------------- #

    def trusted_keys(self, host: str, port: int) -> list[HostKeyRecord]:
        """Return the recorded host keys for ``host:port``."""
        return list(self._entries().get((host, port), []))

    def check(self, host: str, port: int, key_type: str, key_blob: str) -> str:
        """Return ``TRUSTED``, ``UNKNOWN``, or ``MISMATCH`` for a presented key."""
        entries = self.trusted_keys(host, port)
        for entry in entries:
            if entry.key_type == key_type and entry.key_blob == key_blob:
                return TRUSTED
        return MISMATCH if entries else UNKNOWN

    def record(self, host: str, port: int, key_type: str, key_blob: str) -> None:
        """Record a host key for ``host:port`` and persist it (idempotent)."""
        with _STORE_LOCK:
            entries = self._entries_locked()
            existing = entries.setdefault((host, port), [])
            for entry in existing:
                if entry.key_type == key_type and entry.key_blob == key_blob:
                    return
            existing.append(
                HostKeyRecord(host=host, port=port, key_type=key_type, key_blob=key_blob)
            )
            self._write_locked()

    # -- internals ---------------------------------------------------------- #

    def _entries(self) -> dict[tuple[str, int], list[HostKeyRecord]]:
        with _STORE_LOCK:
            return self._entries_locked()

    def _entries_locked(self) -> dict[tuple[str, int], list[HostKeyRecord]]:
        if self._records is None:
            self._records = self._load()
        return self._records

    def _load(self) -> dict[tuple[str, int], list[HostKeyRecord]]:
        records: dict[tuple[str, int], list[HostKeyRecord]] = {}
        if not self._path.exists():
            return records
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read known_hosts store %s: %s", self._path, exc)
            return records
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 4:
                continue
            host, port_text, key_type, key_blob = parts
            try:
                port = int(port_text)
            except ValueError:
                continue
            records.setdefault((host, port), []).append(
                HostKeyRecord(host=host, port=port, key_type=key_type, key_blob=key_blob)
            )
        return records

    def _write_locked(self) -> None:
        lines = ["# OpenWrt AI Copilot SSH known hosts (host port key_type key_blob)"]
        for (host, port), entries in sorted(self._records.items()):
            for entry in sorted(entries, key=lambda item: item.key_type):
                lines.append(f"{host} {port} {entry.key_type} {entry.key_blob}")
        text = "\n".join(lines) + "\n"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_name(f"{self._path.name}.tmp")
        temp.write_text(text, encoding="utf-8")
        with suppress(OSError):  # pragma: no cover - best effort on exotic filesystems
            os.chmod(temp, 0o600)
        os.replace(temp, self._path)


def host_key_settings(
    config: SSHConfig,
) -> tuple[HostKeyStore | None, bool]:
    """Resolve the host-key verification inputs for ``config``.

    Returns a ``(store, allow_tou)`` pair. ``store`` is ``None`` when
    verification is delegated to the SSH library (system known_hosts or an
    explicit known_hosts path); otherwise the caller must route every presented
    host key through :func:`verify_host_key`.

    * ``known_hosts`` path set    -> ``(None, False)`` strict, library-handled.
    * ``host_key_policy="system"`` -> ``(None, False)`` strict, library-handled.
    * ``host_key_policy="reject"`` -> strict store at the default app path.
    * ``host_key_policy="auto"``   -> TOFU store at the default app path.
    """
    if config.known_hosts is not None or config.host_key_policy == "system":
        return None, False
    if config.host_key_policy == "reject":
        return HostKeyStore(default_known_hosts_path()), False
    return HostKeyStore(default_known_hosts_path()), True


def verify_host_key(
    store: HostKeyStore,
    host: str,
    port: int,
    key_type: str,
    key_blob: str,
    *,
    allow_tou: bool,
) -> tuple[bool, str | None]:
    """Decide whether to accept a presented host key.

    Returns ``(accepted, reason)``. When accepted, an unknown key is recorded so
    later connections with the same key are trusted and a later different key is
    rejected. A trusted key that has since changed always returns ``(False,
    ...)`` regardless of ``allow_tou``.
    """
    status = store.check(host, port, key_type, key_blob)
    if status == TRUSTED:
        return True, None
    if status == MISMATCH:
        return False, f"host key for {host}:{port} has changed"
    if allow_tou:
        store.record(host, port, key_type, key_blob)
        return True, None
    return False, f"host key for {host}:{port} is not trusted"
