"""Knowledge source tests (OpenWrt catalog, filesystem, static)."""

from __future__ import annotations

import pytest

from knowledge.errors import KnowledgeSourceError
from knowledge.sources import FileSystemSource, OpenWrtKnowledgeSource, StaticSource
from knowledge.sources.openwrt import OPENWRT_TOPICS


def test_openwrt_source_exposes_all_topics() -> None:
    source = OpenWrtKnowledgeSource()
    assert len(OPENWRT_TOPICS) == 12
    assert source.id == "openwrt"
    assert source.source_type == "openwrt"
    references = source.list_documents()
    assert len(references) == 12
    assert references == [f"topic:{topic}" for topic in list(OPENWRT_TOPICS)]


def test_openwrt_topics_have_catalog_fields() -> None:
    for _topic_id, meta in OPENWRT_TOPICS.items():
        assert "description" in meta
        assert "reference" in meta
        assert "formats" in meta
        assert "packages" in meta
        assert "config_files" in meta
        assert "tags" in meta


def test_openwrt_source_scoped_topics() -> None:
    source = OpenWrtKnowledgeSource(topics=["wireguard", "openvpn"])
    assert source.list_documents() == ["topic:wireguard", "topic:openvpn"]
    assert source.formats == {"html", "markdown"}


def test_openwrt_topic_lookup() -> None:
    source = OpenWrtKnowledgeSource()
    wireguard = source.topic("wireguard")
    assert "WireGuard" in wireguard["description"]
    assert "/etc/config/network" in wireguard["config_files"]


def test_openwrt_topic_unknown_raises() -> None:
    with pytest.raises(KnowledgeSourceError, match="Unknown OpenWrt topic"):
        OpenWrtKnowledgeSource().topic("bogus")


def test_openwrt_load_is_catalog_error() -> None:
    with pytest.raises(KnowledgeSourceError, match="catalog"):
        OpenWrtKnowledgeSource().load("topic:wireguard")


def test_filesystem_source_lists_relative_paths(tmp_path) -> None:
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("b", encoding="utf-8")
    source = FileSystemSource(tmp_path, pattern="**/*")
    assert set(source.list_documents()) == {"a.md", "sub/b.txt"}
    assert source.format_for("a.md") == "markdown"
    assert source.format_for("b.txt") == "txt"
    assert source.format_for("x.unknown") == "txt"


def test_filesystem_source_load(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("content", encoding="utf-8")
    source = FileSystemSource(tmp_path)
    assert source.load("a.txt") == b"content"


def test_filesystem_source_missing_raises(tmp_path) -> None:
    with pytest.raises(KnowledgeSourceError, match="Could not read"):
        FileSystemSource(tmp_path).load("nope.txt")


def test_filesystem_source_missing_root_empty() -> None:
    assert FileSystemSource("/does/not/exist").list_documents() == []


def test_static_source() -> None:
    source = StaticSource(
        "static",
        {"a": "hello", "b": b"bytes"},
        format="txt",
        description="samples",
    )
    assert source.list_documents() == ["a", "b"]
    assert source.load("a") == b"hello"
    assert source.load("b") == b"bytes"
    assert source.format_for("anything") == "txt"
    assert source.id == "static"


def test_static_source_missing_raises() -> None:
    with pytest.raises(KnowledgeSourceError, match="has no document"):
        StaticSource("static").load("nope")
