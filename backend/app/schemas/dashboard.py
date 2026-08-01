"""Live dashboard wire schema.

One ``DashboardUpdate`` is broadcast to every connected dashboard WebSocket
subscriber on each poll. When the device is unreachable the last good snapshot
is retained and ``connected`` flips to ``False`` with a human-readable error.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from router_agent.model import DeviceSnapshot


class DashboardUpdate(BaseModel):
    type: Literal["update"] = "update"
    sequence: int
    sent_at: datetime
    source: Literal["ssh", "local", "simulated"]
    device_id: str
    connected: bool = True
    error: str | None = None
    snapshot: DeviceSnapshot | None = None
