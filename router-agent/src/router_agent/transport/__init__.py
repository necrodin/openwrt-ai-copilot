"""Transport abstraction for reaching OpenWrt devices.

The agent never talks to vendors — it executes commands over SSH (or runs
locally on the device) and calls ubus either through the shell or through LuCI's
HTTP JSON-RPC interface. All three paths converge on the same
:class:`CommandRunner` / :class:`UbusClient` contracts used by collectors.
"""

from router_agent.transport.base import CommandRunner
from router_agent.transport.local import LocalTransport
from router_agent.transport.luci import LuciRpcClient
from router_agent.transport.ssh import SSHTransport
from router_agent.transport.ubus import UbusClient

__all__ = [
    "CommandRunner",
    "LocalTransport",
    "LuciRpcClient",
    "SSHTransport",
    "UbusClient",
]
