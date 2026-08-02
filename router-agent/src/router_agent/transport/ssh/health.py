"""SSH connection health reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

__all__ = ["SSHHealth"]


@dataclass(frozen=True)
class SSHHealth:
    """Result of a connection validation / health probe."""

    ok: bool
    host: str
    port: int
    backend: str
    connected: bool
    #: Round-trip latency of the probe in milliseconds.
    latency_ms: float | None = None
    error: str | None = None
    #: The probe command that was run to validate the connection.
    probe: str | None = None
    probe_output: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def success(
        cls,
        *,
        host: str,
        port: int,
        backend: str,
        latency_ms: float | None = None,
        probe: str | None = None,
        probe_output: str | None = None,
    ) -> SSHHealth:
        return cls(
            ok=True,
            host=host,
            port=port,
            backend=backend,
            connected=True,
            latency_ms=latency_ms,
            probe=probe,
            probe_output=probe_output,
        )

    @classmethod
    def failure(
        cls,
        *,
        host: str,
        port: int,
        backend: str,
        error: str,
        connected: bool = False,
        latency_ms: float | None = None,
    ) -> SSHHealth:
        return cls(
            ok=False,
            host=host,
            port=port,
            backend=backend,
            connected=connected,
            latency_ms=latency_ms,
            error=error,
        )
