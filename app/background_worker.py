"""Background Ollama answer generation without blocking the Tkinter UI."""

from __future__ import annotations

import queue
import os
import threading
import time

from .answer_lexicon import local_candidates
from .ollama_provider import OLLAMA_MODEL, suggest as suggest_with_ollama
from .prompt_detector import normalize_prompt
from .search_cache import SearchCache
from .prompt_constraints import split_prompt_exclusions


def result_is_current(request_id: int, current_request_id: int, prompt: str, current_prompt: str) -> bool:
    """Reject a completed answer if either its request or prompt is obsolete."""
    return request_id == current_request_id and normalize_prompt(prompt) == normalize_prompt(current_prompt)


class SearchWorker:
    FAILURE_COOLDOWN_SECONDS = 30
    MAX_OLLAMA_PASSES = max(1, min(8, int(os.environ.get("KRILLION_OLLAMA_PASSES", "5"))))

    def __init__(self, events: queue.Queue, cache: SearchCache | None = None) -> None:
        self.events = events
        self.cache = cache or SearchCache()
        self._lock = threading.Lock()
        self._inflight: dict[tuple[str, tuple[str, ...]], list[int]] = {}
        self._live_exclusions: dict[str, set[str]] = {}
        self._active_key: tuple[str, tuple[str, ...]] | None = None
        self._ollama_failure_until = 0.0

    def exclude(self, prompt: str, answers: list[str]) -> None:
        """Exclude answers observed on the live game page from later passes."""
        key = normalize_prompt(prompt)
        with self._lock:
            self._live_exclusions.setdefault(key, set()).update(
                answer.casefold().strip() for answer in answers if answer.strip()
            )

    def reset_session(self) -> None:
        """Forget live-page exclusions and stop scheduling passes for the old game."""
        with self._lock:
            self._live_exclusions.clear()
            self._active_key = None

    def request(
        self, prompt: str, request_id: int, force: bool = False,
        excluded_answers: list[str] | None = None,
    ) -> None:
        prompt_key = normalize_prompt(prompt)
        exclusions = tuple(sorted({item.casefold().strip() for item in (excluded_answers or [])}))
        key = (prompt_key, exclusions)
        with self._lock:
            self._active_key = key
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
                cached_candidates = None if force or exclusions else self.cache.get_candidates(prompt)
                cached_results = None if force or exclusions else self.cache.get(prompt)
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
                    model_error = "Ollama recently failed; use Refresh Answer to retry."
                else:
                    try:
                        seen_answers: set[str] = set()
                        for pass_number in range(self.MAX_OLLAMA_PASSES):
                            with self._lock:
                                if self._active_key != key:
                                    break
                                live_exclusions = list(self._live_exclusions.get(prompt_key, set()))
                            previous_count = len(model_candidates)

                            def publish_partial(partial: list[dict]) -> None:
                                combined = list(model_candidates)
                                combined_keys = {item["answer"].casefold().strip() for item in combined}
                                combined.extend(
                                    item for item in partial
                                    if item["answer"].casefold().strip() not in combined_keys
                                )
                                emit(combined, False, None, "ollama")

                            pass_candidates = suggest_with_ollama(
                                prompt,
                                hints=hints,
                                excluded_answers=(
                                    list(excluded_answers or [])
                                    + live_exclusions
                                    + [item["answer"] for item in model_candidates]
                                ),
                                on_update=publish_partial,
                                fast=pass_number == 0,
                            )
                            for item in pass_candidates:
                                answer_key = item["answer"].casefold().strip()
                                if answer_key not in seen_answers:
                                    seen_answers.add(answer_key)
                                    model_candidates.append(item)
                            if len(model_candidates) == previous_count:
                                break
                            emit(model_candidates, False, None, "ollama")
                        self._ollama_failure_until = 0.0
                    except Exception as exc:
                        model_error = f"Ollama unavailable: {exc}"
                        self._ollama_failure_until = time.monotonic() + self.FAILURE_COOLDOWN_SECONDS

                with self._lock:
                    live_exclusions = set(self._live_exclusions.get(prompt_key, set()))
                candidates = [
                    item for item in (model_candidates or dictionary)
                    if item["answer"].casefold().strip() not in live_exclusions
                ]
                source = "ollama" if model_candidates else "local-fallback"
                if not candidates and not model_error:
                    model_error = "Ollama did not return a readable answer."

                # Complete immediately after local generation.
                if model_candidates and not exclusions:
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
