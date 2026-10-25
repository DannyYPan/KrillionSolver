"""Search coordinator with a shared in-flight request per normalized prompt."""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .prompt_detector import normalize_prompt
from .answer_lexicon import local_candidates
from .learned_answers import get_learned
from .ollama_provider import OLLAMA_MODEL, suggest as suggest_with_ollama
from .search_cache import SearchCache
from .search_provider import SEARCH_BACKENDS, SEARCH_QUERY_COUNT, extract_candidates, make_query, search, split_prompt_exclusions


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
        self._provider_failure_until: dict[str, float] = {}

    def request(self, prompt: str, request_id: int, force: bool = False) -> None:
        key = normalize_prompt(prompt)
        with self._lock:
            if key in self._inflight:
                if request_id not in self._inflight[key]:
                    self._inflight[key].append(request_id)
                return
            retry_at = self._failure_until.get(key, 0.0)
            if not force and retry_at > time.monotonic():
                _core_prompt, excluded = split_prompt_exclusions(prompt)
                local = local_candidates(prompt, excluded)
                learned = [{
                    "answer": answer,
                    "evidence": "Previously entered and confirmed by you for this prompt.",
                    "title": "Your saved answers",
                    "url": "",
                    "sources": [],
                    "evidence_status": "You confirmed this answer",
                    "evidence_score": 0,
                    "source_count": 0,
                } for answer in get_learned(prompt, excluded)]
                self.events.put(("search", {
                    "prompt": prompt,
                    "query": make_query(prompt),
                    "results": [],
                    "candidates": learned + [item for item in local if item["answer"].casefold() not in {entry["answer"].casefold() for entry in learned}],
                    "source": "fresh" if local or learned else "error",
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
            model_candidates: list[dict] = []
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
                    _core_prompt, excluded = split_prompt_exclusions(prompt)
                    local = local_candidates(prompt, excluded)
                    learned = [{
                        "answer": answer,
                        "evidence": "Previously entered and confirmed by you for this prompt.",
                        "title": "Your saved answers",
                        "url": "",
                        "sources": [],
                        "evidence_status": "You confirmed this answer",
                        "evidence_score": 0,
                        "source_count": 0,
                    } for answer in get_learned(prompt, excluded)]
                    pinned = []
                    pinned_keys = set()
                    for item in learned + local + model_candidates:
                        answer_key = str(item.get("answer", "")).casefold().strip()
                        if answer_key and answer_key not in pinned_keys:
                            pinned.append(item)
                            pinned_keys.add(answer_key)
                    # Preserve web evidence when the same answer is also in the local lexicon.
                    web_by_answer = {str(item.get("answer", "")).casefold().strip(): item for item in candidates}
                    for pinned_item in pinned:
                        web_item = web_by_answer.get(str(pinned_item["answer"]).casefold().strip())
                        if web_item and pinned_item.get("evidence_status") != "You confirmed this answer":
                            pinned_item.update(web_item)
                    candidates = pinned + [item for item in candidates if str(item.get("answer", "")).casefold().strip() not in pinned_keys]
                    payload = {
                        "prompt": prompt,
                        "query": make_query(prompt, stage),
                        "results": list(combined),
                        "candidates": candidates,
                        "source": "error" if not combined and not candidates and errors else source,
                        "error": "; ".join(errors) or None,
                        "stage": stage,
                        "complete": complete,
                        "elapsed_seconds": time.perf_counter() - started_at,
                    }
                    with self._lock:
                        request_ids = list(self._inflight.get(key, []))
                    for completed_id in request_ids:
                        self.events.put(("search", {**payload, "request_id": completed_id}))

                stage_errors: dict[str, str] = {}
                if cached is not None:
                    cached_stages = {int(item.get("search_stage", 0)) for item in combined}
                    if not cached_stages:
                        cached_stages = {0}
                    publish(max(cached_stages), [], complete=True, candidates=cached_candidates)
                else:
                    providers = []
                    if force:
                        self._provider_failure_until.pop("ollama", None)
                    for provider in SEARCH_BACKENDS:
                        if force:
                            self._provider_failure_until.pop(provider, None)
                        retry_at = self._provider_failure_until.get(provider, 0.0)
                        if retry_at > time.monotonic():
                            stage_errors[provider] = "provider temporarily unavailable; cooling down"
                        else:
                            providers.append(provider)
                    tasks = [(stage, provider) for provider in providers for stage in range(SEARCH_QUERY_COUNT)]
                    ollama_ready = bool(OLLAMA_MODEL) and self._provider_failure_until.get("ollama", 0.0) <= time.monotonic()
                    if ollama_ready:
                        tasks.append((-1, "ollama"))
                    if not tasks:
                        publish(0, list(dict.fromkeys(stage_errors.values())), complete=True)
                    else:
                        # Show deterministic local dictionary/country answers while the web searches start.
                        publish(0, [], complete=False)
                        with ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="answer-search") as pool:
                            futures = {}
                            for stage, provider in tasks:
                                if provider == "ollama":
                                    futures[pool.submit(suggest_with_ollama, prompt)] = (stage, provider)
                                else:
                                    futures[pool.submit(search, prompt, niche_level=stage, backend=provider)] = (stage, provider)
                            finished = 0
                            for future in as_completed(futures):
                                stage, provider = futures[future]
                                try:
                                    stage_results = future.result()
                                    if provider == "ollama":
                                        model_candidates = stage_results
                                        self._provider_failure_until.pop("ollama", None)
                                    else:
                                        for result in stage_results:
                                            result["search_provider"] = provider
                                        self._merge_stage_results(combined, stage_results, stage, provider)
                                except Exception as exc:
                                    if provider == "ollama":
                                        self._provider_failure_until[provider] = time.monotonic() + self.FAILURE_COOLDOWN_SECONDS
                                    else:
                                        stage_errors[provider] = f"{type(exc).__name__}: {exc}"
                                finished += 1
                                publish(
                                    max(stage, 0),
                                    list(dict.fromkeys(stage_errors.values())),
                                    complete=finished == len(futures),
                                )
                    for provider in providers:
                        if provider in stage_errors:
                            self._provider_failure_until[provider] = time.monotonic() + self.FAILURE_COOLDOWN_SECONDS
                        else:
                            self._provider_failure_until.pop(provider, None)

                if combined and not stage_errors:
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
    def _merge_stage_results(
        combined: list[dict[str, str]], results: list[dict[str, str]], stage: int, provider: str = ""
    ) -> None:
        known = {
            f"{item.get('url', '').casefold()}|{item.get('snippet', '').casefold()}"
            if item.get("url")
            else f"{item.get('title', '').casefold()}|{item.get('snippet', '').casefold()}"
            for item in combined
        }
        for item in results:
            item["search_stage"] = str(stage)
            item["search_provider"] = provider or item.get("search_provider", "")
            key = (
                f"{item.get('url', '').casefold()}|{item.get('snippet', '').casefold()}"
                if item.get("url")
                else f"{item.get('title', '').casefold()}|{item.get('snippet', '').casefold()}"
            )
            if key not in known:
                item["search_providers"] = [item["search_provider"]] if item.get("search_provider") else []
                combined.append(item)
                known.add(key)
            else:
                existing = next((old for old in combined if (
                    f"{old.get('url', '').casefold()}|{old.get('snippet', '').casefold()}"
                    if old.get("url") else f"{old.get('title', '').casefold()}|{old.get('snippet', '').casefold()}"
                ) == key), None)
                if existing is not None and item.get("search_provider"):
                    providers = existing.setdefault("search_providers", [existing.get("search_provider", "")])
                    if item["search_provider"] not in providers:
                        providers.append(item["search_provider"])
