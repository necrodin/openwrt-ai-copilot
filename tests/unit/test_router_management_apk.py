"""Unit tests for apk-format parsing in the router management service.

The OpenWrt 25 ``apk`` package manager emits different text than the legacy
``opkg``: ``apk list --upgradable`` lines carry the synopsis size, ``apk info
-a`` prints a ``<pkgid> <field>:`` heading-block format, and the installed
world is queryable as a ``KEY:value`` database at ``/lib/apk/db/installed``.
These tests lock in the parsers against captured on-device output.
"""

from __future__ import annotations

from app.services.router_management import RouterManagementService

_parse = RouterManagementService._parse_apk_upgradable
_info = RouterManagementService._parse_apk_info
_db = RouterManagementService._parse_apk_installed_db
_split = RouterManagementService._split_apk_stream
_human = RouterManagementService._parse_apk_human_size


def test_split_apk_stream_buckets_stderr_warnings() -> None:
    text = (
        "WARNING: opening from cache /var/cache/apk: No such file or directory\n"
        "ERROR: something failed\n"
        "libcurl-8.10.1-r0 aarch64 {https://downloads.openwrt.org/releases/packages} (188167)\n"
        "\n"
    )
    data, warnings = _split(text)
    assert data == [
        "libcurl-8.10.1-r0 aarch64 {https://downloads.openwrt.org/releases/packages} (188167)"
    ]
    assert warnings == [
        "WARNING: opening from cache /var/cache/apk: No such file or directory",
        "ERROR: something failed",
    ]


def test_split_apk_stream_ignores_blank_lines() -> None:
    data, warnings = _split("\n  \n\t\nbase-files-258-r0\n")
    assert data == ["base-files-258-r0"]
    assert warnings == []


def test_parse_apk_upgradable_trailing_synopsis_size() -> None:
    text = (
        "base-files-258-r0 mips_24kc {feeds/base/base-files} (16384) [installed]\n"
        "dnsmasq-2.91-r2 mips_24kc {feeds/base/network/services/dnsmasq} "
        "(449806) [upgradable from dnsmasq-2.91-r1]\n"
        "luci-1:25.0.0 all {feeds/luci} (1553) [upgradable]\n"
        "WARNING: opening from cache /var/cache/apk: No such file or directory\n"
    )
    upgrades = _parse(text)
    assert upgrades == {
        "dnsmasq": "2.91-r2",
        "luci": "1:25.0.0",
    }


def test_parse_apk_upgradable_ignores_non_matching_lines() -> None:
    assert _parse("") == {}
    assert _parse("WARNING: only a warning\n") == {}
    assert _parse("not-a-pkgid-line\n") == {}


def test_parse_apk_installed_db_parses_stanzas() -> None:
    text = (
        "P:base-files\n"
        "V:258-r0\n"
        "A:mips_24kc\n"
        "S:27147\n"
        "I:16384\n"
        "T:Base filesystem\n"
        "U:http://git.openwrt.org/\n"
        "L:GPL-2.0\n"
        "o:feeds/base/base-files\n"
        "D:libc\n"
        "\n"
        "P:dnsmasq\n"
        "V:2.91-r2\n"
        "A:mips_24kc\n"
        "S:472860\n"
        "I:449806\n"
        "T:DNS and DHCP server\n"
        "L:GPL-2.0\n"
        "o:feeds/base/network/services/dnsmasq\n"
        "D:libc libubus20251202\n"
    )
    db = _db(text)
    assert set(db) == {"base-files", "dnsmasq"}
    assert db["dnsmasq"]["version"] == "2.91-r2"
    assert db["dnsmasq"]["architecture"] == "mips_24kc"
    assert db["dnsmasq"]["size"] == 472860
    assert db["dnsmasq"]["installed_size"] == 449806
    assert db["dnsmasq"]["license"] == "GPL-2.0"
    assert db["dnsmasq"]["origin"] == "feeds/base/network/services/dnsmasq"
    assert db["dnsmasq"]["depends"] == ["libc", "libubus20251202"]


def test_parse_apk_installed_db_handles_dataset_markers() -> None:
    text = (
        "C:Q1aB2c\n"
        "# Architectures available in the repositories:\n"
        "A:mips_24kc\n"
        "D:so:libc.musl-mips_24kc\n"
        "\n"
        "P:zlib\n"
        "V:1.3.1-r2\n"
        "T:Compression library\n"
        "D:so:libc\n"
    )
    db = _db(text)
    assert set(db) == {"zlib"}
    assert db["zlib"]["version"] == "1.3.1-r2"
    assert db["zlib"]["depends"] == ["so:libc"]


def test_parse_apk_installed_db_skips_leading_metadata_before_first_stanza() -> None:
    db = _db("Q1aB2c\n# comment\nP:curl\nV:8.10.1-r0\n")
    assert set(db) == {"curl"}
    assert db["curl"]["version"] == "8.10.1-r0"


def test_parse_apk_human_size() -> None:
    assert _human("304 KiB") == 304 * 1024
    assert _human("1 MiB") == 1024**2
    assert _human("2 GiB") == 2 * 1024**3
    assert _human("512 B") == 512
    assert _human("") is None
    assert _human("not a size") is None


def test_parse_apk_info_block_format() -> None:
    text = (
        "dnsmasq-2.91-r2 description:\n"
        "It is intended to provide coupled DNS and DHCP service to a LAN.\n"
        "\n"
        "dnsmasq-2.91-r2 depends on:\n"
        "libc\n"
        "libubus20251202\n"
        "\n"
        "dnsmasq-2.91-r2 installed size:\n"
        "304 KiB\n"
        "\n"
        "dnsmasq-2.91-r2 download size:\n"
        "449 KiB\n"
        "\n"
        "dnsmasq-2.91-r2 webpage:\n"
        "http://www.thekelleys.org.uk/dnsmasq/\n"
        "\n"
        "dnsmasq-2.91-r2 license:\n"
        "GPL-2.0\n"
        "WARNING: opening from cache /var/cache/apk: No such file or directory\n"
    )
    info = _info(text, "dnsmasq")
    assert info["version"] == "2.91-r2"
    assert info["description"] == "It is intended to provide coupled DNS and DHCP service to a LAN."
    assert info["depends"] == ["libc", "libubus20251202"]
    assert info["installed_size"] == 304 * 1024
    assert info["download_size"] == 449 * 1024
    assert info["homepage"] == "http://www.thekelleys.org.uk/dnsmasq/"
    assert info["license"] == "GPL-2.0"


def test_parse_apk_info_filters_virtual_dependencies() -> None:
    text = (
        "libc-1.2.7-r2 description:\n"
        "C library\n"
        "\n"
        "libc-1.2.7-r2 depends on:\n"
        "so:libc.musl-mips_24kc\n"
        "\n"
        "libc-1.2.7-r2 provides:\n"
        "so:libc.musl-mips_24kc\n"
    )
    info = _info(text, "libc")
    assert info["version"] == "1.2.7-r2"
    assert info["depends"] == []


def test_parse_apk_info_unknown_package_matches_no_heading() -> None:
    info = _info("base-files-258-r0 description:\nBase\n", "curl")
    assert info["version"] == ""
    assert info["description"] == "Base"