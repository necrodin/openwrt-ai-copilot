"""Vector math helpers shared by in-process backends.

Pure Python (no numpy) so the SQLite reference backend has zero dependencies.
"""

from __future__ import annotations


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity in [-1, 1]; 0.0 for empty/zero vectors."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right, strict=True):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / ((left_norm * right_norm) ** 0.5)


__all__ = ["cosine_similarity"]
