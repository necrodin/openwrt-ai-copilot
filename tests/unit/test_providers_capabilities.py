"""Capability detection heuristic tests."""

from __future__ import annotations

from providers.capabilities import (
    detect_capabilities,
    has_embedding_model,
    has_rerank_model,
    has_vision_model,
)


def test_has_embedding_model() -> None:
    assert has_embedding_model("nomic-embed-text")
    assert has_embedding_model("text-embedding-3-small")
    assert has_embedding_model("bge-m3")
    assert not has_embedding_model("qwen2.5:7b")


def test_has_vision_model() -> None:
    assert has_vision_model("llava:13b")
    assert has_vision_model("gpt-4o")
    assert has_vision_model("qwen2-vl:7b")
    assert not has_vision_model("qwen2.5:7b")


def test_has_rerank_model() -> None:
    assert has_rerank_model("nvidia/llama-3.2-nv-rerankqa-1b-v2")
    assert has_rerank_model("cross-encoder/ms-marco-MiniLM")
    assert not has_rerank_model("qwen2.5:7b")


def test_declared_defaults_win_without_catalog() -> None:
    caps = detect_capabilities(
        declared={"chat", "stream"},
        configured_models=["qwen2.5:7b"],
        catalog_models=[],
    )
    assert caps.as_set == {"chat", "stream"}
    assert caps.static is True


def test_configured_embed_model_enables_embeddings() -> None:
    caps = detect_capabilities(
        declared={"chat", "stream"},
        configured_models=["qwen2.5:7b", "nomic-embed-text"],
        catalog_models=[],
    )
    assert caps.embeddings is True
    assert caps.static is True


def test_catalog_probe_enables_vision_and_marks_runtime() -> None:
    caps = detect_capabilities(
        declared={"chat", "stream"},
        configured_models=["qwen2.5:7b"],
        catalog_models=["llava:13b", "qwen2-vl:7b"],
    )
    assert caps.vision is True
    assert caps.embeddings is False
    assert caps.static is False


def test_catalog_probe_enables_rerank_and_embeddings() -> None:
    caps = detect_capabilities(
        declared={"chat", "stream"},
        configured_models=[],
        catalog_models=["nvidia/llama-3.2-nv-rerankqa-1b-v2"],
    )
    assert caps.rerank is True
    assert caps.static is False


def test_forced_override_wins_and_is_static() -> None:
    caps = detect_capabilities(
        declared={"chat", "stream"},
        configured_models=["qwen2.5:7b"],
        catalog_models=[],
        forced={"chat", "vision"},
    )
    assert caps.as_set == {"chat", "vision"}
    assert caps.static is True
    assert caps.models == ["qwen2.5:7b"]


def test_forced_override_filters_unknown_capabilities() -> None:
    caps = detect_capabilities(
        declared={"chat"},
        configured_models=[],
        catalog_models=[],
        forced={"chat", "teleport"},
    )
    assert "teleport" not in caps.as_set
    assert caps.chat is True
