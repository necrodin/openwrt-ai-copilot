"""Kernel / board identity collector.

Source: ``ubus call system board``. Also used by the snapshot to populate the
meta block (hostname, model, firmware). Stores the raw board dict in the shared
context state so other collectors/snapshot can reuse it.
"""

from __future__ import annotations

from contextlib import suppress

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import KernelInfo

_BOARD_STATE_KEY = "system.board"


class KernelCollector(Collector):
    name = "kernel"

    def collect(self, ctx: CollectorContext) -> KernelInfo:
        board: dict = {}
        with suppress(Exception):  # noqa: BLE001 - empty identity is acceptable
            board = ctx.ubus.call("system", "board")
        ctx.state[_BOARD_STATE_KEY] = board
        return KernelInfo(
            kernel=str(board.get("kernel") or ""),
            release=str(board.get("release") or ""),
            hostname=str(board.get("hostname") or ""),
            model=str(board.get("model") or ""),
            architecture=str(board.get("architecture") or ""),
            board=str(board.get("board_name") or ""),
            system=str(board.get("system") or ""),
            version=str(board.get("version") or ""),
        )
