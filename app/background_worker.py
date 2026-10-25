"""Ollama-first answer generation with lightweight, targeted web checks."""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .answer_lexicon import local_candidates
from .ollama_provider import OLLAMA_MODEL, suggest as suggest_with_ollama
from .prompt_detector import normalize_prompt
from .search_cache import SearchCache
from .search_provider import SEARCH_BACKENDS, search, split_prompt_exclusions, verify_candidates


def result_is_current(request_id: int, current_request_id: int, prompt: str, current_prompt: str) -> bool:
    """Reject a completed search if either its request or prompt is obsolete."""
    return request_id == current_request_id and normalize_prompt(prompt) == normalize_prompt(current_prompt)


class SearchWorker:
    FAILURE_COOLDOWN_SECONDS = 60
    WEB_CHECK_LIMIT = 3

    def __init__(self, events: queue.Queue, cache: SearchCache | None = None) -> None:
        self.events = events
        self.cache = cache or SearchCache()
        self._lock = threading.Lock()
        self._inflight: dict[str, list[int]] = {}
        self._provider_failure_until: dict[str, float] = {}

    def request(self, prompt: str, request_id: int, force: bool = False) -> None:
        key = normalize_prompt(prompt)
        with self._lock:
            if key in self._inflight:
                if request_id not in self._inflight[key]:
                    self._inflight[key].append(request_id)
                return
            if force:
                self._provider_failure_until.pop("ollama", None)
                for backend in SEARCH_BACKENDS:
                    self._provider_failure_until.pop(backend, None)
            self._inflight[key] = [request_id]

        def emit(candidates: list[dict], results: list[dict], complete: bool, error: str | None, source: str) -> None:
            payload = {
                "prompt": prompt,
                "query": "Ollama candidates → targeted web checks",
                "results": list(results),
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
            nonlocal started_at
            started_at = time.perf_counter()
            combined: list[dict[str, str]] = []
            errors: list[str] = []
            candidates: list[dict] = []
            try:
                cached_candidates = None if force else self.cache.get_candidates(prompt)
                cached_results = None if force else self.cache.get(prompt)
                if cached_candidates is not None and cached_results is not None:
                    emit(cached_candidates, cached_results, True, None, "cached")
                    return

                _core, excluded = split_prompt_exclusions(prompt)
                dictionary = local_candidates(prompt, excluded)
                # Confirmed user answers are training data, not a live answer cache.
                hints = list(dict.fromkeys(item["answer"] for item in dictionary))[:12]

                model_error = None
                ollama_generated = False
                if OLLAMA_MODEL and self._provider_failure_until.get("ollama", 0.0) <= time.monotonic():
                    try:
                        candidates = suggest_with_ollama(prompt, hints=hints)
                        ollama_generated = bool(candidates)
                        self._provider_failure_until.pop("ollama", None)
                    except Exception as exc:
                        model_error = f"Ollama unavailable: {exc}"
                        self._provider_failure_until["ollama"] = time.monotonic() + self.FAILURE_COOLDOWN_SECONDS
                else:
                    model_error = "Ollama is disabled or temporarily unavailable."

                # Show the model's candidates while only their supporting pages are checked.
                candidates = candidates or learned + dictionary
                emit(candidates, combined, False, model_error, "ollama" if not model_error else "local-fallback")

                if not candidates:
                    emit([], [], True, model_error or "Ollama returned no usable candidates.", "error")
                    return

                backend = next((name for name in SEARCH_BACKENDS
                                if self._provider_failure_until.get(name, 0.0) <= time.monotonic()), None)
                if not ollama_generated:
                    pass  # Local fallback data is not misrepresented as model output.
                elif backend is None:
                    errors.append("Web search providers are cooling down")
                else:
                    checks = []
                    for candidate in candidates[:self.WEB_CHECK_LIMIT]:
                        answer = str(candidate.get("answer", "")).strip()
                        if answer:
                            checks.append((candidate, f'"{answer}" {prompt}'))
                    with ThreadPoolExecutor(max_workers=max(1, len(checks)), thread_name_prefix="answer-check") as pool:
                        futures = {pool.submit(search, prompt, max_results=3, backend=backend, query=query): candidate
                                   for candidate, query in checks}
                        for future in as_completed(futures):
                            try:
                                results = future.result()
                                for result in results:
                                    result["search_provider"] = backend
                                combined.extend(results)
                                self._provider_failure_until.pop(backend, None)
                                candidates = verify_candidates(candidates, combined)
                                emit(candidates, combined, False, model_error, "ollama")
                            except Exception as exc:
                                errors.append(f"{backend}: {type(exc).__name__}: {exc}")
                                self._provider_failure_until[backend] = time.monotonic() + self.FAILURE_COOLDOWN_SECONDS

                # Saved user-confirmed answers remain clearly marked, regardless of web snippets.
                candidates_by_key = {item["answer"].casefold(): item for item in candidates}
                candidates = list(candidates_by_key.values())
                if not candidates and model_error:
                    errors.append(model_error)
                if ollama_generated and combined and not errors:
                    self.cache.put(prompt, combined, candidates)
                emit(candidates, combined, True, "; ".join(dict.fromkeys(errors)) or model_error, "ollama")
            finally:
                with self._lock:
                    self._inflight.pop(key, None)

        started_at = time.perf_counter()
        threading.Thread(target=work, name="ollama-answer-search", daemon=True).start()
