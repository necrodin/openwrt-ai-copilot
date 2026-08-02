"""Conversation memory: store, rolling window, trimming, compression, snapshots.

Three cooperating pieces:

- :class:`InMemoryMemoryStore` — a thread-safe, in-memory persistence layer for
  :class:`ConversationState` (swap for a durable backend behind the
  :class:`MemoryStore` protocol later).
- :class:`RollingConversationMemory` — enforces the rolling context window:
  drops the oldest turn when the window size is exceeded, keeps the live window
  within a token budget, and compresses overflow into :class:`MemorySnapshot`
  summaries (deterministic, extractive — no LLM).
- :class:`ConversationManager` — the facade apps call to drive a conversation.

Compression is intentionally non-LLM: older turns are summarised by their first
sentences plus keyword extraction, so the same input always yields the same
snapshot (easy to test, cache, and audit).
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import Counter

from rag.models import ConversationState, MemorySnapshot, Message
from rag.protocols import ConversationMemory, MemoryStore
from rag.tokens import HeuristicTokenEstimator, TokenEstimator

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-zA-Z]+")

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "for",
        "nor",
        "so",
        "yet",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "with",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
        "who",
        "whom",
        "how",
        "when",
        "where",
        "why",
        "do",
        "does",
        "did",
        "will",
        "would",
        "can",
        "could",
        "should",
        "may",
        "might",
        "have",
        "has",
        "had",
        "not",
        "you",
        "your",
        "we",
        "they",
        "he",
        "she",
        "them",
        "i",
        "my",
        "me",
    }
)


def _message_id(role: str, content: str) -> str:
    payload = f"{role}\x00{content}".encode()
    return hashlib.sha256(payload).hexdigest()


def summarize_messages(
    messages: list[Message],
    *,
    max_chars: int = 400,
    max_keywords: int = 5,
) -> tuple[str, list[str]]:
    """Deterministic extractive summary: first sentences + keywords."""
    sentences: list[str] = []
    for message in messages:
        sentence = _SENTENCE_BREAK.split(message.content or "")
        pieces = (piece.strip() for piece in sentence if piece.strip())
        first = next(pieces, message.content[:80])
        sentences.append(f"{message.role}: {first}")
    summary = "; ".join(sentences)[:max_chars]
    words = _WORD.findall(" ".join(message.content for message in messages).casefold())
    counts = Counter(word for word in words if word not in _STOPWORDS and len(word) > 2)
    keywords = [word for word, _ in counts.most_common(max_keywords)]
    return summary, keywords


class InMemoryMemoryStore(MemoryStore):
    """Thread-safe in-memory :class:`ConversationState` storage."""

    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}
        self._lock = threading.RLock()

    def create(self, conversation_id: str, *, title: str = "") -> ConversationState:
        with self._lock:
            state = self._states.get(conversation_id)
            if state is not None:
                return state
            state = ConversationState(conversation_id=conversation_id, title=title)
            self._states[conversation_id] = state
            return state

    def get(self, conversation_id: str) -> ConversationState | None:
        with self._lock:
            return self._states.get(conversation_id)

    def list(self) -> list[ConversationState]:
        with self._lock:
            return list(self._states.values())

    def delete(self, conversation_id: str) -> bool:
        with self._lock:
            return self._states.pop(conversation_id, None) is not None

    def save(self, state: ConversationState) -> ConversationState:
        with self._lock:
            self._states[state.conversation_id] = state
            return state

    def clear(self) -> None:
        with self._lock:
            self._states.clear()


class RollingConversationMemory(ConversationMemory):
    """Rolling-window memory with trimming, compression, and snapshots."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        window_size: int = 20,
        max_snapshots: int = 8,
        compress_threshold: int = 30,
        estimator: TokenEstimator | None = None,
    ) -> None:
        self.store = store or InMemoryMemoryStore()
        self.window_size = max(1, window_size)
        self.max_snapshots = max(1, max_snapshots)
        self.compress_threshold = max(1, compress_threshold)
        self.estimator = estimator or HeuristicTokenEstimator()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # ConversationMemory API                                             #
    # ------------------------------------------------------------------ #

    def add(self, conversation_id: str, role: str, content: str) -> ConversationState:
        with self._lock:
            state = self.store.create(conversation_id)
            if not content:
                return state
            state.messages.append(Message(role=role, content=content))
            state.token_count += self.estimator.estimate(content)
            state.pending_turns += 1
            self._trim(state)
            self._compress_if_needed(state)
            return self.store.save(state)

    def history(
        self,
        conversation_id: str,
        *,
        max_tokens: int | None = None,
    ) -> list[Message]:
        with self._lock:
            state = self.store.get(conversation_id)
            if state is None:
                return []
            return self._fit_history(state.messages, max_tokens)

    def state(self, conversation_id: str) -> ConversationState | None:
        with self._lock:
            return self.store.get(conversation_id)

    def snapshot(self, conversation_id: str) -> MemorySnapshot | None:
        with self._lock:
            state = self.store.get(conversation_id)
            return state.snapshots[-1] if state and state.snapshots else None

    # ------------------------------------------------------------------ #
    # Convenience                                                        #
    # ------------------------------------------------------------------ #

    def create(self, conversation_id: str, *, title: str = "") -> ConversationState:
        with self._lock:
            return self.store.create(conversation_id, title=title)

    def reset(self, conversation_id: str) -> None:
        with self._lock:
            self.store.delete(conversation_id)

    def clear(self) -> None:
        with self._lock:
            self.store.clear()

    def _fit_history(self, messages: list[Message], max_tokens: int | None) -> list[Message]:
        if max_tokens is None or max_tokens <= 0:
            return list(messages)
        kept: list[Message] = []
        total = 0
        for message in reversed(messages):
            cost = self.estimator.estimate(message.content)
            if total + cost > max_tokens:
                break
            kept.append(message)
            total += cost
        kept.reverse()
        return kept

    # ------------------------------------------------------------------ #
    # Window + compression                                               #
    # ------------------------------------------------------------------ #

    def _trim(self, state: ConversationState) -> None:
        """Drop the oldest messages beyond the rolling window size."""
        while len(state.messages) > self.window_size:
            dropped = state.messages.pop(0)
            state.token_count = max(0, state.token_count - self.estimator.estimate(dropped.content))

    def _compress_if_needed(self, state: ConversationState) -> None:
        """Compress old turns into a snapshot once enough have accumulated.

        Triggers when ``pending_turns`` reaches the compression threshold and
        the live window has room to spare, then folds the oldest
        ``compress_threshold // 2`` messages into a :class:`MemorySnapshot`.
        """
        chunk_size = self.compress_threshold // 2
        while state.pending_turns >= self.compress_threshold and len(state.messages) >= chunk_size:
            overflow = state.messages[:chunk_size]
            summary, keywords = summarize_messages(overflow)
            snapshot = MemorySnapshot(
                conversation_id=state.conversation_id,
                summary=summary,
                keywords=keywords,
                message_ids=[_message_id(m.role, m.content) for m in overflow],
                token_count=self.estimator.estimate(summary),
            )
            state.snapshots.append(snapshot)
            state.snapshots = state.snapshots[-self.max_snapshots :]
            state.messages = state.messages[len(overflow) :]
            compressed_cost = sum(self.estimator.estimate(m.content) for m in overflow)
            state.token_count = max(0, state.token_count - compressed_cost)
            state.pending_turns -= len(overflow)


