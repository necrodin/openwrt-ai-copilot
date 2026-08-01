"""Transport tests: local runner, ubus decoding, LuCI JSON-RPC."""

from __future__ import annotations

import json

import httpx
import pytest

from router_agent.errors import CommandError, LuciRpcError, UbusError
from router_agent.transport.base import clean_output
from router_agent.transport.local import LocalTransport
from router_agent.transport.luci import LuciRpcClient
from router_agent.transport.ubus import UbusClient
from tests.unit.router_agent_helpers import FakeRunner


def test_clean_output_strips_crlf() -> None:
    assert clean_output("a\r\nb\r\n") == "a\nb"


def test_local_transport_run_and_close() -> None:
    transport = LocalTransport()
    assert transport.run("printf 'hi\\n'") == "hi"
    assert transport.run("printf 'a\\r\\nb\\n'") == "a\nb"
    transport.close()
    with pytest.raises(CommandError):
        transport.run("true")


def test_local_transport_nonzero_exit_raises() -> None:
    transport = LocalTransport()
    with pytest.raises(CommandError):
        transport.run("exit 3")


def test_ubus_call_decodes_json() -> None:
    runner = FakeRunner({"ubus call system board": json.dumps({"hostname": "router"})})
    ubus = UbusClient(runner)
    assert ubus.call("system", "board") == {"hostname": "router"}
    assert "ubus call system board" in runner.calls


def test_ubus_call_with_params_encodes_json() -> None:
    runner = FakeRunner({"ubus call iwinfo info": "{}"})
    ubus = UbusClient(runner)
    ubus.call("iwinfo", "info", params={"device": "radio0"})
    command = runner.calls[0]
    assert command == 'ubus call iwinfo info {"device":"radio0"}'


def test_ubus_call_non_json_raises() -> None:
    runner = FakeRunner({"ubus call system board": "not json"})
    with pytest.raises(UbusError):
        UbusClient(runner).call("system", "board")


def test_ubus_call_failure_wrapped() -> None:
    runner = FakeRunner({})  # no scripted output -> CommandError
    with pytest.raises(UbusError):
        UbusClient(runner).call("system", "board")


def test_ubus_available() -> None:
    runner = FakeRunner({"ubus list": "system\nsession\n"})
    assert UbusClient(runner).available() is True
    assert UbusClient(FakeRunner({})).available() is False


def _luci_client(handler):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return client


def test_luci_login_and_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        params = body["params"]
        session, obj, method = params[0], params[1], params[2]
        if obj == "session" and method == "login":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 1, "result": [0, {"ubus_rpc_session": "abc123"}]},
            )
        assert session == "abc123"
        assert (obj, method) == ("system", "board")
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": [0, {"hostname": "router"}]}
        )

    client = _luci_client(handler)
    luci = LuciRpcClient("http://luci", username="root", password="secret", client=client)
    assert luci.session == "abc123"
    assert luci.call("system", "board") == {"hostname": "router"}
    luci.close()


def test_luci_call_error_code_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": [-32002, "access denied"]}
        )

    client = _luci_client(handler)
    luci = LuciRpcClient("http://luci", client=client)
    with pytest.raises(LuciRpcError):
        luci.call("system", "board")
    luci.close()


def test_luci_login_missing_token_raises() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": [0, {}]})

    client = _luci_client(handler)
    with pytest.raises(LuciRpcError):
        LuciRpcClient("http://luci", username="root", password="x", client=client)
    client.close()
