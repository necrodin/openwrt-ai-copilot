"""Router agent CLI entry point.

The agent collects data only: it connects to a router (SSH, or runs locally,
optionally using LuCI RPC) and prints ONE normalized JSON snapshot to stdout.
There is no AI and no dashboard.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from router_agent.collectors import COLLECTOR_NAMES, select_collectors
from router_agent.collectors.base import CollectorContext
from router_agent.config import AgentConfig
from router_agent.errors import ConnectionFailedError
from router_agent.snapshot import build_snapshot
from router_agent.transport.local import LocalTransport
from router_agent.transport.luci import LuciRpcClient
from router_agent.transport.ssh import SSHTransport
from router_agent.transport.ubus import UbusClient

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="router-agent",
        description=(
            "OpenWrt AI Copilot — on-device router agent. Collects a normalized "
            "JSON snapshot of a router's state (data collection only)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect", help="Collect and print one snapshot")
    connect = collect.add_argument_group("connection")
    connect.add_argument("--host", default="", help="Router IP/hostname")
    connect.add_argument("--port", type=int, default=22)
    connect.add_argument("--username", default="root")
    connect.add_argument("--key", type=Path, help="SSH private key path")
    connect.add_argument("--password", help="SSH password (avoid on shared shells)")
    connect.add_argument("--local", action="store_true", help="Run on the router itself")
    connect.add_argument("--luci-url", help="LuCI base URL, e.g. http://192.168.1.1")
    connect.add_argument("--luci-username", default="root")
    connect.add_argument("--luci-password")

    collect.add_argument("--device-id", default="", help="Stable device identifier")
    collect.add_argument("--command-timeout", type=float, default=20.0)
    collect.add_argument("--log-lines", type=int, default=200)
    collect.add_argument(
        "--only",
        nargs="*",
        choices=sorted(COLLECTOR_NAMES),
        help="Collect only these sections",
    )
    collect.add_argument(
        "--exclude",
        nargs="*",
        choices=sorted(COLLECTOR_NAMES),
        help="Skip these sections",
    )
    collect.add_argument("--output", help="Write JSON to this file instead of stdout")
    return parser


def _build_config(args: argparse.Namespace) -> AgentConfig:
    return AgentConfig(
        device_id=args.device_id,
        host=args.host,
        port=args.port,
        username=args.username,
        ssh_key_path=args.key,
        password=args.password,
        luci_url=args.luci_url,
        luci_username=args.luci_username,
        luci_password=args.luci_password,
        command_timeout=args.command_timeout,
        log_lines=args.log_lines,
        enabled_collectors=set(args.only or []),
        disabled_collectors=set(args.exclude or []),
    )


def collect(args: argparse.Namespace) -> int:
    config = _build_config(args)

    runner = LocalTransport() if args.local else _connect_ssh(config)
    luci = None
    if args.luci_url:
        luci = LuciRpcClient(
            args.luci_url,
            username=args.luci_username,
            password=args.luci_password,
        )
    ubus = UbusClient(runner, timeout=config.command_timeout)

    ctx = CollectorContext(
        runner=runner,
        ubus=ubus,
        luci=luci,
        config=config,
    )
    try:
        snapshot = build_snapshot(
            ctx,
            select_collectors(config),
            device_id=config.device_id or config.host or "unconfigured",
            transport="local" if args.local else "ssh",
            host=args.host,
        )
    finally:
        runner.close()
        if luci is not None:
            luci.close()

    payload = json.dumps(snapshot.model_dump(), indent=2, default=str)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


def _connect_ssh(config: AgentConfig) -> SSHTransport:
    if not config.host:
        raise ConnectionFailedError("No --host given; provide a router address or use --local")
    return SSHTransport(
        config.host,
        port=config.port,
        username=config.username,
        password=config.password,
        key_path=config.ssh_key_path,
        command_timeout=config.command_timeout,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            return collect(args)
    except ConnectionFailedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error("unknown command")


if __name__ == "__main__":
    sys.exit(main())
