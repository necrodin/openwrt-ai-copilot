"""System log collector.

Source: ``logread -l <n>`` (logd). Parses the common OpenWrt log line format
leniently; the raw line is always preserved.
"""

from __future__ import annotations

import re

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import LogEntry, LogInfo

# e.g. "Mon Aug  1 23:04:41 2026 daemon.info hostapd[1234]: message"
_HEADER = re.compile(
    r"^(?P<date>[A-Z][a-z]{2} [A-Z][a-z]{2} {1,2}\d{1,2} \d{2}:\d{2}:\d{2} \d{4})"
    r" (?P<facility>\w+)\.(?P<priority>\w+) "
    r"(?P<ident>[^:]+): (?P<message>.*)$"
)
# e.g. "2026-08-01 23:04:41 daemon.info hostapd[1234]: message"
_ISO = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
    r" (?P<facility>\w+)\.(?P<priority>\w+) "
    r"(?P<ident>[^:]+): (?P<message>.*)$"
)


def _parse_line(line: str) -> LogEntry:
    entry = LogEntry(raw=line)
    match = _HEADER.match(line) or _ISO.match(line)
    if match:
        entry.timestamp = match.group("date")
        entry.facility = match.group("facility")
        entry.priority = match.group("priority")
        entry.ident = match.group("ident")
        entry.message = match.group("message")
    else:
        entry.message = line
    return entry


def parse_logread(text: str) -> list[LogEntry]:
    return [_parse_line(line) for line in text.splitlines() if line.strip()]


class LogsCollector(Collector):
    name = "logs"

    def collect(self, ctx: CollectorContext) -> LogInfo:
        lines = ctx.config.log_lines
        output = ctx.sh(f"logread -l {lines}", default="")
        return LogInfo(entries=parse_logread(output))
