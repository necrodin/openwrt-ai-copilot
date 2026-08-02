"""SSH configuration and credentials.

``SSHCredentials`` carries the authentication material (password and/or private
key); ``SSHConfig`` carries everything else needed to open and keep a pool of
SSH connections: host, port, timeouts, keep-alive, pool sizing, retries, host
key verification, and the backend to use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from router_agent.config import AgentConfig

__all__ = ["HOST_KEY_POLICIES", "SSHCredentials", "SSHConfig"]

HOST_KEY_POLICIES = ("auto", "system", "reject")

BACKENDS = ("asyncssh", "paramiko", "mock")


@dataclass(frozen=True)
class SSHCredentials:
    """Authentication material for an SSH connection."""

    username: str = "root"
    password: str | None = None
    #: Inline PEM private key data (takes precedence over ``private_key_path``).
    private_key: str | None = None
    #: Path to a private key file.
    private_key_path: Path | None = None
    private_key_passphrase: str | None = None

    @property
    def has_password(self) -> bool:
        return bool(self.password)

    @property
    def has_private_key(self) -> bool:
        return self.private_key is not None or self.private_key_path is not None

    @property
    def authenticate_with_key(self) -> bool:
        return self.has_private_key


@dataclass(frozen=True)
class SSHConfig:
    """Everything needed to open and keep SSH connections."""

    host: str
    port: int = 22
    #: Connect timeout in seconds.
    timeout: float = 15.0
    #: Per-command timeout in seconds.
    command_timeout: float = 20.0
    #: Keep-alive ping interval in seconds (0 disables).
    keepalive_interval: float = 30.0
    #: Maximum concurrent connections.
    pool_size: int = 4
    #: Number of automatic retries on transient connect/command failures.
    retry_count: int = 2
    #: Delay between retries in seconds.
    retry_delay: float = 0.5
    #: "auto" (trust-on-first-use), "system" (system known_hosts), "reject".
    host_key_policy: str = "auto"
    #: Path to a known_hosts file; strict verification is used when set.
    known_hosts: Path | None = None
    #: Backend: "asyncssh" | "paramiko" | "mock" | None (auto = asyncssh when
    #: installed, else paramiko).
    backend: str | None = None
    credentials: SSHCredentials = field(default_factory=SSHCredentials)

    def __post_init__(self) -> None:
        if self.port < 1 or self.port > 65535:
            raise ValueError("SSH port must be in 1..65535")
        if self.pool_size < 1:
            raise ValueError("SSH pool_size must be >= 1")
        if self.retry_count < 0:
            raise ValueError("SSH retry_count must be >= 0")
        if self.timeout <= 0 or self.command_timeout <= 0:
            raise ValueError("SSH timeouts must be positive")
        if self.host_key_policy not in HOST_KEY_POLICIES:
            raise ValueError(f"host_key_policy must be one of {HOST_KEY_POLICIES}")
        if self.backend is not None and self.backend not in BACKENDS:
            raise ValueError(f"backend must be one of {BACKENDS} or None")

    @classmethod
    def from_agent_config(cls, config: AgentConfig) -> SSHConfig:
        """Build an ``SSHConfig`` from the router agent's own settings."""
        return cls(
            host=config.host,
            port=config.port,
            timeout=config.ssh_timeout,
            command_timeout=config.command_timeout,
            credentials=SSHCredentials(
                username=config.username,
                password=config.password,
                private_key_path=config.ssh_key_path,
            ),
        )
