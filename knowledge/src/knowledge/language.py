"""Pure-Python language detection.

No external libraries. Detection is a two-step heuristic:

1. **Script detection** — Unicode block ranges classify the dominant script
   (Latin, Cyrillic, Arabic, CJK, Greek, Hebrew, Devanagari, …).
2. **Stop-word scoring** — for Latin/Cyrillic scripts, the text is tokenized
   and scored against a small per-language stop-word list. The language with
   the most stop-word hits wins; ties resolve by total hit counts.

Returns ISO 639-1 codes (``"en"``, ``"de"``, ``"ru"``, …). Short or
uninformative inputs return ``"unknown"``.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ]+")


def _script(text: str) -> str:
    counts: dict[str, int] = {}
    for char in text:
        codepoint = ord(char)
        if 0x0041 <= codepoint <= 0x024F:
            counts["latin"] = counts.get("latin", 0) + 1
        elif 0x0400 <= codepoint <= 0x052F:
            counts["cyrillic"] = counts.get("cyrillic", 0) + 1
        elif 0x0600 <= codepoint <= 0x06FF:
            counts["arabic"] = counts.get("arabic", 0) + 1
        elif (
            0x4E00 <= codepoint <= 0x9FFF
            or 0x3040 <= codepoint <= 0x30FF
            or 0xAC00 <= codepoint <= 0xD7AF
        ):
            counts["cjk"] = counts.get("cjk", 0) + 1
        elif 0x0370 <= codepoint <= 0x03FF:
            counts["greek"] = counts.get("greek", 0) + 1
        elif 0x0590 <= codepoint <= 0x05FF:
            counts["hebrew"] = counts.get("hebrew", 0) + 1
        elif 0x0900 <= codepoint <= 0x097F:
            counts["devanagari"] = counts.get("devanagari", 0) + 1
    if not counts:
        return "unknown"
    return max(counts, key=counts.get)


#: ISO 639-1 → stop words. Order matters: earlier entries are preferred on ties.
_STOP_WORDS: dict[str, set[str]] = {
    "en": {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "are",
        "not",
        "you",
        "all",
        "will",
        "your",
        "can",
        "have",
        "has",
        "was",
        "were",
        "which",
        "when",
        "where",
        "what",
        "about",
        "into",
        "their",
        "there",
        "these",
        "those",
        "would",
        "should",
        "could",
        "is",
        "of",
        "to",
        "as",
        "at",
        "be",
        "by",
        "on",
        "it",
        "or",
        "an",
    },
    "de": {
        "der",
        "die",
        "das",
        "und",
        "ist",
        "sind",
        "nicht",
        "mit",
        "für",
        "auf",
        "eine",
        "ein",
        "den",
        "dem",
        "des",
        "von",
        "zur",
        "zum",
        "als",
        "auch",
        "sich",
        "bei",
        "nach",
        "über",
        "wenn",
        "wie",
        "im",
        "in",
    },
    "fr": {
        "le",
        "la",
        "les",
        "et",
        "est",
        "sont",
        "pas",
        "une",
        "un",
        "des",
        "pour",
        "avec",
        "dans",
        "qui",
        "que",
        "sur",
        "ce",
        "cette",
        "ses",
        "leur",
        "plus",
        "tout",
        "au",
        "aux",
        "du",
    },
    "es": {
        "el",
        "la",
        "los",
        "las",
        "es",
        "son",
        "no",
        "una",
        "un",
        "para",
        "con",
        "en",
        "que",
        "por",
        "este",
        "esta",
        "estos",
        "como",
        "más",
        "del",
        "al",
        "su",
        "sus",
        "de",
        "se",
    },
    "it": {
        "il",
        "lo",
        "la",
        "le",
        "gli",
        "i",
        "è",
        "sono",
        "non",
        "una",
        "un",
        "per",
        "con",
        "in",
        "che",
        "come",
        "più",
        "del",
        "della",
        "delle",
        "degli",
        "dei",
        "su",
        "suo",
        "sua",
        "e",
        "di",
    },
    "pt": {
        "o",
        "os",
        "a",
        "as",
        "e",
        "é",
        "são",
        "não",
        "uma",
        "um",
        "para",
        "com",
        "em",
        "que",
        "como",
        "mais",
        "do",
        "da",
        "dos",
        "das",
        "de",
        "se",
        "por",
        "esta",
        "este",
    },
    "nl": {
        "de",
        "het",
        "een",
        "en",
        "is",
        "zijn",
        "niet",
        "met",
        "voor",
        "op",
        "aan",
        "dat",
        "die",
        "van",
        "als",
        "ook",
        "bij",
        "naar",
        "over",
        "wordt",
        "kan",
        "heeft",
    },
    "ru": {
        "и",
        "в",
        "не",
        "на",
        "что",
        "это",
        "с",
        "по",
        "как",
        "для",
        "при",
        "от",
        "к",
        "о",
        "он",
        "она",
        "они",
        "мы",
        "вы",
        "из",
        "у",
        "же",
        "бы",
        "так",
        "все",
    },
    "sv": {
        "och",
        "att",
        "är",
        "som",
        "för",
        "med",
        "det",
        "den",
        "en",
        "ett",
        "inte",
        "på",
        "av",
        "till",
        "har",
        "de",
        "om",
        "kan",
        "vid",
    },
    "pl": {
        "i",
        "w",
        "na",
        "nie",
        "że",
        "się",
        "to",
        "jest",
        "do",
        "z",
        "o",
        "za",
        "po",
        "od",
        "jak",
        "co",
        "ale",
        "przez",
        "dla",
    },
}

_SCRIPT_TO_LANGUAGE: dict[str, str] = {
    "arabic": "ar",
    "cjk": "zh",
    "greek": "el",
    "hebrew": "he",
    "devanagari": "hi",
    "cyrillic": "ru",
}


def detect_language(text: str) -> str:
    """Return the ISO 639-1 language code for ``text`` (``"unknown"`` if unsure)."""
    sample = text[:4000]
    script = _script(sample)
    if script == "unknown":
        return "unknown"
    if script == "latin":
        return _detect_latin(sample)
    if script == "cyrillic":
        return _detect_cyrillic(sample)
    return _SCRIPT_TO_LANGUAGE[script]


def _detect_latin(text: str) -> str:
    tokens = [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1]
    if not tokens:
        return "unknown"
    best_language: str | None = None
    best_score = -1
    for language, stop_words in _STOP_WORDS.items():
        if language in ("ru", "pl"):
            continue
        score = sum(1 for token in tokens if token in stop_words)
        if score > best_score:
            best_score = score
            best_language = language
    if best_language is None or best_score < 2:
        return "unknown"
    return best_language


def _detect_cyrillic(text: str) -> str:
    tokens = [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1]
    if not tokens:
        return "unknown"
    ru = _STOP_WORDS["ru"]
    score = sum(1 for token in tokens if token in ru)
    if score >= 1:
        return "ru"
    return "unknown"


__all__ = ["detect_language"]
