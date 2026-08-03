"""Router agent error hierarchy.

Collectors catch these to record per-collector failures in the snapshot; they
never abort the whole collection. The agent is data-collection-only — no AI
logic lives here.
"""


class RouterAgentError(Exception):
    """Base class for all router agent errors."""


class ConnectionFailedError(RouterAgentError):
    """The device could not be reached (SSH refused, auth failed, etc.)."""


class CommandError(RouterAgentError):
    """A remote command failed (non-zero exit or parse error)."""


class UbusError(RouterAgentError):
    """A ubus call failed."""


class LuciRpcError(RouterAgentError):
    """A LuCI JSON-RPC call failed."""
