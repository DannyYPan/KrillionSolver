"""Background Ollama answer generation without blocking the Tkinter UI."""

from __future__ import annotations

import queue
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .answer_lexicon import local_candidates
from .learned_answers import get_learned, get_rejected
from .ollama_provider import OLLAMA_MODEL, suggest as suggest_with_ollama
from .prompt_detector import normalize_prompt
from .search_cache import SearchCache
from .prompt_constraints import split_prompt_exclusions

_LEXICON_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="krillion-lexicon")


def result_is_current(request_id: int, current_request_id: int, prompt: str, current_prompt: str) -> bool:
    """Reject a completed answer if either its request or prompt is obsolete."""
    return request_id == current_request_id and normalize_prompt(prompt) == normalize_prompt(current_prompt)


class SearchWorker:
    FAILURE_COOLDOWN_SECONDS = 30
    MAX_OLLAMA_PASSES = max(1, min(8, int(os.environ.get("KRILLION_OLLAMA_PASSES", "5"))))
    MAX_CANDIDATES = max(8, min(40, int(os.environ.get("KRILLION_MAX_CANDIDATES", "24"))))

    def __init__(self, events: queue.Queue, cache: SearchCache | None = None) -> None:
        self.events = events
        self.cache = cache or SearchCache()
        self._lock = threading.Lock()
        self._inflight: dict[tuple[str, str, tuple[str, ...]], list[int]] = {}
        self._live_exclusions: dict[str, set[str]] = {}
        self._active_key: tuple[str, str, tuple[str, ...]] | None = None
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
        excluded_answers: list[str] | None = None, mode: str = "Krillion",
    ) -> None:
        prompt_key = normalize_prompt(prompt)
        mode_key = mode.strip() or "Krillion"
        exclusions = tuple(sorted({item.casefold().strip() for item in (excluded_answers or [])}))
        key = (mode_key.casefold(), prompt_key, exclusions)
        cache_prompt = prompt if mode_key == "Krillion" else f"{mode_key}\n{prompt}"
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
                historical_rejections = get_rejected(prompt, mode=mode_key)
                rejected_keys = {answer.casefold().strip() for answer in historical_rejections}
                cached_candidates = None if force or exclusions else self.cache.get_candidates(cache_prompt)
                cached_results = None if force or exclusions else self.cache.get(cache_prompt)
                if cached_candidates is not None and cached_results is not None:
                    cached_candidates = [
                        item for item in cached_candidates
                        if item["answer"].casefold().strip() not in rejected_keys
                    ]
                    if cached_candidates:
                        emit(cached_candidates, True, None, "cached")
                        return

                _core, excluded = split_prompt_exclusions(prompt)
                learned_candidates = [
                    {"answer": answer, "confirmed": True}
                    for answer in get_learned(
                        prompt, list(excluded) + list(excluded_answers or []), mode=mode_key
                    )
                ]
                if learned_candidates:
                    emit(learned_candidates, False, None, "learned")
                # Run local lookup alongside the first speed-focused Ollama pass.
                # Large dictionary/syllable data must not delay the first answer.
                local_exclusions = list(excluded) + list(excluded_answers or []) + historical_rejections
                dictionary_future = _LEXICON_EXECUTOR.submit(
                    local_candidates, prompt, local_exclusions, 5, mode=mode_key
                )
                dictionary: list[dict] = []
                hints: list[str] = []
                model_candidates: list[dict] = []
                model_error: str | None = None
                generation_complete = threading.Event()
                last_partial_emit = 0.0

                def merge_candidates(*groups: list[dict]) -> list[dict]:
                    merged: list[dict] = []
                    seen: set[str] = set()
                    for group in groups:
                        for item in group:
                            answer_key = item["answer"].casefold().strip()
                            if answer_key and answer_key not in seen:
                                seen.add(answer_key)
                                merged.append(item)
                                if len(merged) >= self.MAX_CANDIDATES:
                                    return merged
                    return merged

                def publish_dictionary(future) -> None:
                    if generation_complete.is_set():
                        return
                    try:
                        ready = future.result()
                    except Exception:
                        return
                    if ready:
                        emit(merge_candidates(learned_candidates, ready, model_candidates), False, None, "local")

                dictionary_future.add_done_callback(publish_dictionary)

                if not OLLAMA_MODEL:
                    model_error = "Ollama is disabled."
                elif self._ollama_failure_until > time.monotonic():
                    model_error = "Ollama recently failed; use Refresh Answer to retry."
                else:
                    try:
                        seen_answers: set[str] = set()
                        for pass_number in range(self.MAX_OLLAMA_PASSES):
                            if pass_number > 0 and not dictionary:
                                dictionary = dictionary_future.result()
                                hints = list(dict.fromkeys(item["answer"] for item in dictionary))[:12]
                            with self._lock:
                                if self._active_key != key:
                                    break
                                live_exclusions = list(self._live_exclusions.get(prompt_key, set()))
                            previous_count = len(model_candidates)

                            def publish_partial(partial: list[dict]) -> None:
                                nonlocal last_partial_emit
                                now = time.monotonic()
                                if now - last_partial_emit < 0.2:
                                    return
                                last_partial_emit = now
                                ready_dictionary = dictionary_future.result() if dictionary_future.done() else []
                                combined = merge_candidates(
                                    learned_candidates, ready_dictionary, model_candidates, partial,
                                )
                                emit(combined, False, None, "ollama")

                            pass_candidates = suggest_with_ollama(
                                prompt,
                                hints=hints,
                                excluded_answers=(
                                    list(excluded_answers or [])
                                    + live_exclusions
                                    + historical_rejections
                                    + [item["answer"] for item in learned_candidates]
                                    + [item["answer"] for item in dictionary]
                                    + [item["answer"] for item in model_candidates]
                                ),
                                on_update=publish_partial,
                                fast=pass_number == 0,
                                prefer_rare=mode_key == "Krillion" and pass_number > 0,
                            )
                            for item in pass_candidates:
                                answer_key = item["answer"].casefold().strip()
                                if answer_key not in seen_answers and len(model_candidates) < self.MAX_CANDIDATES:
                                    seen_answers.add(answer_key)
                                    model_candidates.append(item)
                            if len(model_candidates) == previous_count:
                                break
                            if len(merge_candidates(learned_candidates, dictionary, model_candidates)) >= self.MAX_CANDIDATES:
                                break
                            ready_dictionary = dictionary_future.result() if dictionary_future.done() else []
                            emit(
                                merge_candidates(learned_candidates, ready_dictionary, model_candidates),
                                False, None, "ollama",
                            )
                        self._ollama_failure_until = 0.0
                    except Exception as exc:
                        model_error = f"Ollama unavailable: {exc}"
                        self._ollama_failure_until = time.monotonic() + self.FAILURE_COOLDOWN_SECONDS

                if not dictionary:
                    dictionary = dictionary_future.result()
                with self._lock:
                    live_exclusions = set(self._live_exclusions.get(prompt_key, set()))
                candidates = []
                candidate_keys: set[str] = set()
                for item in merge_candidates(learned_candidates, dictionary, model_candidates):
                    answer_key = item["answer"].casefold().strip()
                    if (answer_key not in live_exclusions and answer_key not in rejected_keys
                            and answer_key not in candidate_keys):
                        candidate_keys.add(answer_key)
                        candidates.append(item)
                source = "ollama" if model_candidates else ("learned" if learned_candidates else "local-fallback")
                if not candidates and not model_error:
                    model_error = "Ollama did not return a readable answer."

                # Complete immediately after local generation.
                if model_candidates and not exclusions:
                    self.cache.put(cache_prompt, [], candidates)
                generation_complete.set()
                emit(candidates, True, model_error, source)
            except Exception as exc:
                # Keep unexpected provider/data errors visible in the UI instead of
                # letting the worker thread die without sending a completion event.
                emit([], True, f"Answer generation failed: {type(exc).__name__}: {exc}", "error")
            finally:
                with self._lock:
                    self._inflight.pop(key, None)

        threading.Thread(target=work, name="ollama-answer", daemon=True).start()
