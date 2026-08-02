"""Language detection tests for the knowledge platform."""

from __future__ import annotations

import pytest

from knowledge.language import detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The quick brown fox jumps over the lazy dog", "en"),
        ("OpenWrt is a Linux distribution for routers and networks", "en"),
        ("OpenWrt est une distribution pour les routeurs et le reseau", "fr"),
        ("Der Router ist nicht konfiguriert und startet neu", "de"),
        ("El router esta configurado para la red local", "es"),
        ("OpenWrt e uma distribuicao para roteadores de rede", "pt"),
        ("Het systeem is niet geconfigureerd en wordt opnieuw gestart", "nl"),
        ("Il router non e configurato e si riavvia da solo", "it"),
        ("Привет мир, это мой маршрутизатор и сеть", "ru"),
        ("这是一个基于 Linux 的路由器操作系统，支持各种功能", "zh"),
        ("هذا هو نظام التشغيل المثبت على الجهاز", "ar"),
        ("Γεια σας, αυτός είναι ο δρομολογητής", "el"),
    ],
)
def test_detect_language_common(text: str, expected: str) -> None:
    assert detect_language(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "12345 !!!",
        "OpenWrt",
        "xyz qwerty asdfgh zxcvb",
    ],
)
def test_detect_language_unknown(text: str) -> None:
    assert detect_language(text) == "unknown"


def test_detect_language_ignores_markup() -> None:
    assert detect_language("<b>The</b> router and the network are configured") == "en"


def test_detect_language_deterministic() -> None:
    text = "The router is configured with the firewall"
    assert detect_language(text) == detect_language(text)
