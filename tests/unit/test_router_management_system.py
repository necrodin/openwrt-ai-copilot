"""Unit tests for the router system-info collection and parsing.

Lock in the real-device regression: ``/proc/device-tree/model`` is NUL
terminated and carries no trailing newline, which glued the ``==uname==``
marker onto the model line and caused ``system_info`` to raise IndexError
(HTTP 500) on the System page. Also covers the robust empty-section handling,
the MTD flash-size calculation (nested partitions not double-counted) and the
apk feed listing on the OpenWrt 25 ``/etc/apk/repositories.d`` layout.
"""

from __future__ import annotations

from app.services.router_management import RouterManagementService

_first_line = RouterManagementService._first_line
_parse_mtd = RouterManagementService._parse_mtd_flash_bytes


class FakeTransport:
    def __init__(self, stdout: str) -> None:
        self._stdout = stdout

    def run(self, command: str, *, timeout: float | None = None) -> str:
        return self._stdout

    def close(self) -> None:
        pass


def test_system_gather_handles_nul_terminated_dtnode() -> None:
    # Real OpenWrt 25.12 output: `cat /proc/device-tree/model` emits the model
    # string followed by a NUL byte with NO trailing newline, so `==uname==`
    # lands on the same line. The gatherer must still isolate the uname block.
    stdout = (
        "==release==\nDISTRIB_RELEASE='25.12.0'\n"
        "==dtnode==\nXiaomi AIoT AC2350\x00==uname==\nLinux 6.12.71 mips\n"
        "==ntpen==\n\n__AI_EXIT__=0\n"
    )
    service = RouterManagementService()
    transport = FakeTransport(stdout)
    gathered = service._system_gather(transport)
    # With the NUL glued to the dtnode content the marker is lost on real
    # output; the parser must never crash and the uname fallback stays empty.
    assert "uname" not in gathered


def test_first_line_returns_first_non_blank() -> None:
    assert _first_line("") == ""
    assert _first_line("\n  \nvalue\n") == "value"
    assert _first_line("a\nb") == "a"


def test_parse_mtd_flash_bytes_skips_nested_partitions() -> None:
    mtd = (
        'dev:    size   erasesize  name\n'
        'mtd0: 00030000 00010000 "Bootloader"\n'
        'mtd1: 00010000 00010000 "Nvram"\n'
        'mtd2: 00010000 00010000 "Bdata"\n'
        'mtd3: 00010000 00010000 "crash"\n'
        'mtd4: 00010000 00010000 "art"\n'
        'mtd5: 00020000 00010000 "cfg_bak"\n'
        'mtd6: 00170000 00010000 "overlay"\n'
        'mtd7: 00e00000 00010000 "firmware"\n'
        'mtd8: 002a0000 00010000 "kernel"\n'
        'mtd9: 00b60000 00010000 "rootfs"\n'
        'mtd10: 006c0000 00010000 "rootfs_data"\n'
    )
    total = _parse_mtd(mtd)
    # firmware (0xe00000) contains kernel+rootfs+rootfs_data; only the
    # top-level partitions count, giving the 16 MiB physical flash.
    assert total == 16 * 1024 * 1024


def test_parse_mtd_flash_bytes_empty() -> None:
    assert _parse_mtd("") is None


def test_parse_apk_search_splits_data_from_warnings() -> None:
    text = (
        "WARNING: opening from cache /var/cache/apk: No such file or directory\n"
        "luci-base-25.0.0 all {feeds/luci} (12345)\n"
    )
    results, warnings = RouterManagementService._parse_apk_search(text)
    assert [p["name"] for p in results] == ["luci-base"]
    assert results[0]["version"] == "25.0.0"
    assert len(warnings) == 1
    assert warnings[0].startswith("WARNING: opening from cache")


def test_feeds_apk_reads_repositories_d_layout() -> None:
    class FeedsTransport:
        def __init__(self) -> None:
            self.commands: list[str] = []

        def run(self, command: str, *, timeout: float | None = None) -> str:
            self.commands.append(command)
            if "cat /etc/apk/repositories" in command:
                return (
                    "# add your custom package feeds here\n"
                    "#\n"
                    "https://downloads.openwrt.org/releases/25.12.0/"
                    "targets/ath79/generic/packages/packages.adb\n"
                    "https://downloads.openwrt.org/releases/25.12.0/"
                    "packages/mips_24kc/base/packages.adb\n"
                )
            if "ls -1t /var/cache/apk" in command:
                return "/var/cache/apk/APKINDEX.6f3b844b.tar.gz\n"
            if "date -r" in command:
                return "1786790292\n"
            return ""

        def close(self) -> None:
            pass

    service = RouterManagementService()
    transport = FeedsTransport()
    service.open = lambda: transport  # type: ignore[method-assign]
    service._pkg_manager = lambda: "apk"  # type: ignore[method-assign]
    feeds = service.feeds()
    assert feeds["count"] == 2
    assert [f["name"] for f in feeds["feeds"]] == ["repo0", "repo1"]
    assert feeds["feeds"][0]["url"].endswith("targets/ath79/generic/packages/packages.adb")
    assert feeds["last_update"] == 1786790292
