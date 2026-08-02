"""Metadata filter evaluation shared by every backend.

A filter is a list of :class:`MetadataFilter` leaf clauses combined with AND.
The matcher works on plain dicts so HTTP backends can reuse it to validate
filters (and, where the backend lacks native filtering, to post-filter).
"""

from __future__ import annotations

from typing import Any

from vectorstore.errors import InvalidMetadataFilterError
from vectorstore.models import MetadataFilter

_OPERATORS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains"})


def validate_filters(filters: list[MetadataFilter]) -> None:
    """Raise :class:`InvalidMetadataFilterError` for unsupported clauses."""
    for clause in filters:
        if clause.op not in _OPERATORS:
            raise InvalidMetadataFilterError(f"Unsupported metadata filter operator {clause.op!r}")


def _matches_clause(metadata: dict[str, Any], clause: MetadataFilter) -> bool:
    value = metadata.get(clause.field)
    op = clause.op
    expected = clause.value

    if op == "eq":
        return value == expected
    if op == "ne":
        return value != expected
    if op == "gt":
        return isinstance(value, (int, float)) and value > expected
    if op == "gte":
        return isinstance(value, (int, float)) and value >= expected
    if op == "lt":
        return isinstance(value, (int, float)) and value < expected
    if op == "lte":
        return isinstance(value, (int, float)) and value <= expected
    if op == "in":
        return isinstance(expected, (list, tuple, set)) and value in expected
    if op == "not_in":
        return isinstance(expected, (list, tuple, set)) and value not in expected
    if op == "contains":
        return isinstance(value, str) and isinstance(expected, str) and expected in value
    raise InvalidMetadataFilterError(f"Unsupported metadata filter operator {op!r}")


def matches(metadata: dict[str, Any], filters: list[MetadataFilter]) -> bool:
    """Return True when every filter clause matches ``metadata``."""
    if not filters:
        return True
    return all(_matches_clause(metadata, clause) for clause in filters)


__all__ = ["matches", "validate_filters"]
