"""Snapshot assembler.

Runs the selected collectors and merges their normalized results into ONE
:class:`DeviceSnapshot`. Every collector runs in isolation: a failure in one
section is recorded under ``errors`` and never aborts the rest of the
collection.
"""

from __future__ import annotations

from datetime import UTC, datetime

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.collectors.kernel import KernelInfo
from router_agent.model import CollectError, DeviceSnapshot, SnapshotMeta


def build_snapshot(
    ctx: CollectorContext,
    collectors: list[Collector],
    *,
    device_id: str,
    transport: str,
    host: str,
) -> DeviceSnapshot:
    """Collect every section and assemble a single normalized snapshot."""
    results: dict[str, object] = {}
    errors: list[CollectError] = []
    ran: list[str] = []

    for collector in collectors:
        ran.append(collector.name)
        try:
            results[collector.name] = collector.collect(ctx)
        except Exception as exc:  # noqa: BLE001 - contain per-collector failures
            errors.append(CollectError(collector=collector.name, error=str(exc)))

    kernel = results.get("kernel")
    if not isinstance(kernel, KernelInfo):
        kernel = KernelInfo()
        try:
            board = ctx.ubus.call("system", "board")
            kernel = KernelInfo(
                kernel=str(board.get("kernel") or ""),
                release=str(board.get("release") or ""),
                hostname=str(board.get("hostname") or ""),
                model=str(board.get("model") or ""),
                architecture=str(board.get("architecture") or ""),
                board=str(board.get("board_name") or ""),
                system=str(board.get("system") or ""),
                version=str(board.get("version") or ""),
            )
            results["kernel"] = kernel
        except Exception:  # noqa: BLE001 - identity is best-effort
            pass

    meta = SnapshotMeta(
        collected_at=datetime.now(UTC),
        device_id=device_id,
        transport=transport,
        host=host,
        board=kernel.board,
        model=kernel.model,
        firmware=kernel.release,
        collectors_run=ran,
    )

    from router_agent.model import DhcpInfo, FirewallInfo, LogInfo, NetworkStatus, WifiInfo

    network_status = None
    raw_status = ctx.state.get("network_status")
    if isinstance(raw_status, dict):
        network_status = NetworkStatus(
            gateway=raw_status.get("gateway"),
            dns=raw_status.get("dns") or [],
            wan_interface=raw_status.get("wan_interface"),
        )

    return DeviceSnapshot(
        meta=meta,
        cpu=results.get("cpu"),
        memory=results.get("memory"),
        temperature=results.get("temperature", []),
        storage=results.get("storage", []),
        network=results.get("network", []),
        network_status=network_status,
        firewall=results.get("firewall") or FirewallInfo(),
        wifi=results.get("wifi") or WifiInfo(),
        clients=results.get("clients", []),
        arp=results.get("arp", []),
        routing=results.get("routing", []),
        vpn=results.get("vpn", []),
        dhcp=results.get("dhcp") or DhcpInfo(),
        packages=results.get("packages", []),
        services=results.get("services", []),
        kernel=kernel,
        logs=results.get("logs") or LogInfo(),
        errors=errors,
    )


__all__ = ["build_snapshot"]