class ConversationManager:
    """Facade for driving a conversation through rolling-window memory."""

    def __init__(
        self,
        memory: ConversationMemory | None = None,
        *,
        estimator: TokenEstimator | None = None,
    ) -> None:
        self.memory = memory or RollingConversationMemory()
        self.estimator = estimator or HeuristicTokenEstimator()

    def create(self, conversation_id: str, *, title: str = "") -> ConversationState:
        return self.memory.create(conversation_id, title=title)

    def add_user(self, conversation_id: str, content: str) -> ConversationState:
        return self.memory.add(conversation_id, "user", content)

    def add_assistant(self, conversation_id: str, content: str) -> ConversationState:
        return self.memory.add(conversation_id, "assistant", content)

    def get_state(self, conversation_id: str) -> ConversationState | None:
        return self.memory.state(conversation_id)

    def get_history(
        self,
        conversation_id: str,
        *,
        max_tokens: int | None = None,
    ) -> list[Message]:
        return self.memory.history(conversation_id, max_tokens=max_tokens)

    def snapshot(self, conversation_id: str) -> MemorySnapshot | None:
        return self.memory.snapshot(conversation_id)

    def reset(self, conversation_id: str) -> None:
        self.memory.reset(conversation_id)

    def list_conversations(self) -> list[ConversationState]:
        return self.memory.store.list()


__all__ = [
    "ConversationManager",
    "InMemoryMemoryStore",
    "RollingConversationMemory",
    "summarize_messages",
]
