"""Free web search via the current ddgs package."""

from __future__ import annotations

import os
import re
import threading
import time

from .answer_lexicon import satisfies_constraint


def _pluralize(word: str) -> str:
    irregular = {"person": "people", "child": "children", "man": "men", "woman": "women", "mouse": "mice", "goose": "geese", "tooth": "teeth", "foot": "feet", "fish": "fish", "sheep": "sheep", "deer": "deer", "species": "species", "series": "series"}
    lower = word.casefold()
    if lower in irregular:
        return irregular[lower]
    if lower.endswith("y") and len(lower) > 1 and lower[-2] not in "aeiou":
        return word[:-1] + "ies"
    if lower.endswith(("ss", "us")):
        return word + "es"
    if lower.endswith("s"):
        return word
    if lower.endswith(("x", "ch", "sh")):
        return word + "es"
    return word + "s"


_DOES_NOT_COUNT = r"(?:doesn't|does not|doesnt|don't|do not|isn't|is not)\s+count"


def split_prompt_exclusions(prompt: str) -> tuple[str, list[str]]:
    """Return the actual category prompt and explicit items the game excludes."""
    patterns = (
        re.compile(rf"\s*\((?P<excluded>[^()]*)\s+{_DOES_NOT_COUNT}\b[^)]*\)\s*$", re.I),
        re.compile(rf"\s+(?:[—–-]\s+|;\s*|,\s*)(?P<excluded>.+?)\s+{_DOES_NOT_COUNT}\b[^.!?]*[.!?]*$", re.I),
        re.compile(r"\s+\b(?:excluding|except for|except|but not|not including)\s+(?P<excluded>[^.!?;]+)[.!?]*$", re.I),
    )
    core = prompt.strip()
    excluded: list[str] = []
    for pattern in patterns:
        match = pattern.search(core)
        if not match:
            continue
        raw = match.group("excluded")
        raw = re.sub(r"^\s*but\s+", "", raw, flags=re.I)
        excluded.extend(
            re.sub(r"^(?:a|an|the)\s+", "", part.strip(" .,!?:;—–-"), flags=re.I)
            for part in re.split(r",|\band\b|\bor\b", raw, flags=re.I)
        )
        core = core[:match.start()].rstrip(" ,;—–-")
        break
    return core, [item for item in excluded if item]


def make_query(prompt: str, niche_level: int = 0) -> str:
    prompt, _excluded = split_prompt_exclusions(prompt)
    original = prompt.strip().rstrip("?.! ")
    topic = re.sub(
        r"^(?:name|list|give me|think of|come up with)\s+(?:me\s+)?(?:a|an|the|something|someone|one|any|another|one more)\s+",
        "",
        original,
        flags=re.IGNORECASE,
    )
    topic = re.sub(r"^(?:what|which|who|where|when|why|how)\s+(?:(?:is|are|was|were|do|does|did)\s+)?", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"^(?:a|an|the)\s+", "", topic, flags=re.IGNORECASE)
    topic = topic if topic.casefold() != original.casefold() else original or prompt.strip()
    has_qualifier = re.search(
        r"\b(?:in|on|at|from|near|within|of|for|with|that|which|who|by|made|written|directed|located|found|starts?|ends?)\b",
        topic,
        re.IGNORECASE,
    )
    if not has_qualifier:
        topic = re.sub(r"([A-Za-z]+)$", lambda match: _pluralize(match.group(1)), topic)
    if niche_level <= 0:
        return f"examples of {topic}"
    if niche_level == 1:
        return f"specific named examples of {topic}"
    if niche_level == 2:
        return f"unusual lesser-known examples of {topic}"
    if niche_level == 3:
        return f"list of {topic} names"
    return f"\"examples include\" {topic}"


