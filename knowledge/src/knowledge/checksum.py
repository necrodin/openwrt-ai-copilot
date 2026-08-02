"""Checksum helpers for the knowledge platform.

A document's checksum is a stable digest of its **normalized** text (see
:mod:`knowledge.normalization`), so equivalent content with different
whitespace produces the same digest — this is what powers change detection
(incremental indexing) and duplicate detection.
"""

from __future__ import annotations

import hashlib


def sha256_hex(text: str) -> str:
    """Return the lowercase hex sha256 digest of ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def document_checksum(text: str) -> str:
    """Digest used for document versioning/duplicates.

    Computed over the whitespace-collapsed, case-normalized text so that pure
    formatting differences never count as a content change.
    """
    from knowledge.normalization import canonical_text

    return sha256_hex(canonical_text(text))


def chunk_checksum(text: str) -> str:
    """Digest used for a single chunk (over the raw chunk text)."""
    return sha256_hex(text.strip())


__all__ = ["chunk_checksum", "document_checksum", "sha256_hex"]
