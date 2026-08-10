"""Shell-injection regression tests for the router management service.

Every user-supplied string that ends up in an SSH command must be either
allow-listed by a strict regex or shell-quoted (``_sh_quote`` /
``_shell_single``). The regression that surfaced here is
:meth:`RouterManagementService.system_set_config`: ``language`` and ``notes``
were interpolated into ``uci set`` commands verbatim, so a crafted value such as
``x'; touch /tmp/pwn; '`` executed arbitrary shell on the router.

These tests keep that surface locked down: metacharacters are rejected or
confined to a single-quoted argument, and the other guard sites (packages,
services, DHCP, DNS, network, firewall) stay rejected.
"""

from __future__ import annotations

import pytest

from app.services.router_management import RouterManagementError, RouterManagementService


class CapturingTransport:
    """Records every command sent and answers a clean zero exit."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    def run(self, command: str, *, timeout: float | None = None) -> str:
        self.commands.append(command)
        return "\n__AI_EXIT__=0"

    def close(self) -> None:
        pass


def _capture_service() -> tuple[RouterManagementService, CapturingTransport]:
    service = RouterManagementService()
    transport = CapturingTransport()
    service.open = lambda: transport  # type: ignore[method-assign]
    return service, transport


def _live(text: str) -> str:
    """Return the characters the shell actually executes in ``text``.

    Single quotes group everything between them as a literal argument, so only
    characters outside ``'...'`` spans (plus ``\\x`` escapes) are live. The
    ``'\\''`` idiom closes and reopens the span around an embedded apostrophe,
    which this scanner mirrors: a backslash outside quotes escapes the next
    character into the live token without toggling quote state.
    """
    out: list[str] = []
    in_single = False
    index = 0
    while index < len(text):
        ch = text[index]
        if in_single:
            if ch == "'":
                in_single = False
            index += 1
            continue
        if ch == "\\":
            if index + 1 < len(text):
                out.append(text[index + 1])
            index += 2
            continue
        if ch == "'":
            in_single = True
            index += 1
            continue
        out.append(ch)
        index += 1
    return "".join(out)


# -- system_set_config ------------------------------------------------------ #


def test_system_language_rejects_shell_metacharacters() -> None:
    service, _ = _capture_service()
    for malicious in ("en;reboot", "en$(id)", "en`reboot`", "en'", "en&reboot"):
        with pytest.raises(RouterManagementError):
            service.system_set_config(
                hostname=None, timezone=None, language=malicious, notes=None
            )


def test_system_hostname_and_timezone_still_validated() -> None:
    service, _ = _capture_service()
    for field, malicious in (
        ("hostname", "gw;reboot"),
        ("hostname", "gw$(id)"),
        ("timezone", "UTC;reboot"),
        ("timezone", "UTC`reboot`"),
    ):
        kwargs = {"hostname": None, "timezone": None, "language": None, "notes": None}
        kwargs[field] = malicious
        with pytest.raises(RouterManagementError):
            service.system_set_config(**kwargs)


def test_system_valid_values_are_emitted_quoted() -> None:
    service, transport = _capture_service()
    result = service.system_set_config(
        hostname="gw", timezone="Europe/Berlin", language="en", notes="lab router"
    )
    assert result["ok"] is True
    script = transport.commands[0]
    assert "uci set system.@system[0].hostname='gw'" in script
    assert "uci set system.@system[0].timezone='Europe/Berlin'" in script
    assert "uci set system.@system[0].language='en'" in script
    assert "uci set system.@system[0].notes='lab router'" in script
    assert "uci commit system" in script
    assert "/etc/init.d/sysntpd restart" in script


def test_system_notes_injection_is_confined_to_a_single_argument() -> None:
    service, transport = _capture_service()
    payload = "x'; touch /tmp/pwn; $(echo pwn2); `id`; &"
    result = service.system_set_config(
        hostname=None, timezone=None, language=None, notes=payload
    )
    assert result["ok"] is True
    script = transport.commands[0]
    # Every embedded quote is present in its escaped '\'' form.
    assert script.count("'\\''") >= payload.count("'")
    # Nothing from the payload can run on the shell: ';', '$(' and the
    # backticks all stay inside a single-quoted span.
    live = _live(script)
    assert "touch" not in live
    assert "pwn" not in live
    assert "pwn2" not in live
    assert "id" not in live
    assert "$(" not in live
    assert "`" not in live


def test_sh_quote_roundtrip_leaves_no_breakout() -> None:
    quoted = RouterManagementService._sh_quote("x'; touch /tmp/pwn; '")
    assert quoted == "'x'\\''; touch /tmp/pwn; '\\'''"
    live = _live(quoted)
    assert "touch" not in live
    assert ";" not in live
    assert "$" not in live


# -- storage --------------------------------------------------------------- #


def test_storage_target_is_shell_quoted() -> None:
    service, transport = _capture_service()
    job = service.job_store.create("storage", message="Queued")
    out = service.run_storage_job(
        job.id, action="unmount", target="/dev/sda1; touch /tmp/pwn"
    )
    assert out.status == "succeeded"
    script = transport.commands[0]
    assert "'/dev/sda1; touch /tmp/pwn'" in script
    assert "touch" not in _live(script)


# -- guards that reject before any command runs ----------------------------- #


def test_package_mutations_reject_injected_name() -> None:
    service = RouterManagementService()
    for mutate in (
        service.package_install,
        service.package_remove,
        service.package_upgrade,
        service.package_reinstall,
    ):
        with pytest.raises(RouterManagementError):
            mutate("curl; reboot")


def test_service_action_rejects_injected_name() -> None:
    service = RouterManagementService()
    job = service.job_store.create("services", message="Queued")
    out = service.run_services_job(job.id, action="start", service="dropbear; reboot")
    assert out.status == "failed"
    assert "Invalid service name" in (out.error or "")


def test_dhcp_host_add_rejects_injected_values() -> None:
    service = RouterManagementService()
    with pytest.raises(RouterManagementError):
        service.dhcp_add_host(
            hostname="gw; reboot", ip="10.0.0.5", mac="aa:bb:cc:dd:ee:ff"
        )
    with pytest.raises(RouterManagementError):
        service.dhcp_add_host(
            hostname="gw", ip="10.0.0.5$(reboot)", mac="aa:bb:cc:dd:ee:ff"
        )
    with pytest.raises(RouterManagementError):
        service.dhcp_add_host(
            hostname="gw", ip="10.0.0.5", mac="aa:bb:cc:dd:ee:ff; reboot"
        )


def test_dhcp_host_values_are_single_quoted() -> None:
    service, transport = _capture_service()
    service.dhcp_add_host(hostname="gw", ip="10.0.0.5", mac="aa:bb:cc:dd:ee:ff")
    script = transport.commands[0]
    assert "uci set dhcp.$sid.name='gw'" in script
    assert "uci set dhcp.$sid.ip='10.0.0.5'" in script
    assert "uci set dhcp.$sid.mac='aa:bb:cc:dd:ee:ff'" in script
    assert "reboot" not in _live(script)


def test_dns_server_rejects_injected_value() -> None:
    service = RouterManagementService()
    with pytest.raises(RouterManagementError):
        service.dns_add_server(server="8.8.8.8; rm -rf /")
    with pytest.raises(RouterManagementError):
        service.dns_remove_server(server="8.8.8.8`reboot`")


def test_network_interface_rejects_injected_name() -> None:
    service = RouterManagementService()
    for func in (
        service.net_interface_restart,
        service.net_interface_renew,
        service.net_interface_release,
    ):
        with pytest.raises(RouterManagementError):
            func(section="wan; reboot")
    with pytest.raises(RouterManagementError):
        service.net_interface_set_enabled(section="wan; reboot", enabled=True)


def test_firewall_section_rejects_injected_identifier() -> None:
    service = RouterManagementService()
    with pytest.raises(RouterManagementError):
        service.toggle_firewall_rule(section="cfg040f11; reboot", enabled=True)
    with pytest.raises(RouterManagementError):
        service.toggle_wireless_ssid(section="wlan0; reboot", enabled=True)
    with pytest.raises(RouterManagementError):
        service.toggle_vpn_instance(section="home; reboot", enabled=True)