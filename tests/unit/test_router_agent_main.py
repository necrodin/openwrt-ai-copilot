"""CLI tests: argument parsing, config mapping, output behavior, error paths."""

from __future__ import annotations

import json

import pytest

from router_agent.errors import CommandError, ConnectionFailedError
from router_agent.main import _build_config, build_parser, collect, main


def test_parser_requires_collect_command() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_only_exposes_all_collector_names() -> None:
    parser = build_parser()
    collect_parser = [p for p in parser._actions if p.dest == "command"][0].choices["collect"]
    only = [a for a in collect_parser._actions if a.dest == "only"][0]
    choices = set(only.choices)
    assert {
        "cpu",
        "memory",
        "temperature",
        "storage",
        "network",
        "firewall",
        "wifi",
        "clients",
        "arp",
        "routing",
        "vpn",
        "dhcp",
        "packages",
        "services",
        "kernel",
        "logs",
    } == choices


def test_build_config_maps_args() -> None:
    args = build_parser().parse_args(
        [
            "collect",
            "--host",
            "192.168.1.1",
            "--port",
            "2222",
            "--username",
            "root",
            "--key",
            "~/.ssh/id_ed25519",
            "--luci-url",
            "http://192.168.1.1",
            "--only",
            "cpu",
            "kernel",
            "--exclude",
            "logs",
            "--log-lines",
            "50",
        ]
    )
    config = _build_config(args)
    assert config.host == "192.168.1.1"
    assert config.port == 2222
    assert config.luci_url == "http://192.168.1.1"
    assert config.enabled_collectors == {"cpu", "kernel"}
    assert config.disabled_collectors == {"logs"}
    assert config.log_lines == 50


def test_collect_without_host_raises() -> None:
    args = build_parser().parse_args(["collect"])
    with pytest.raises(ConnectionFailedError):
        collect(args)


def test_collect_writes_one_json_file(monkeypatch, tmp_path) -> None:
    class OfflineRunner:
        def run(self, command: str, *, timeout: float | None = None) -> str:
            raise CommandError("offline test device")

        def close(self) -> None:
            pass

    monkeypatch.setattr("router_agent.main._connect_ssh", lambda _config: OfflineRunner())
    out_file = tmp_path / "snapshot.json"
    args = build_parser().parse_args(
        ["collect", "--host", "192.168.1.1", "--output", str(out_file)]
    )
    assert collect(args) == 0
    payload = json.loads(out_file.read_text())
    assert payload["meta"]["host"] == "192.168.1.1"
    assert payload["meta"]["transport"] == "ssh"
    assert isinstance(payload["errors"], list)
    assert "cpu" in payload  # lenient collectors still produce a valid snapshot


def test_collect_prints_json_to_stdout(monkeypatch, capsys) -> None:
    class OfflineRunner:
        def run(self, command: str, *, timeout: float | None = None) -> str:
            raise CommandError("offline test device")

        def close(self) -> None:
            pass

    monkeypatch.setattr("router_agent.main._connect_ssh", lambda _config: OfflineRunner())
    args = build_parser().parse_args(["collect", "--host", "192.168.1.1"])
    assert collect(args) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert "meta" in payload


def test_main_connection_error_exits_2(monkeypatch, capsys) -> None:
    def _connect(_config):
        raise ConnectionFailedError("SSH connect to 192.168.1.1: boom")

    monkeypatch.setattr("router_agent.main._connect_ssh", _connect)
    code = main(["collect", "--host", "192.168.1.1"])
    assert code == 2
    assert "error:" in capsys.readouterr().err
