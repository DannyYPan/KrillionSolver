"""Free web search via the current ddgs package."""

from __future__ import annotations

import re
import threading
import time


def make_query(prompt: str, niche_level: int = 0) -> str:
    original = prompt.strip().rstrip("?.! ")
    topic = re.sub(
        r"^(?:name|list|give me|think of|come up with)\s+(?:me\s+)?(?:a|an|the|something|someone|one|any|another|one more)\s+",
        "",
        original,
        flags=re.IGNORECASE,
    )
    topic = topic if topic.casefold() != original.casefold() else original or prompt.strip()
    if niche_level <= 0:
        return f"examples of {topic}"
    if niche_level == 1:
        return f"unusual examples of {topic}"
    return f"rare lesser-known examples of {topic}"


_LIST_PHRASE = re.compile(
    r"\b(?:such as|including|include|includes|examples include|examples are|for example|e\.g\.)\s+([^.!?]{3,180})",
    re.IGNORECASE,
)
_NUMBERED_ITEM = re.compile(r"(?:^|\s)(?:\d{1,2}[.)]|[-*•])\s*([A-Z][^.!?]{2,90})")
_LIST_CONTEXT = re.compile(r"\b(?:examples?|include|including|following|these|such as|items?)\b", re.IGNORECASE)
_NICHE_SIGNAL = re.compile(r"\b(?:obscure|lesser[- ]known|little[- ]known|overlooked|remote|unusual|forgotten)\b", re.IGNORECASE)
_GENERIC_TITLE = re.compile(
    r"\b(?:list of|top \d+|guide to|examples of|best \w+|facts about|lesser[- ]known|little[- ]known)\b",
    re.IGNORECASE,
)
_WEB_NOISE = re.compile(r"\b(?:website|official site|click here|read more|learn more|homepage|wikimedia|wikipedia|commons)\b|(?:www\.|\.com\b|\.org\b|\.net\b)", re.IGNORECASE)
SEARCH_TIMEOUT_SECONDS = 2
SEARCH_WALL_TIMEOUT_SECONDS = 3.5
_search_slots = threading.BoundedSemaphore(3)


def _candidate_parts(text: str) -> list[str]:
    text = re.sub(r"\([^)]*\)", "", text)
    parts = re.split(r"\s*,\s*|\s+and\s+|\s+or\s+|\s*;\s*", text, flags=re.IGNORECASE)
    candidates = []
    for part in parts:
        value = re.sub(r"^[^\w]+|[^\w]+$", "", part.strip())
        value = re.sub(r"^(?:and|or)\s+", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+(?:are|is|were|was|have|has|remain|lie|can be|may be|flows?|winds?|runs?|lies|located|stretches|crosses|cuts|drains)\b.*$", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+(?:photo|image|picture|source|via)\b.*$", "", value, flags=re.IGNORECASE)
        value = re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.IGNORECASE)
        if (
            2 <= len(value) <= 64
            and len(value.split()) <= 7
            and not _GENERIC_TITLE.search(value)
            and not _WEB_NOISE.search(value)
        ):
            candidates.append(value)
    return candidates


def extract_candidates(results: list[dict[str, str]]) -> list[dict[str, str]]:
    """Extract answer ideas only when a search snippet explicitly supports them.

    This is intentionally conservative. It does not claim game acceptance or
    score rarity; its ordering reflects relevance to the niche-focused query.
    """
    found: dict[str, dict[str, str]] = {}
    for result in results:
        snippet = result.get("snippet", "").strip()
        url = result.get("url", "").strip()
        candidates: list[str] = []
        for match in _LIST_PHRASE.finditer(snippet):
            candidates.extend(_candidate_parts(match.group(1)))
        for match in _NUMBERED_ITEM.finditer(snippet):
            preceding_text = snippet[max(0, match.start() - 140):match.start()]
            if _LIST_CONTEXT.search(preceding_text):
                candidates.extend(_candidate_parts(match.group(1)))

        niche_signal = bool(_NICHE_SIGNAL.search(snippet))
        for candidate in candidates:
            key = re.sub(r"\W+", " ", candidate.casefold()).strip()
            if not key or key in found:
                continue
            found[key] = {
                "answer": candidate,
                "evidence": snippet,
                "url": url,
                "title": result.get("title", ""),
                "niche_signal": "yes" if niche_signal else "search relevance",
                "search_stage": str(result.get("search_stage", 0)),
            }
    return sorted(found.values(), key=lambda item: (int(item.get("search_stage", "0")), item["niche_signal"] == "yes"))


def search(prompt: str, max_results: int = 5, niche_level: int = 0) -> list[dict[str, str]]:
    """Search with a hard wall-clock deadline, even if DDGS tries slow engines."""
    from ddgs import DDGS

    started_at = time.monotonic()
    if not _search_slots.acquire(timeout=SEARCH_WALL_TIMEOUT_SECONDS):
        raise TimeoutError("All search slots are busy; retry in a moment")

    completed = threading.Event()
    outcome: dict[str, object] = {}

    def run_search() -> None:
        try:
            outcome["results"] = DDGS(timeout=SEARCH_TIMEOUT_SECONDS).text(
                make_query(prompt, niche_level), region="us-en", max_results=max_results, backend="auto"
            )
        except Exception as exc:
            outcome["error"] = exc
        finally:
            _search_slots.release()
            completed.set()

    threading.Thread(target=run_search, name="ddgs-request", daemon=True).start()
    remaining = max(0.0, SEARCH_WALL_TIMEOUT_SECONDS - (time.monotonic() - started_at))
    if not completed.wait(remaining):
        raise TimeoutError(f"Search exceeded {SEARCH_WALL_TIMEOUT_SECONDS:g}s; provider/network is too slow")
    if "error" in outcome:
        raise outcome["error"]
    raw_results = outcome.get("results") or []
    normalized: list[dict[str, str]] = []
    for item in raw_results or []:
        normalized.append({
            "title": str(item.get("title") or "Untitled result"),
            "snippet": str(item.get("body") or item.get("snippet") or ""),
            "url": str(item.get("href") or item.get("url") or ""),
        })
    return normalized[:max_results]
