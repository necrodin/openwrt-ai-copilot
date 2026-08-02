"""Normalization and checksum tests for the knowledge platform."""

from __future__ import annotations

from knowledge.checksum import chunk_checksum, document_checksum, sha256_hex
from knowledge.normalization import canonical_text, normalize_text


def test_normalize_collapses_whitespace() -> None:
    assert normalize_text("OpenWrt  is   a\nlinux distro.") == "OpenWrt is a\nlinux distro."


def test_normalize_unifies_newlines() -> None:
    assert normalize_text("a\r\nb\rc\nd") == "a\nb\nc\nd"


def test_normalize_strips_control_chars() -> None:
    assert normalize_text("a\x00b\x1f c") == "ab c"


def test_normalize_nfc() -> None:
    composed = "\u00e9"  # é as a single codepoint
    decomposed = "e\u0301"  # e + combining acute
    assert normalize_text(decomposed) == composed


def test_normalize_preserves_paragraph_breaks() -> None:
    assert normalize_text("one\n\n\n\ntwo") == "one\n\ntwo"
    assert normalize_text("one\n\ntwo") == "one\n\ntwo"


def test_normalize_trims_leading_trailing_blank_lines() -> None:
    assert normalize_text("\n\nhello\n\n\n") == "hello"


def test_canonical_text_lowercases_and_strips_punctuation() -> None:
    assert canonical_text("OpenWrt, a Linux distro!") == "openwrt a linux distro"


def test_canonical_text_is_whitespace_insensitive() -> None:
    a = canonical_text("The   router\n\nis configured.")
    b = canonical_text("the router is configured.")
    assert a == b


def test_document_checksum_is_formatting_insensitive() -> None:
    assert document_checksum("Firewall Rules\n\nSetup") == document_checksum("firewall rules setup")


def test_document_checksum_differs_by_content() -> None:
    assert document_checksum("firewall rules") != document_checksum("firewall rules v2")


def test_chunk_checksum_over_raw_text() -> None:
    assert chunk_checksum(" hello ") == chunk_checksum("hello")
    assert chunk_checksum("hello") != chunk_checksum("hello world")


def test_sha256_hex_length_and_hex() -> None:
    digest = sha256_hex("openwrt")
    assert len(digest) == 64
    int(digest, 16)  # must be valid hex
    assert sha256_hex("openwrt") == sha256_hex("openwrt")
    assert sha256_hex("openwrt") != sha256_hex("openwrt!")
