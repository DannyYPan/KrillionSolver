"""Local Ollama answer generation and tolerant parsing of concise responses."""

from __future__ import annotations

import json
import os
import re
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from .answer_lexicon import candidate_check, prompt_kind
from .prompt_constraints import split_prompt_exclusions

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("KRILLION_OLLAMA_MODEL", "llama3.1:latest").strip()
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("KRILLION_OLLAMA_TIMEOUT_SECONDS", "60"))
OLLAMA_KEEP_ALIVE = os.environ.get("KRILLION_OLLAMA_KEEP_ALIVE", "10m").strip()
OLLAMA_NUM_CTX = max(512, min(8192, int(os.environ.get("KRILLION_OLLAMA_NUM_CTX", "2048"))))

SYSTEM_PROMPT = """You help with fast open-answer trivia. Return concise, directly usable English answers.
First identify the subject immediately after words such as Name, Give, or List. Answer that subject. Words later in qualifiers, exclusions, purposes, or examples do not change the requested subject.
All answers must be complete English words or names normally written in English, never abbreviations, initials, or partial word fragments. Obey every stated condition and exclusion. Treat supplied dictionary/country examples as hints, not as proof they fit. Give one safe, category-matching candidate first, then alternatives only when confident. Usually use one word or a short proper name per answer. Do not explain or claim game acceptance or rarity is verified. If uncertain, say UNCERTAIN.
Return a short list, starting immediately with SAFE: <one candidate>. Put MORE OPTIONS on a new
line and list up to ten distinct alternatives separated by commas. Do not repeat an answer."""

_BAD_EXACT_ANSWERS = {
    "answer", "answers", "candidate", "example", "examples", "none", "unknown",
    "what", "which", "who", "where", "why", "name", "safe", "more options",
}
_BAD_RESULT_TEXT = re.compile(
    r"(?:^|\b)(?:top\s+(?:listeners|results|answers)|popular\s+(?:results|answers)|"
    r"search\s+results?|official\s+(?:site|website)|home\s*page|listeners?\s+this\s+month|"
    r"click\s+here|read\s+more)(?:\b|$)|https?://|www\.|\.com\b|\.org\b|\.net\b",
    re.I,
)


def _looks_like_answer(answer: str, prompt: str, *, fast: bool) -> bool:
    """Remove headings, fragments, and page-title-like model output cheaply."""
    clean = " ".join(answer.split()).strip(" \"'`.,;:!?()[]{}")
    key = re.sub(r"[^\w\s-]", " ", clean.casefold()).strip()
    letters = re.sub(r"[^a-z]", "", key)
    if not clean or not letters or key in _BAD_EXACT_ANSWERS or _BAD_RESULT_TEXT.search(clean):
        return False
    if len(clean) > 100 or len(clean.split()) > 5 or "?" in answer or ":" in answer:
        return False
    # The speed pass previously leaked fragments such as "ab" and "ad".
    # Later checked passes may still return real short titles such as "Up".
    if fast and len(letters) < 3 and not re.search(r"\b(?:letter|symbol|chemical element)\b", prompt, re.I):
        return False
    return True


def _breaks_fast_text_rule(answer: str, kind: tuple[str, str] | None) -> bool:
    """Check spelling constraints without loading the full pronunciation dictionary."""
    if not kind:
        return False
    category, value = kind
    word = re.sub(r"[^a-z]", "", answer.casefold())
    if category == "ending":
        return not word.endswith(value) or len(word) <= len(value)
    if category == "starting":
        return not word.startswith(value) or len(word) <= len(value)
    if category == "contains":
        return value not in word or word == value
    if category == "compound":
        return value not in word or word == value
    return False


def _parts(text: str) -> list[str]:
    return [re.sub(r"^[\s\d.)*-]+|[\s.;]+$", "", part).strip() for part in re.split(r",|\n", text) if part.strip()]


