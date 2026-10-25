"""Background Ollama answer generation without blocking the Tkinter UI."""

from __future__ import annotations

import queue
import threading
import time

from .answer_lexicon import local_candidates
from .ollama_provider import OLLAMA_MODEL, suggest as suggest_with_ollama
from .prompt_detector import normalize_prompt
from .search_cache import SearchCache
from .search_provider import split_prompt_exclusions


def result_is_current(request_id: int, current_request_id: int, prompt: str, current_prompt: str) -> bool:
    """Reject a completed answer if either its request or prompt is obsolete."""
    return request_id == current_request_id and normalize_prompt(prompt) == normalize_prompt(current_prompt)


class SearchWorker:
    FAILURE_COOLDOWN_SECONDS = 30

    def __init__(self, events: queue.Queue, cache: SearchCache | None = None) -> None:
        self.events = events
        self.cache = cache or SearchCache()
        self._lock = threading.Lock()
        self._inflight: dict[str, list[int]] = {}
        self._ollama_failure_until = 0.0

    def request(self, prompt: str, request_id: int, force: bool = False) -> None:
        key = normalize_prompt(prompt)
        with self._lock:
            if key in self._inflight:
                if request_id not in self._inflight[key]:
                    self._inflight[key].append(request_id)
                return
            if force:
                self._ollama_failure_until = 0.0
            self._inflight[key] = [request_id]

        started_at = time.perf_counter()

        def emit(candidates: list[dict], complete: bool, error: str | None, source: str) -> None:
            payload = {
                "prompt": prompt,
                "query": "Local Ollama answer (web search skipped)",
                "results": [],
                "candidates": list(candidates),
                "source": source,
                "error": error,
                "stage": 0,
                "complete": complete,
                "elapsed_seconds": time.perf_counter() - started_at,
            }
            with self._lock:
                request_ids = list(self._inflight.get(key, []))
            for completed_id in request_ids:
                self.events.put(("search", {**payload, "request_id": completed_id}))

        def work() -> None:
            try:
                cached_candidates = None if force else self.cache.get_candidates(prompt)
                cached_results = None if force else self.cache.get(prompt)
                if cached_candidates is not None and cached_results is not None:
                    emit(cached_candidates, True, None, "cached")
                    return

                _core, excluded = split_prompt_exclusions(prompt)
                dictionary = local_candidates(prompt, excluded)
                hints = list(dict.fromkeys(item["answer"] for item in dictionary))[:12]
                model_candidates: list[dict] = []
                model_error: str | None = None

                if not OLLAMA_MODEL:
                    model_error = "Ollama is disabled."
                elif self._ollama_failure_until > time.monotonic():
                    model_error = "Ollama recently failed; use Refresh Search to retry."
                else:
                    try:
                        model_candidates = suggest_with_ollama(prompt, hints=hints)
                        self._ollama_failure_until = 0.0
                    except Exception as exc:
                        model_error = f"Ollama unavailable: {exc}"
                        self._ollama_failure_until = time.monotonic() + self.FAILURE_COOLDOWN_SECONDS

                candidates = model_candidates or dictionary
                source = "ollama" if model_candidates else "local-fallback"
                if not candidates and not model_error:
                    model_error = "Ollama did not return a readable answer."

                # Complete immediately after generation; no web request can block or hide it.
                if model_candidates:
                    self.cache.put(prompt, [], model_candidates)
                emit(candidates, True, model_error, source)
            except Exception as exc:
                # Keep unexpected provider/data errors visible in the UI instead of
                # letting the worker thread die without sending a completion event.
                emit([], True, f"Answer generation failed: {type(exc).__name__}: {exc}", "error")
            finally:
                with self._lock:
                    self._inflight.pop(key, None)

        threading.Thread(target=work, name="ollama-answer", daemon=True).start()
