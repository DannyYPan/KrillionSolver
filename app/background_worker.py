"""Search coordinator with a shared in-flight request per normalized prompt."""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .prompt_detector import normalize_prompt
from .search_cache import SearchCache
from .search_provider import extract_candidates, make_query, search


def result_is_current(request_id: int, current_request_id: int, prompt: str, current_prompt: str) -> bool:
    """Reject a completed search if either its request or prompt is obsolete."""
    return request_id == current_request_id and normalize_prompt(prompt) == normalize_prompt(current_prompt)


class SearchWorker:
    FAILURE_COOLDOWN_SECONDS = 60

    def __init__(self, events: queue.Queue, cache: SearchCache | None = None) -> None:
        self.events = events
        self.cache = cache or SearchCache()
        self._lock = threading.Lock()
        self._inflight: dict[str, list[int]] = {}
        self._failure_until: dict[str, float] = {}

    def request(self, prompt: str, request_id: int, force: bool = False) -> None:
        key = normalize_prompt(prompt)
        with self._lock:
            if key in self._inflight:
                if request_id not in self._inflight[key]:
                    self._inflight[key].append(request_id)
                return
            retry_at = self._failure_until.get(key, 0.0)
            if not force and retry_at > time.monotonic():
                self.events.put(("search", {
                    "prompt": prompt,
                    "query": make_query(prompt),
                    "results": [],
                    "candidates": [],
                    "source": "error",
                    "error": "Search recently failed; use Refresh Search to retry",
                    "stage": 2,
                    "complete": True,
                    "elapsed_seconds": 0.0,
                    "request_id": request_id,
                }))
                return
            if force:
                self._failure_until.pop(key, None)
            self._inflight[key] = [request_id]

        def work() -> None:
            started_at = time.perf_counter()
            combined: list[dict[str, str]] = []
            try:
                cached = None if force else self.cache.get(prompt)
                if cached is not None:
                    combined, source = cached, "cached"
                    for item in combined:
                        item.setdefault("search_stage", 0)
                    cached_candidates = self.cache.get_candidates(prompt)
                else:
                    combined, source = [], "fresh"
                    cached_candidates = None

                def publish(stage: int, errors: list[str], complete: bool = False, candidates: list[dict] | None = None) -> None:
                    candidates = candidates if candidates is not None else extract_candidates(combined, prompt)
                    payload = {
                        "prompt": prompt,
                        "query": make_query(prompt, stage),
                        "results": list(combined),
                        "candidates": candidates,
                        "source": "error" if not combined and errors else source,
                        "error": "; ".join(errors) or None,
                        "stage": stage,
                        "complete": complete,
                        "elapsed_seconds": time.perf_counter() - started_at,
                    }
                    with self._lock:
                        request_ids = list(self._inflight.get(key, []))
                    for completed_id in request_ids:
                        self.events.put(("search", {**payload, "request_id": completed_id}))

                stage_errors: dict[int, str] = {}
                if cached is not None:
                    cached_stages = {int(item.get("search_stage", 0)) for item in combined}
                    if not cached_stages:
                        cached_stages = {0}
                    publish(max(cached_stages), [], complete=cached_stages.issuperset({0, 1, 2}), candidates=cached_candidates)
                    stages = [stage for stage in (1, 2) if stage not in cached_stages]
                else:
                    stages = [0, 1, 2]

                if stages:
                    with ThreadPoolExecutor(max_workers=len(stages), thread_name_prefix="answer-search") as pool:
                        futures = {
                            pool.submit(search, prompt) if stage == 0 else pool.submit(search, prompt, niche_level=stage): stage
                            for stage in stages
                        }
                        pending = set(futures)
                        # The broad search always gets first chance to populate the answer list.
                        broad = next((future for future, stage in futures.items() if stage == 0), None)
                        if broad is not None:
                            pending.remove(broad)
                            try:
                                stage_results = broad.result()
                                self._merge_stage_results(combined, stage_results, 0)
                            except Exception as exc:
                                stage_errors[0] = f"{type(exc).__name__}: {exc}"
                            if combined:
                                self.cache.put(prompt, combined, extract_candidates(combined, prompt))
                            publish(0, list(stage_errors.values()), complete=not pending)

                        finished = set()
                        for future in as_completed(pending):
                            stage = futures[future]
                            try:
                                stage_results = future.result()
                                self._merge_stage_results(combined, stage_results, stage)
                            except Exception as exc:
                                stage_errors[stage] = f"{type(exc).__name__}: {exc}"
                            finished.add(stage)
                            all_done = len(finished) == len(pending)
                            publish(stage, list(stage_errors.values()), complete=all_done)

                if combined:
                    self.cache.put(prompt, combined, extract_candidates(combined, prompt))
            finally:
                with self._lock:
                    if not combined:
                        self._failure_until[key] = time.monotonic() + self.FAILURE_COOLDOWN_SECONDS
                    else:
                        self._failure_until.pop(key, None)
                    self._inflight.pop(key, None)

        threading.Thread(target=work, name="web-search", daemon=True).start()

    @staticmethod
    def _merge_stage_results(combined: list[dict[str, str]], results: list[dict[str, str]], stage: int) -> None:
        known = {
            f"{item.get('url', '').casefold()}|{item.get('snippet', '').casefold()}"
            if item.get("url")
            else f"{item.get('title', '').casefold()}|{item.get('snippet', '').casefold()}"
            for item in combined
        }
        for item in results:
            item["search_stage"] = str(stage)
            key = (
                f"{item.get('url', '').casefold()}|{item.get('snippet', '').casefold()}"
                if item.get("url")
                else f"{item.get('title', '').casefold()}|{item.get('snippet', '').casefold()}"
            )
            if key not in known:
                combined.append(item)
                known.add(key)