_LIST_PHRASE = re.compile(
    r"\b(?:such as|including|include|includes|examples include|examples are|for example|e\.g\.)\s+([^.!?]{3,180})",
    re.IGNORECASE,
)
_FACT_SENTENCE = re.compile(
    r"\b(?:the\s+)?([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,4})\s+"
    r"(?:is|was|are|were|lies|flows)\s+(?:an?\s+|the\s+)?([^.!?]{2,120})",
    re.IGNORECASE,
)
_TYPE_OF = re.compile(r"\b([A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*){0,4})\s+is\s+(?:a|an)\s+type\s+of\s+([\w -]{2,50})", re.IGNORECASE)
_COLON_LIST = re.compile(r"\b(?:examples?|groups?|include|including|following|such as)\s*:\s*([^.!?]{3,180})", re.IGNORECASE)
_NUMBERED_ITEM = re.compile(r"(?:^|\s)(?:\d{1,2}[.)]|[-*•])\s*([A-Z][^.!?]{2,90})")
_LIST_CONTEXT = re.compile(r"\b(?:examples?|include|including|following|these|such as|items?)\b", re.IGNORECASE)
_NICHE_SIGNAL = re.compile(r"\b(?:obscure|lesser[- ]known|little[- ]known|overlooked|remote|unusual|forgotten)\b", re.IGNORECASE)
_GENERIC_TITLE = re.compile(
    r"\b(?:list of|top \d+|guide to|examples of|best \w+|facts about|about|overview|introduction|history of|"
    r"popular|famous|well[- ]known|lesser[- ]known|little[- ]known|"
    r"how to|everything you need to know|most beautiful|amazing|ultimate guide|complete guide|listeners? this month|top listeners|most streamed|monthly listeners|charts|what)\b",
    re.IGNORECASE,
)
_WEB_NOISE = re.compile(r"\b(?:website|official site|click here|read more|learn more|homepage|wikimedia|wikipedia|commons)\b|(?:www\.|\.com\b|\.org\b|\.net\b)", re.IGNORECASE)
_TITLE_SPLIT = re.compile(r"\s+(?:\||—|–|-)\s+|:\s+")
_STOP_WORDS = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "name", "list", "give", "me", "what", "which", "who", "where", "when", "why", "how", "is", "are", "some", "examples", "category", "portal", "index"}
# Search calls run in background workers and may take several seconds.
def _positive_env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default

SEARCH_TIMEOUT_SECONDS = _positive_env_int("KRILLION_SEARCH_TIMEOUT_SECONDS", 10)
SEARCH_WALL_TIMEOUT_SECONDS = _positive_env_int("KRILLION_SEARCH_WALL_TIMEOUT_SECONDS", 30)
_configured_backends = os.environ.get(
    "KRILLION_DDGS_BACKENDS", os.environ.get("KRILLION_DDGS_BACKEND", "bing,google,brave")
)
SEARCH_BACKENDS = tuple(dict.fromkeys(part.strip().casefold() for part in _configured_backends.split(",") if part.strip())) or ("bing",)
SEARCH_BACKEND = SEARCH_BACKENDS[0]
SEARCH_QUERY_COUNT = 5
SEARCH_RESULTS_PER_QUERY = _positive_env_int("KRILLION_SEARCH_RESULTS_PER_QUERY", 4)
MAX_CANDIDATES = 12
_search_slots = threading.BoundedSemaphore(len(SEARCH_BACKENDS) * SEARCH_QUERY_COUNT)


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
            and value.casefold() not in {"it", "this", "that", "there", "here", "these", "those", "they"}
            and not _GENERIC_TITLE.search(value)
            and not _WEB_NOISE.search(value)
        ):
            candidates.append(value)
    return candidates


def _snippet_candidates(snippet: str, prompt: str = "") -> list[str]:
    candidates: list[str] = []
    for match in _LIST_PHRASE.finditer(snippet):
        candidates.extend(_candidate_parts(match.group(1)))
    for match in _COLON_LIST.finditer(snippet):
        context = snippet[max(0, match.start() - 100):match.end()]
        describes_groups = re.search(r"\b(?:island|river|mountain|lake)\s+groups?\b", context, re.I)
        prompt_asks_groups = bool(re.search(r"\bgroups?\b", prompt, re.I))
        if not (describes_groups and not prompt_asks_groups):
            candidates.extend(_candidate_parts(match.group(1)))
    for match in _NUMBERED_ITEM.finditer(snippet):
        preceding_text = snippet[max(0, match.start() - 140):match.start()]
        if _LIST_CONTEXT.search(preceding_text):
            candidates.extend(_candidate_parts(match.group(1)))
    # A concise definition can support an answer even when the source does not
    # format its examples as a list (e.g. "A beagle is a type of dog").
    for match in _TYPE_OF.finditer(snippet):
        category = match.group(2).strip().split()
        prompt_terms = _term_set(prompt)
        if not prompt_terms or prompt_terms & _term_set(" ".join(category)):
            candidates.extend(_candidate_parts(match.group(1)))
    prompt_terms = _term_set(prompt)
    for match in _FACT_SENTENCE.finditer(snippet):
        subject, predicate = match.groups()
        if not prompt_terms or prompt_terms & _term_set(subject + " " + predicate):
            candidates.extend(_candidate_parts(subject))
    return candidates