def parse_suggestions(
    text: str, prompt: str, excluded_answers: list[str] | None = None,
    check_local: bool = True,
) -> list[dict[str, object]]:
    if not text or re.search(r"\bUNCERTAIN\b", text, re.I):
        return []
    core, excluded = split_prompt_exclusions(prompt)
    excluded_keys = {item.casefold().strip() for item in excluded}
    excluded_keys.update(item.casefold().strip() for item in (excluded_answers or []))
    lines = {}
    for line in text.splitlines():
        match = re.match(r"\s*(SAFE|MORE OPTIONS)\s*:\s*(.*?)\s*$", line, re.I)
        if match:
            lines[match.group(1).casefold()] = match.group(2)
    ordered = _parts(lines.get("safe", ""))[:1] + _parts(lines.get("more options", ""))[:10]
    if not ordered:
        # Some locally created Ollama tags ignore the requested labels. Accept
        # a short direct answer (or short answer list) instead of dropping it.
        plain = []
        for line in text.splitlines():
            line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
            lead = re.match(r"^(?:the\s+)?(?:answer|candidate)\s*(?::|\bis\b)\s*:?[ \t]*(.+)$", line, re.I)
            if not lead:
                lead = re.match(r"^(?:a good answer|one answer)\s+is\s+(.+)$", line, re.I)
            if lead:
                line = lead.group(1).strip()
            else:
                line = line.strip(" .;:")
                if re.search(r"\b(?:maybe|probably|perhaps|i think|is|are|because|since|as an ai)\b", line, re.I):
                    continue
            if not line or len(line) > 100 or re.search(r"\b(?:as an ai|i cannot|i can't|here is why)\b", line, re.I):
                continue
            if len(line.split()) > 5:
                continue
            plain.extend(_parts(line))
        ordered = plain[:5]
    seen: set[str] = set()
    ranked_results: list[tuple[int, int, dict[str, object]]] = []
    kind = prompt_kind(core)
    closed_category = bool(kind and kind[0] in {
        "trivia", "tv_character", "sitcom", "country", "country_region",
        "ending", "starting", "contains", "compound", "english_word", "syllables",
    })
    strict_lexical = bool(kind and kind[0] in {
        "ending", "starting", "contains", "compound", "english_word", "syllables",
    })
    for answer in ordered:
        key = re.sub(r"\W+", " ", answer.casefold()).strip()
        if not key or key in seen or key in excluded_keys:
            continue
        if not _looks_like_answer(answer, core, fast=not check_local):
            continue
        if not check_local and _breaks_fast_text_rule(answer, kind):
            continue
        check = candidate_check(answer, core) if (check_local or closed_category) else "uncertain"
        if check == "reject":
            continue
        if strict_lexical and check != "match":
            continue
        if not check_local and closed_category and check != "match":
            continue
        seen.add(key)
        # Confirmed local matches keep the model's order at the top. Candidates
        # outside the local data remain available afterward to avoid false negatives.
        ranked_results.append((0 if check == "match" else 1, len(ranked_results), {"answer": answer}))
    ranked_results.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked_results]


def suggest(
    prompt: str,
    hints: list[str] | None = None,
    excluded_answers: list[str] | None = None,
    on_update: Callable[[list[dict[str, object]]], None] | None = None,
    fast: bool = False,
    prefer_rare: bool = False,
) -> list[dict[str, object]]:
    if not OLLAMA_MODEL:
        return []
    body = json.dumps({
        "model": OLLAMA_MODEL,
        # Ollama otherwise unloads an idle model after its default keep-alive
        # period, making the next prompt pay the model-load delay again.
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "stream": True,
        "messages": [
            {"role": "system", "content": (
                SYSTEM_PROMPT
                if not fast
                else "Identify the subject immediately after Name, Give, or List and answer that subject. "
                     "Later qualifiers and examples do not change the subject. Obey every condition and exclusion. "
                     "Return only: SAFE: <answer>. Do not explain."
            )},
            {"role": "user", "content": (
                f"Prompt: {prompt}\n"
                f"Possible English dictionary/country examples to consider: {', '.join(hints or []) or 'none'}\n"
                f"Do not suggest these answers: {', '.join(excluded_answers or []) or 'none'}\n"
                + (
                    "Return one answer immediately."
                    if fast else
                    (
                        "Return only valid candidates that satisfy the prompt. Prefer uncommon, specific, "
                        "less obvious answers after ensuring they are real, well-established, and category-correct. "
                        "Never invent a name merely to make it rare."
                        if prefer_rare else
                        "Return only candidates that satisfy the prompt. Prioritize dependable answers over rarity."
                    )
                )
            )},
        ],
        "options": {
            "temperature": 0.08 if fast else (0.2 if prefer_rare else 0.15),
            "num_predict": 20 if fast else 96,
            "num_ctx": OLLAMA_NUM_CTX,
        },
    }).encode("utf-8")
    request = Request(f"{OLLAMA_HOST}/api/chat", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            accumulated = ""
            last_answers: tuple[str, ...] = ()
            for raw_line in response:
                if not raw_line.strip():
                    continue
                payload = json.loads(raw_line.decode("utf-8"))
                accumulated += str((payload.get("message") or {}).get("content") or "")
                # Publish complete lines and comma-terminated alternatives only;
                # this avoids briefly showing half-generated words.
                stable_lines = []
                for line in accumulated.splitlines(keepends=True):
                    if line.endswith(("\n", "\r")):
                        stable_lines.append(line)
                    elif re.match(r"\s*MORE OPTIONS\s*:", line, re.I) and "," in line:
                        stable_lines.append(line.rsplit(",", 1)[0] + "\n")
                partial = parse_suggestions("".join(stable_lines), prompt, excluded_answers, check_local=not fast)
                answers = tuple(str(item["answer"]) for item in partial)
                if answers != last_answers and on_update and partial:
                    on_update(partial)
                    last_answers = answers
            final_candidates = parse_suggestions(accumulated, prompt, excluded_answers, check_local=not fast)
            if on_update and final_candidates:
                on_update(final_candidates)
            return final_candidates
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        close_error = getattr(exc, "close", None)
        if callable(close_error):
            close_error()
        raise RuntimeError(f"Ollama unavailable: {exc}") from exc
