"""Conversation memory tests: store, rolling window, trim, compress, snapshots."""

from __future__ import annotations

from rag.memory import (
    ConversationManager,
    InMemoryMemoryStore,
    RollingConversationMemory,
    summarize_messages,
)
from rag.models import ConversationState, Message


def test_store_crud() -> None:
    store = InMemoryMemoryStore()
    created = store.create("c1", title="Chat")
    assert created.conversation_id == "c1"
    assert store.get("c1") is created
    assert store.create("c1").conversation_id == "c1"
    assert len(store.list()) == 1
    assert store.delete("c1") is True
    assert store.delete("c1") is False
    assert store.get("c1") is None


def test_store_save_updates_state() -> None:
    store = InMemoryMemoryStore()
    state = store.create("c1")
    state.messages.append(Message(role="user", content="hi"))
    saved = store.save(state)
    assert saved is state
    assert len(store.get("c1").messages) == 1


def test_store_clear() -> None:
    store = InMemoryMemoryStore()
    store.create("a")
    store.create("b")
    store.clear()
    assert store.list() == []


def test_rolling_window_trims_oldest() -> None:
    memory = RollingConversationMemory(window_size=4)
    for i in range(6):
        memory.add("c1", "user", f"message {i}")
    state = memory.state("c1")
    assert len(state.messages) == 4
    assert state.messages[0].content == "message 2"
    assert state.messages[-1].content == "message 5"


def test_empty_content_not_stored() -> None:
    memory = RollingConversationMemory()
    state = memory.add("c1", "user", "")
    assert state.messages == []


def test_history_respects_max_tokens() -> None:
    memory = RollingConversationMemory()
    for _ in range(3):
        memory.add("c1", "user", "word " * 20)
    history = memory.history("c1", max_tokens=30)
    # newest message alone (~100 chars / 4 = 25 tokens) fits, adding older overflows
    assert len(history) == 1
    assert history[0].content.startswith("word")


def test_history_no_limit_returns_all() -> None:
    memory = RollingConversationMemory()
    for i in range(3):
        memory.add("c1", "user", f"m{i}")
    assert len(memory.history("c1")) == 3
    assert memory.history("missing") == []


def test_compression_creates_snapshots() -> None:
    memory = RollingConversationMemory(window_size=10, compress_threshold=16, max_snapshots=3)
    for i in range(8):
        memory.add("c1", "user", f"Question number {i} about the firewall.")
        memory.add("c1", "assistant", f"Answer number {i}: packets are forwarded.")
    state = memory.state("c1")
    assert len(state.snapshots) == 1
    snapshot = state.snapshots[0]
    assert snapshot.conversation_id == "c1"
    assert "Question number" in snapshot.summary
    assert "firewall" in snapshot.keywords
    assert snapshot.message_ids


def test_compression_repeats_and_caps_snapshots() -> None:
    memory = RollingConversationMemory(window_size=6, compress_threshold=10, max_snapshots=2)
    for i in range(30):
        memory.add("c1", "user", f"user message {i}")
        memory.add("c1", "assistant", f"assistant reply {i}")
    state = memory.state("c1")
    assert len(state.snapshots) == 2


def test_token_count_tracks_window() -> None:
    memory = RollingConversationMemory(window_size=3)
    for _ in range(5):
        memory.add("c1", "user", "a" * 40)
    state = memory.state("c1")
    assert len(state.messages) == 3
    assert state.token_count == 3 * 10


def test_snapshot_latest_accessor() -> None:
    memory = RollingConversationMemory(window_size=4, compress_threshold=4)
    memory.add("c1", "user", "a")
    memory.add("c1", "assistant", "b")
    memory.add("c1", "user", "c")
    memory.add("c1", "assistant", "d")
    snapshot = memory.snapshot("c1")
    assert snapshot is not None
    assert snapshot.summary != ""
    assert memory.snapshot("missing") is None


def test_reset_deletes_state() -> None:
    memory = RollingConversationMemory()
    memory.add("c1", "user", "hi")
    memory.reset("c1")
    assert memory.state("c1") is None


def test_summarize_messages_deterministic() -> None:
    messages = [
        Message(role="user", content="The firewall forwards packets."),
        Message(role="assistant", content="Yes it does."),
    ]
    first = summarize_messages(messages)
    second = summarize_messages(messages)
    assert first == second
    summary, keywords = first
    assert summary.startswith("user: The firewall forwards packets.")
    assert "firewall" in keywords


def test_manager_facade() -> None:
    manager = ConversationManager(RollingConversationMemory())
    state = manager.create("c1", title="t1")
    assert isinstance(state, ConversationState)
    manager.add_user("c1", "hello")
    manager.add_assistant("c1", "hi there")
    assert [m.role for m in manager.get_state("c1").messages] == ["user", "assistant"]
    assert manager.get_history("c1")[0].content == "hello"
    assert [s.conversation_id for s in manager.list_conversations()] == ["c1"]
    manager.reset("c1")
    assert manager.get_state("c1") is None