def _title_candidate(title: str, prompt: str) -> str | None:
    """Take a short leading entity from a headline; it remains title-only evidence."""
    if re.match(r"^(?:category|portal|index)\s*:", title.strip(), re.IGNORECASE):
        return None
    title_head = _TITLE_SPLIT.split(title.strip(), maxsplit=1)[0].strip(" -–—|:")
    if not title_head or len(title_head) > 64 or _GENERIC_TITLE.search(title_head) or _WEB_NOISE.search(title_head):
        return None
    if len(title_head.split()) > 5 or re.match(r"^(?:\d+|the best|best|top|how|why|what|discover|explore)\b", title_head, re.I):
        return None
    candidate_tokens = _term_set(title_head)
    prompt_tokens = _term_set(prompt)
    if not candidate_tokens or candidate_tokens.issubset(prompt_tokens):
        return None
    return title_head


def _domain(url: str) -> str:
    match = re.search(r"https?://([^/]+)", url, re.IGNORECASE)
    return match.group(1).casefold().removeprefix("www.") if match else url.casefold()


def _term_set(text: str) -> set[str]:
    terms = {word.casefold() for word in re.findall(r"[\w'-]+", text)} - _STOP_WORDS
    normalized = set()
    for term in terms:
        if len(term) > 4 and term.endswith("ies"):
            normalized.add(term[:-3] + "y")
        elif len(term) > 4 and term.endswith("s") and not term.endswith("ss"):
            normalized.add(term[:-1])
        else:
            normalized.add(term)
    return normalized


def _candidate_key(text: str) -> str:
    """Normalize spelling variants, punctuation, capitalization and simple plurals."""
    invariant = {"bus", "gas", "news", "series", "species", "status"}
    words = re.findall(r"\w+", text.casefold())
    normalized = []
    for word in words:
        if word in invariant or len(word) <= 3:
            normalized.append(word)
        elif word.endswith("ies"):
            normalized.append(word[:-3] + "y")
        elif word.endswith(("ches", "shes", "xes", "zes")):
            normalized.append(word[:-2])
        elif word.endswith("s") and not word.endswith("ss"):
            normalized.append(word[:-1])
        else:
            normalized.append(word)
    return " ".join(normalized)


