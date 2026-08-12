"""Kernel / board identity collector.

Source: ``ubus call system board``. Also used by the snapshot to populate the
meta block (hostname, model, firmware). Stores the raw board dict in the shared
context state so other collectors/snapshot can reuse it.

On modern OpenWrt the ``release`` field is a *dict* (``distribution``,
``version``, ``revision``, ``target``, ``description``); older firmware returns
a plain string. The collector parses both into structured fields so consumers
never see a raw Python ``repr`` of the dict.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import KernelInfo

_BOARD_STATE_KEY = "system.board"


def _parse_release(raw: Any) -> dict[str, str | None]:
    """Parse the ``release`` value of ``ubus system board`` into fields."""
    if isinstance(raw, dict):
        keys = ("distribution", "version", "revision", "target", "description")
        clean = {key: _clean(raw.get(key)) for key in keys}
        build_date = None
        for key in ("date", "build_date", "timestamp"):
            value = raw.get(key)
            if value is not None and str(value).strip():
                build_date = str(value).strip()
                break
        return {
            "distribution": clean["distribution"],
            "release_version": clean["version"],
            "revision": clean["revision"],
            "target": clean["target"],
            "release_description": clean["description"],
            "build_date": build_date,
        }
    text = _clean(raw)
    return {
        "distribution": None,
        "release_version": text,
        "revision": None,
        "target": None,
        "release_description": text,
        "build_date": None,
    }


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class KernelCollector(Collector):
    name = "kernel"

    def collect(self, ctx: CollectorContext) -> KernelInfo:
        board: dict = {}
        with suppress(Exception):  # noqa: BLE001 - empty identity is acceptable
            board = ctx.ubus.call("system", "board")
        ctx.state[_BOARD_STATE_KEY] = board

        parsed = _parse_release(board.get("release"))
        release = parsed["release_description"] or parsed["release_version"] or ""
        return KernelInfo(
            kernel=str(board.get("kernel") or ""),
            release=release,
            hostname=str(board.get("hostname") or ""),
            model=str(board.get("model") or ""),
            architecture=str(board.get("architecture") or ""),
            board=str(board.get("board_name") or ""),
            system=str(board.get("system") or ""),
            version=str(board.get("version") or ""),
            distribution=parsed["distribution"],
            release_version=parsed["release_version"],
            revision=parsed["revision"],
            target=parsed["target"],
            release_description=parsed["release_description"],
            build_date=parsed["build_date"],
        )
