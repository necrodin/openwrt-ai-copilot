"""Metadata extractor tests for the knowledge platform."""

from __future__ import annotations

from knowledge.extractors import (
    CompositeMetadataExtractor,
    HeadingExtractor,
    LanguageExtractor,
    SourceExtractor,
    StatsExtractor,
    TitleExtractor,
)
from knowledge.models import KnowledgeDocument, KnowledgeMetadata


def _doc(**overrides) -> KnowledgeDocument:
    fields = {
        "id": "d1",
        "source": "openwrt",
        "reference": "topic:wireguard",
        "format": "markdown",
        "text": "WireGuard configuration for routers\n\nSome more lines.\nThird.",
    }
    fields.update(overrides)
    return KnowledgeDocument(**fields)


def test_title_extractor_from_document_title() -> None:
    metadata = TitleExtractor().extract(_doc(title="Explicit"))
    assert metadata.get("title") == "Explicit"


def test_title_extractor_from_first_heading() -> None:
    doc = _doc(
        title="",
        metadata=KnowledgeMetadata(values={"headings": [{"text": "Intro", "level": 1}]}),
    )
    assert TitleExtractor().extract(doc).get("title") == "Intro"


def test_title_extractor_from_first_line() -> None:
    doc = _doc(title="")
    assert TitleExtractor().extract(doc).get("title") == "WireGuard configuration for routers"


def test_heading_extractor_preserves_headings() -> None:
    headings = [{"text": "A", "level": 1, "offset": 0}]
    doc = _doc(metadata=KnowledgeMetadata(values={"headings": headings}))
    assert HeadingExtractor().extract(doc).get("headings") == headings


def test_heading_extractor_empty() -> None:
    assert HeadingExtractor().extract(_doc()).get("headings") == []


def test_language_extractor_detects() -> None:
    assert (
        LanguageExtractor().extract(_doc(text="The router is configured.")).get("language") == "en"
    )


def test_language_extractor_keeps_explicit() -> None:
    assert LanguageExtractor().extract(_doc(language="de")).get("language") == "de"


def test_source_extractor_plumbing() -> None:
    metadata = SourceExtractor().extract(_doc())
    assert metadata.get("source") == "openwrt"
    assert metadata.get("reference") == "topic:wireguard"
    assert metadata.get("format") == "markdown"


def test_stats_extractor_counts() -> None:
    metadata = StatsExtractor().extract(_doc(text="one two three\n\nfour"))
    assert metadata.get("word_count") == 4
    assert metadata.get("line_count") == 3
    assert metadata.get("char_count") == len("one two three\n\nfour")


def test_composite_extractor_merges_in_order() -> None:
    composite = CompositeMetadataExtractor()
    composite.add(SourceExtractor()).add(TitleExtractor()).add(StatsExtractor())
    metadata = composite.extract(_doc())
    assert metadata.get("source") == "openwrt"
    assert metadata.get("title") == "WireGuard configuration for routers"
    assert metadata.get("word_count") is not None


def test_composite_extractor_overrides_later() -> None:
    class _Later:
        extractor_type = "later"

        def extract(self, document):
            return KnowledgeMetadata(values={"source": "overridden"})

    composite = CompositeMetadataExtractor()
    composite.add(SourceExtractor()).add(_Later())
    assert composite.extract(_doc()).get("source") == "overridden"
