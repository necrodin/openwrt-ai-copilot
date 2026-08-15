"""Unit tests for the package repository search failure classes.

``search_packages`` must distinguish a genuine no-match from the distinct
failure modes: no supported package manager, an empty/never-updated repository
index, and unreadable repository metadata. Raw diagnostics are kept (truncated)
under ``detail`` so the UI never has to render a wall of stderr.

On apk, a missing index cache is recovered automatically: the search refreshes
the feeds once (``apk update``) and retries, so a search on a fresh router
works without the operator first clicking "Update feeds".
"""

from __future__ import annotations

from app.services.router_management import RouterManagementService


class FakeResult:
    def __init__(self, stdout: str, ok: bool = True) -> None:
        self.stdout = stdout
        self.ok = ok
        self.exit_code = 0 if ok else 1
        self.duration_ms = 1


class ScriptedRun:
    """Returns canned output keyed by command prefix."""

    def __init__(self, responses: dict[str, FakeResult]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, command: str, **_: object) -> FakeResult:
        self.calls.append(command)
        for prefix, result in self.responses.items():
            if command.startswith(prefix):
                return result
        return FakeResult("")


def _service() -> RouterManagementService:
    return RouterManagementService()


def test_search_apk_empty_cache_update_fails_is_index_unavailable() -> None:
    warnings = "WARNING: opening from cache /var/cache/apk: No such file or directory"
    runner = ScriptedRun(
        {
            "apk search": FakeResult(warnings + "\n"),
            "apk update": FakeResult("", ok=False),
        }
    )
    service = _service()
    service._pkg_manager = lambda: "apk"  # type: ignore[method-assign]
    service._pkg_run = runner  # type: ignore[method-assign]
    result = service.search_packages("luci")
    assert result["results"] == []
    assert result["repository"]["status"] == "index-unavailable"
    assert result["repository"]["available"] is False
    assert "Update feeds" in result["repository"]["reason"]
    assert result["repository"]["detail"] == [warnings]
    # the auto-refresh attempt happened exactly once
    assert sum(1 for c in runner.calls if c.startswith("apk update")) == 1


def test_search_apk_empty_cache_auto_refresh_recovers() -> None:
    warnings = "WARNING: opening from cache /var/cache/apk: No such file or directory"
    found = "luci-base-25.0.0 all {feeds/luci} (12345)\n"
    runner = ScriptedRun(
        {
            "apk search": FakeResult(warnings + "\n"),
            "apk update": FakeResult("OK: 11163 distinct packages available"),
        }
    )
    # After a successful update the retried search must return real results.
    original_parse = RouterManagementService._parse_apk_search
    calls = {"n": 0}

    def patched_parse(text: str):
        if calls["n"] == 0:
            calls["n"] += 1
            return original_parse(text)  # first call: warnings only
        return original_parse(found)  # retry: real match

    service = _service()
    service._pkg_manager = lambda: "apk"  # type: ignore[method-assign]
    service._pkg_run = runner  # type: ignore[method-assign]
    RouterManagementService._parse_apk_search = staticmethod(patched_parse)
    try:
        result = service.search_packages("luci")
    finally:
        RouterManagementService._parse_apk_search = staticmethod(original_parse)
    assert result["repository"]["status"] == "ok"
    assert result["repository"]["available"] is True
    assert result["count"] == 1
    assert result["results"][0]["name"] == "luci-base"
    assert sum(1 for c in runner.calls if c.startswith("apk update")) == 1


def test_search_apk_cache_present_returns_matches() -> None:
    runner = ScriptedRun(
        {
            "apk search": FakeResult(
                "luci-app-firewall-1.25.0 all {feeds/luci} (2341)\n"
                "luci-base-25.0.0 all {feeds/luci} (12345)\n"
            ),
        }
    )
    service = _service()
    service._pkg_manager = lambda: "apk"  # type: ignore[method-assign]
    service._pkg_run = runner  # type: ignore[method-assign]
    result = service.search_packages("luci")
    assert result["repository"]["status"] == "ok"
    assert result["repository"]["available"] is True
    assert result["count"] == 2
    assert result["results"][0]["name"] == "luci-app-firewall"
    assert result["results"][1]["name"] == "luci-base"
    assert not any(c.startswith("apk update") for c in runner.calls)


def test_search_opkg_empty_index_is_repository_unavailable() -> None:
    service = _service()
    service._pkg_manager = lambda: "opkg"  # type: ignore[method-assign]
    service._pkg_run = lambda _cmd, **_: FakeResult("")  # type: ignore[method-assign]
    result = service.search_packages("luci")
    assert result["results"] == []
    assert result["repository"]["status"] == "repository-unavailable"
    assert result["repository"]["available"] is False
    assert "Update feeds" in result["repository"]["reason"]


def test_search_opkg_no_match_with_index_is_ok() -> None:
    service = _service()
    service._pkg_manager = lambda: "opkg"  # type: ignore[method-assign]
    service._pkg_run = lambda _cmd, **_: FakeResult(  # type: ignore[method-assign]
        "dropbear - 2024.86-2 - Dropbear SSH server\n"
        "dnsmasq - 2.90-1 - DNS and DHCP server\n"
    )
    result = service.search_packages("zzz-nothing")
    assert result["results"] == []
    assert result["repository"]["status"] == "ok"
    assert result["repository"]["available"] is True


def test_search_unknown_manager_is_manager_unavailable() -> None:
    service = _service()
    service._pkg_manager = lambda: "unknown"  # type: ignore[method-assign]
    result = service.search_packages("luci")
    assert result["results"] == []
    assert result["repository"]["status"] == "manager-unavailable"
    assert result["repository"]["available"] is False
    assert "package manager" in result["repository"]["reason"]


def test_search_requires_a_query() -> None:
    service = _service()
    try:
        service.search_packages("   ")
    except Exception as exc:  # noqa: BLE001 - assert the raised error type below
        assert exc.__class__.__name__ == "RouterManagementError"
        return
    raise AssertionError("expected RouterManagementError for a blank query")
