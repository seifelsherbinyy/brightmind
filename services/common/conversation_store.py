"""Thread-aware conversation memory for BrightMind.

Stores message history keyed by a conversation identifier (Slack thread_ts
or DM channel ID) so the LLM receives prior context when responding.

All storage is in-memory with a configurable TTL and max-history length.
Persistence (SQLite / file) is deferred to Phase 2 per the roadmap.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from time import time
from typing import Dict, List, Optional


@dataclass
class _Entry:
    messages: List[Dict[str, str]] = field(default_factory=list)
    last_access: float = field(default_factory=time)


class ConversationStore:
    """In-memory, thread-safe conversation store with TTL eviction."""

    def __init__(
        self,
        max_messages: int = 20,
        ttl_seconds: float = 3600,
    ) -> None:
        self._store: Dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self.max_messages = max_messages
        self.ttl_seconds = ttl_seconds

    def _evict_expired(self) -> None:
        now = time()
        expired = [
            k for k, v in self._store.items()
            if now - v.last_access > self.ttl_seconds
        ]
        for k in expired:
            del self._store[k]

    def append(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        """Add a message to a conversation."""
        with self._lock:
            self._evict_expired()
            entry = self._store.setdefault(conversation_id, _Entry())
            entry.messages.append({"role": role, "content": content})
            entry.last_access = time()
            if len(entry.messages) > self.max_messages:
                entry.messages = entry.messages[-self.max_messages:]

    def get_history(
        self,
        conversation_id: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Return the full message list for a conversation.

        If *system_prompt* is provided it is prepended as the first message
        (it is **not** stored — callers supply it on every request so the
        prompt can evolve without rewriting history).
        """
        with self._lock:
            self._evict_expired()
            entry = self._store.get(conversation_id)
            history = list(entry.messages) if entry else []

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(history)
        return messages

    def clear(self, conversation_id: str) -> None:
        """Remove all messages for a conversation."""
        with self._lock:
            self._store.pop(conversation_id, None)

    def size(self) -> int:
        """Number of active conversations."""
        with self._lock:
            self._evict_expired()
            return len(self._store)
