"""SSH transport error hierarchy.

The classes deliberately sit on top of the existing error families so that
existing ``except`` clauses keep working:

- :class:`ConnectionError` is also a :class:`router_agent.errors.ConnectionFailedError`
  (the CLI and dashboard catch that on connect failure).
- :class:`TimeoutError` is also the built-in ``TimeoutError`` (and therefore
  ``asyncio.TimeoutError`` on Python 3.11+).
"""

from __future__ import annotations

import builtins

from router_agent.errors import ConnectionFailedError, RouterAgentError

__all__ = [
    "SSHError",
    "AuthenticationError",
    "ConnectionError",
    "HostKeyError",
    "TimeoutError",
]


class SSHError(RouterAgentError):
    """Base class for all SSH transport errors."""


class AuthenticationError(SSHError):
    """SSH authentication failed (bad username, password, or key)."""


class ConnectionError(SSHError, ConnectionFailedError):
    """The device could not be reached (refused, unreachable, reset, ...)."""


class HostKeyError(SSHError):
    """Host key verification failed."""


class TimeoutError(SSHError, builtins.TimeoutError):
    """An SSH operation exceeded its timeout."""