def extract_candidates(results: list[dict[str, str]], prompt: str = "") -> list[dict[str, object]]:
    """Extract list-supported entities and label headline-only suggestions unverified."""
    found: dict[str, dict[str, object]] = {}
    core_prompt, excluded_items = split_prompt_exclusions(prompt)
    excluded_keys = {_candidate_key(item) for item in excluded_items}

    def add(candidate: str, result: dict[str, str], from_snippet: bool) -> None:
        key = _candidate_key(candidate)
        candidate_terms = _term_set(candidate)
        prompt_terms = _term_set(core_prompt)
        if not key or key in excluded_keys or (candidate_terms and candidate_terms.issubset(prompt_terms)) or not satisfies_constraint(candidate, core_prompt):
            return
        item = found.setdefault(key, {
            "answer": candidate,
            "evidence": "",
            "url": result.get("url", ""),
            "title": result.get("title", ""),
            "sources": [],
            "_support_domains": set(),
            "_stages": [],
            "_relevance": 0,
            "_source_signals": {},
            "_display_forms": {},
        })
        item["_display_forms"][candidate] = item["_display_forms"].get(candidate, 0) + 1
        source = {
            "title": result.get("title", ""),
            "snippet": result.get("snippet", ""),
            "url": result.get("url", ""),
            "evidence_type": "snippet" if from_snippet else "title",
            "search_providers": result.get("search_providers") or [result.get("search_provider", "")],
        }
        sources = item["sources"]
        source_key = (source["url"], source["snippet"], source["title"])
        if all((old["url"], old["snippet"], old["title"]) != source_key for old in sources):
            sources.append(source)
        stage = int(result.get("search_stage", 0))
        item["_stages"].append(stage)
        prompt_terms = _term_set(core_prompt)
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        text_terms = _term_set(title + " " + snippet)
        relevant = not prompt_terms or bool(prompt_terms & text_terms)
        item["_relevance"] += len(prompt_terms & text_terms)
        # Count each URL once, even if extraction found the same candidate in
        # both fields. Distinct domains provide the independent-result bonus.
        url = result.get("url", "")
        result_key = url.casefold().rstrip("/") or f"{title.casefold()}|{snippet.casefold()}"
        signal = item["_source_signals"].setdefault(result_key, {
            "domain": _domain(url), "title": False, "snippet": False,
            "relevant": relevant,
        })
        signal["relevant"] = signal["relevant"] or relevant
        normalized_title = f" {_candidate_key(title)} "
        if relevant and f" {key} " in normalized_title:
            signal["title"] = True
        if from_snippet and relevant:
            signal["snippet"] = True
        if from_snippet and relevant:
            domain = _domain(result.get("url", ""))
            if domain:
                item["_support_domains"].add(domain)
            if not item["evidence"]:
                item["evidence"] = result.get("snippet", "")
                item["url"] = result.get("url", "")
                item["title"] = result.get("title", "")

    for result in results:
        snippet = result.get("snippet", "").strip()
        for candidate in _snippet_candidates(snippet, core_prompt):
            add(candidate, result, from_snippet=True)
        title_candidate = _title_candidate(result.get("title", ""), core_prompt)
        if title_candidate:
            add(title_candidate, result, from_snippet=False)

    candidates = []
    for item in found.values():
        support_domains = item.pop("_support_domains")
        stages = item.pop("_stages")
        relevance = item.pop("_relevance")
        source_signals = item.pop("_source_signals")
        display_forms = item.pop("_display_forms")
        # Pick the most frequently observed spelling/capitalization.
        item["answer"] = max(display_forms, key=display_forms.get)
        title_points = sum(3 for signal in source_signals.values() if signal["title"])
        snippet_points = sum(2 for signal in source_signals.values() if signal["snippet"])
        independent_domains = {
            signal["domain"] for signal in source_signals.values()
            if signal["domain"] and signal["relevant"]
        }
        independent_bonus = max(0, len(independent_domains) - 1) * 2
        category_points = 3 if any(signal["relevant"] for signal in source_signals.values()) else 0
        item["evidence_score"] = title_points + snippet_points + independent_bonus + category_points
        item["source_count"] = len(support_domains)
        item["evidence_status"] = "Snippet-supported" if support_domains else "Title only · unverified"
        item["search_stage"] = str(min(stages, default=0))
        item["_rank_relevance"] = relevance
        candidates.append(item)
    ranked = sorted(
        candidates,
        key=lambda item: (
            not bool(item["source_count"]),
            -int(item["evidence_score"]),
            -int(item["source_count"]),
            -int(item["_rank_relevance"]),
            int(item["search_stage"]),
        ),
    )
    for item in ranked:
        item.pop("_rank_relevance", None)
    return ranked[:MAX_CANDIDATES]


def search(
    prompt: str,
    max_results: int = SEARCH_RESULTS_PER_QUERY,
    niche_level: int = 0,
    backend: str | None = None,
) -> list[dict[str, str]]:
    """Search with a hard wall-clock deadline, even if DDGS tries slow engines."""
    from ddgs import DDGS
    try:
        import certifi
    except ImportError:
        # pip vendors certifi in standard Windows Python installs; use its CA
        # bundle instead of asking primp to read a restricted Windows store.
        from pip._vendor import certifi

    started_at = time.monotonic()
    if not _search_slots.acquire(timeout=SEARCH_WALL_TIMEOUT_SECONDS):
        raise TimeoutError("All search slots are busy; retry in a moment")

    completed = threading.Event()
    outcome: dict[str, object] = {}

    def run_search() -> None:
        try:
            outcome["results"] = DDGS(timeout=SEARCH_TIMEOUT_SECONDS, verify=certifi.where()).text(
                make_query(prompt, niche_level), region="us-en", max_results=max_results,
                backend=backend or SEARCH_BACKEND,
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
            "search_provider": backend or SEARCH_BACKEND,
        })
    return normalized[:max_results]
