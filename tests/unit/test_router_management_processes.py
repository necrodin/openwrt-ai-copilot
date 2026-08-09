"""Process collection robustness tests for the management service.

These exercise the raw ``/proc`` sampler parsing so malformed or short lines can
never crash the collector. A minimal fake transport stands in for SSH.
"""

from __future__ import annotations

from app.services.router_management import RouterManagementService


class FakeTransport:
    """CommandRunner stand-in that always returns the same output."""

    def __init__(self, output: str) -> None:
        self.output = output

    def run(self, command: str, *, timeout: float | None = None) -> str:
        return self.output

    def close(self) -> None:
        pass


def _collect(stdout: str):
    service = RouterManagementService()
    return service._collect_process_rows(FakeTransport(stdout))


# A syntactically valid /proc/<pid>/stat fragment: 22+ columns after the comm,
# so utime/stime/vsize/rss all index in range.
_VALID_STAT = "1234 (bash) S 0 0 0 0 -1 4194560 500 0 0 0 100 200 0 0 20 0 1 0 0 1000000 250"


def test_process_valid_row() -> None:
    lines = [
        "__AI_CPU_TOTAL__ 512345",
        "__AI_MEM_TOTAL_KB__ 38416",
        f"0|__AI_UIDSEP__|{_VALID_STAT}|__AI_CMDSEP__|/bin/bash -c echo hi",
    ]
    cpu, mem, rows = _collect("\n".join(lines) + "\n")
    assert cpu == 512345
    assert mem == 38416
    assert set(rows) == {"1234"}
    assert rows["1234"]["utime"] == 100
    assert rows["1234"]["stime"] == 200
    assert rows["1234"]["vsz"] == 1000000
    assert rows["1234"]["rss_pages"] == 250
    assert rows["1234"]["user"] == "root"
    assert rows["1234"]["cmd"] == "/bin/bash -c echo hi"


def test_process_rows_tolerates_missing_header_values() -> None:
    lines = (
        "__AI_CPU_TOTAL__",
        "__AI_MEM_TOTAL_KB__",
        f"1000|__AI_UIDSEP__|{_VALID_STAT}|__AI_CMDSEP__|cmd",
    )
    cpu, mem, rows = _collect("\n".join(lines) + "\n")
    assert cpu == 0
    assert mem == 0
    assert "1234" in rows  # keyed by pid from the stat line, not the uid column
    assert rows["1234"]["user"] == "www"  # uid 1000 mapped


def test_process_rows_tolerates_empty_header_column() -> None:
    # Regression: a trailing marker with no value used to raise IndexError.
    stdout = "__AI_MEM_TOTAL_KB__ \n"
    cpu, mem, rows = _collect(stdout)
    assert mem == 0
    assert rows == {}


def test_process_rows_skips_short_stat_lines() -> None:
    lines = (
        "__AI_CPU_TOTAL__ 100",
        "__AI_MEM_TOTAL_KB__ 200",
        "0|__AI_UIDSEP__|1 (x) S 0 0 0 0 -1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0|__AI_CMDSEP__|short",
        "0|__AI_UIDSEP__|30 (y)|__AI_CMDSEP__|no uid",
        f"0|__AI_UIDSEP__|{_VALID_STAT}|__AI_CMDSEP__|ok",
    )
    cpu, mem, rows = _collect("\n".join(lines) + "\n")
    assert set(rows) == {"1234"}  # only the valid row survives


def test_process_rows_skips_malformed_markers() -> None:
    lines = (
        "garbage line without any marker",
        "0|__AI_CMDSEP__|missing uid separator",
        "__AI_CPU_TOTAL__ abc",
    )
    cpu, mem, rows = _collect("\n".join(lines) + "\n")
    assert cpu == 0
    assert rows == {}


def test_process_rows_mixed_valid_and_malformed() -> None:
    lines = (
        "__AI_CPU_TOTAL__ 999",
        "__AI_MEM_TOTAL_KB__ 38416",
        f"0|__AI_UIDSEP__|{_VALID_STAT}|__AI_CMDSEP__|good",
        "0||__AI_CMDSEP__|no stat",
        "not-a-row",
    )
    cpu, mem, rows = _collect("\n".join(lines) + "\n")
    assert cpu == 999
    assert set(rows) == {"1234"}
    assert rows["1234"]["cmd"] == "good"


def test_process_rows_empty_output() -> None:
    cpu, mem, rows = _collect("")
    assert cpu == 0
    assert mem == 0
    assert rows == {}