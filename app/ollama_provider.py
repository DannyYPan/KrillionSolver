"""Optional local Ollama suggestions; candidates remain unverified guesses."""

from __future__ import annotations

import json
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from .answer_lexicon import satisfies_constraint
from .search_provider import split_prompt_exclusions

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("KRILLION_OLLAMA_MODEL", "krillion-fast").strip()
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("KRILLION_OLLAMA_TIMEOUT_SECONDS", "20"))

SYSTEM_PROMPT = """You help with fast open-answer trivia. Return concise, directly usable English answers.
All answers must be English words or names normally written in English. Obey every stated condition and exclusion. Treat supplied dictionary/country examples as hints, not as proof they fit. Give one safe, category-matching candidate first, then up to four alternatives only when confident. Usually use one word or a short proper name per answer. Do not explain or claim game acceptance or rarity is verified. If uncertain, say UNCERTAIN.
Use exactly:
SAFE: <one candidate>
MORE OPTIONS: <up to four comma-separated candidates>"""


def _parts(text: str) -> list[str]:
    return [re.sub(r"^[\s\d.)*-]+|[\s.;]+$", "", part).strip() for part in re.split(r",|\n", text) if part.strip()]


def parse_suggestions(text: str, prompt: str) -> list[dict[str, object]]:
    if not text or re.search(r"\bUNCERTAIN\b", text, re.I):
        return []
    core, excluded = split_prompt_exclusions(prompt)
    excluded_keys = {item.casefold().strip() for item in excluded}
    lines = {}
    for line in text.splitlines():
        match = re.match(r"\s*(SAFE|MORE OPTIONS)\s*:\s*(.*?)\s*$", line, re.I)
        if match:
            lines[match.group(1).casefold()] = match.group(2)
    ordered = _parts(lines.get("safe", ""))[:1] + _parts(lines.get("more options", ""))[:4]
    seen: set[str] = set()
    results = []
    for answer in ordered:
        key = re.sub(r"\W+", " ", answer.casefold()).strip()
        if not key or key in seen or key in excluded_keys or not satisfies_constraint(answer, core):
            continue
        seen.add(key)
        results.append({
            "answer": answer,
            "evidence": "Suggested by your local Ollama model; not checked against Krillion's accepted answers.",
            "title": "Local Ollama suggestion",
            "url": "",
            "sources": [],
            "evidence_status": "Local model suggestion · unverified",
            "evidence_score": 0,
            "source_count": 0,
        })
    return results


def suggest(prompt: str, hints: list[str] | None = None) -> list[dict[str, object]]:
    if not OLLAMA_MODEL:
        return []
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Prompt: {prompt}\n"
                f"Possible English dictionary/country examples to consider: {', '.join(hints or []) or 'none'}\n"
                "Return only candidates that satisfy the prompt."
            )},
        ],
        "options": {"temperature": 0.2, "num_predict": 80},
    }).encode("utf-8")
    request = Request(f"{OLLAMA_HOST}/api/chat", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        close_error = getattr(exc, "close", None)
        if callable(close_error):
            close_error()
        raise RuntimeError(f"Ollama unavailable: {exc}") from exc
    message = payload.get("message") or {}
    return parse_suggestions(str(message.get("content") or ""), prompt)
