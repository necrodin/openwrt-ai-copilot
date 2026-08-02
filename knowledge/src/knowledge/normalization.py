"""Text normalization for the knowledge platform.

Normalization makes documents comparable: Unicode is folded to NFC, control
characters and stray markup are removed, whitespace is collapsed, and
newlines are unified. :func:`canonical_text` additionally lowercases and
strips punctuation — it is used exclusively for checksums / duplicate
detection, never for display.
"""

from __future__ import annotations

import re
import unicodedata

#: Control characters (C0/C1) minus tab/newline/carriage-return.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
#: Runs of whitespace (including newlines) → single space.
_WHITESPACE_RUNS = re.compile(r"[ \t\f\v]+")
#: Line boundaries → "\n".
_LINE_BOUNDARY = re.compile(r"\r\n|\r|\n")
#: Anything that is not a letter, digit, or space (for canonical form).
_NON_ALNUM = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_text(text: str) -> str:
    """Return a normalized version of ``text``.

    - Unicode NFC
    - strip control characters (keeps ``\\n``)
    - collapse intra-line whitespace runs to single spaces
    - trim trailing/leading whitespace per line
    - preserve paragraph structure as single blank lines between paragraphs

    Paragraph breaks are kept so paragraph-aware chunkers can find them; the
    checksum path (:func:`canonical_text`) collapses them away.
    """
    normalized = unicodedata.normalize("NFC", text)
    normalized = _CONTROL_CHARS.sub("", normalized)
    normalized = _LINE_BOUNDARY.sub("\n", normalized)
    lines: list[str] = []
    for raw_line in normalized.split("\n"):
        line = _WHITESPACE_RUNS.sub(" ", raw_line.strip())
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
        else:
            lines.append(line)
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def canonical_text(text: str) -> str:
    """Return a canonical form for comparison.

    Normalizes, lowercases, removes punctuation, and collapses everything to a
    single line. Two documents with the same content (modulo formatting) yield
    the same canonical form.
    """
    normalized = normalize_text(text)
    normalized = normalized.lower()
    normalized = _NON_ALNUM.sub("", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


__all__ = ["canonical_text", "normalize_text"]
