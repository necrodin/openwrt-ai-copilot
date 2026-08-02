"""Parser tests for the knowledge platform (one test per format)."""

from __future__ import annotations

import pytest

from knowledge.errors import KnowledgeParseError
from knowledge.parsers import (
    HtmlParser,
    JsonParser,
    MarkdownParser,
    PdfParser,
    TextParser,
    XmlParser,
    YamlParser,
)


def test_markdown_headings_and_front_matter() -> None:
    raw = b"""---
title: My Guide
author: Talat
---
# Intro

Some **bold** and a [link](https://example.com).

## Details

More *text*.
"""
    doc = MarkdownParser().parse(raw, reference="guide.md", source="wiki")
    assert doc.title == "My Guide"
    assert doc.format == "markdown"
    assert doc.metadata.get("author") == "Talat"
    assert doc.id
    headings = doc.metadata.get("headings")
    assert [h["text"] for h in headings] == ["Intro", "Details"]
    assert headings[0]["level"] == 1
    assert headings[0]["offset"] == 0
    assert "**" not in doc.text
    assert "https://example.com" not in doc.text
    assert "bold" in doc.text


def test_markdown_offsets_match_normalized_text() -> None:
    doc = MarkdownParser().parse(b"# Alpha\n\nbody\n\n## Beta\n\nmore", reference="x", source="s")
    text = doc.text
    for heading in doc.metadata.get("headings"):
        assert text[heading["offset"] :].startswith(heading["text"])


def test_markdown_invalid_utf8_decodes() -> None:
    doc = MarkdownParser().parse(b"# Head\xff", reference="x", source="s")
    assert doc.title.startswith("Head")  # invalid byte is replaced, not fatal


def test_html_extracts_title_headings_text() -> None:
    raw = b"""<html><head><title>Page Title</title></head>
<body><h1>Welcome</h1><p>First paragraph.</p>
<p>Second paragraph.</p><script>var evil = true;</script></body></html>"""
    doc = HtmlParser().parse(raw, reference="page.html", source="web")
    assert doc.title == "Welcome"
    assert doc.format == "html"
    assert "First paragraph." in doc.text
    assert "Second paragraph." in doc.text
    assert "var evil" not in doc.text
    headings = doc.metadata.get("headings")
    assert headings[0]["text"] == "Welcome"


def test_txt_parser() -> None:
    doc = TextParser().parse(b"Hello world\n\nSecond para.", reference="a.txt", source="fs")
    assert doc.title == "Hello world"
    assert doc.text == "Hello world\n\nSecond para."
    assert doc.format == "txt"


def test_json_text_shape() -> None:
    doc = JsonParser().parse(
        b'{"title": "T", "content": "Body line one.\\n\\nBody line two."}',
        reference="a.json",
        source="s",
    )
    assert doc.title == "T"
    assert "Body line one." in doc.text
    assert "Body line two." in doc.text


def test_json_sections_shape() -> None:
    raw = (
        b'{"title": "JT", "sections": [{"title": "S1", "text": "One."},'
        b' {"title": "S2", "text": "Two."}]}'
    )
    doc = JsonParser().parse(raw, reference="j", source="s")
    assert doc.text == "S1\nOne.\n\nS2\nTwo."


def test_json_non_object_falls_back_to_dumps() -> None:
    doc = JsonParser().parse(b"[1, 2, 3]", reference="j", source="s")
    assert "1" in doc.text
    assert "2" in doc.text


def test_json_invalid_is_plain_text() -> None:
    doc = JsonParser().parse(b"not json at all", reference="j", source="s")
    assert doc.text == "not json at all"


def test_yaml_document() -> None:
    raw = b"title: YT\ncontent: Body text here.\nmeta:\n  k: v"
    doc = YamlParser().parse(raw, reference="y.yaml", source="s")
    assert doc.format == "yaml"
    assert doc.title == "YT"
    assert doc.text == "Body text here."
    assert doc.metadata.get("meta") == {"k": "v"}


def test_yaml_plain_string() -> None:
    doc = YamlParser().parse(b"Just a plain string", reference="y", source="s")
    assert doc.text == "Just a plain string"


def test_yaml_invalid_falls_back_to_text() -> None:
    doc = YamlParser().parse(b"key: [unclosed", reference="y", source="s")
    assert "key: [unclosed" in doc.text


def test_xml_document() -> None:
    raw = (
        b"<doc><title>XT</title><section><p>Hello para.</p>"
        b'<item key="a" list="true">x,y</item></section></doc>'
    )
    doc = XmlParser().parse(raw, reference="x.xml", source="s")
    assert doc.format == "xml"
    assert doc.title == "XT"
    assert "Hello para." in doc.text
    assert "x,y" in doc.text


def test_xml_invalid_raises() -> None:
    with pytest.raises(KnowledgeParseError):
        XmlParser().parse(b"<doc><unclosed>", reference="x", source="s")


def test_pdf_requires_pypdf_lazily(monkeypatch) -> None:
    import knowledge.parsers.pdf as pdf_module

    monkeypatch.setattr(pdf_module, "pypdf", None)
    with pytest.raises(KnowledgeParseError, match="pypdf"):
        PdfParser().parse(b"%PDF-1.4 junk", reference="a.pdf", source="s")


def test_pdf_parse_error_wrapped(monkeypatch) -> None:
    import knowledge.parsers.pdf as pdf_module

    class _BrokenPypdf:
        class PdfReader:  # noqa: N801 - mirrors pypdf's class name
            def __init__(self, *args, **kwargs):
                raise RuntimeError("bad pdf")

    monkeypatch.setattr(pdf_module, "pypdf", _BrokenPypdf)
    with pytest.raises(KnowledgeParseError, match="Could not parse PDF"):
        PdfParser().parse(b"%PDF-1.4 junk", reference="a.pdf", source="s")


def test_parser_document_ids_stable() -> None:
    a = MarkdownParser().parse(b"# T\n\nbody", reference="r", source="s")
    b = MarkdownParser().parse(b"# T\n\nbody", reference="r", source="s")
    assert a.id == b.id
    assert a.id == a.id


def test_parser_document_ids_differ_by_reference() -> None:
    a = MarkdownParser().parse(b"# T\n\nbody", reference="r1", source="s")
    b = MarkdownParser().parse(b"# T\n\nbody", reference="r2", source="s")
    assert a.id != b.id
