"""Thread-safe in-memory TTL cache for web search results."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from .prompt_detector import normalize_prompt


@dataclass
class CacheEntry:
    expires_at: float
    results: list[dict[str, str]]


class SearchCache:
    def __init__(self, ttl_seconds: float = 600, clock=time.monotonic) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, prompt: str) -> list[dict[str, str]] | None:
        key = normalize_prompt(prompt)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                del self._entries[key]
                return None
            return [dict(item) for item in entry.results]

    def put(self, prompt: str, results: list[dict[str, str]]) -> None:
        with self._lock:
            self._entries[normalize_prompt(prompt)] = CacheEntry(
                self._clock() + self.ttl_seconds, [dict(item) for item in results]
            )

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
