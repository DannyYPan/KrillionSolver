"""Conservative text-based prompt detection for Krillion game pages."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Detection:
    prompt: str | None
    method: str
    extracted_text: str
    error: str | None = None


def normalize_prompt(text: str) -> str:
    """Normalize whitespace and Unicode for duplicate comparison."""
    value = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", value).strip().casefold()


_PROMPT_START = re.compile(
    r"^(?:(?:name|give|list|think of|come up with)\s+(?:me\s+)?(?:a|an|the|something|someone|one|any|another|one more)\b"
    r"|(?:what|which|who|where|when|why|how)\b"
    r"|(?:fill\s+in\s+the\s+blank|complete\s+the\s+sentence)\b)",
    re.IGNORECASE,
)
_NOISE = re.compile(
    r"^(?:krillion|puffer party|menu|dive in|daily dive|unlimited|archive|settings|"
    r"submit|skip|next|back|play|join|host|ready|loading|waiting|score|players?|"
    r"hearts?|round\s*\d+|\d{1,2}:\d{2}|\d+\s*(?:points?|pts|sec(?:onds?)?))\b",
    re.IGNORECASE,
)
_INSTRUCTION_TEXT = re.compile(
    r"\b(?:name an answer|name anything in|pass the puffer|before it pops|"
    r"play with friends|join a public room|last one floating wins)\b",
    re.IGNORECASE,
)


def _clean_lines(extracted_text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip(" \t\u200b") for line in extracted_text.splitlines() if line.strip()]


def find_said_answers(answers: list[str], extracted_text: str, prompt: str = "") -> list[str]:
    """Find candidate answers already displayed as answer rows on the game page.

    Exact standalone rows and simple ``player: answer``/score rows are accepted.
    The detected prompt line is excluded to avoid treating words in the question
    as previously submitted answers.
    """
    prompt_key = normalize_prompt(prompt)
    lines = [normalize_prompt(line) for line in _clean_lines(extracted_text)]
    lines = [line for line in lines if line and line != prompt_key and len(line) <= 120]
    found: list[str] = []
    for answer in answers:
        answer_key = normalize_prompt(answer)
        if not answer_key:
            continue
        escaped = re.escape(answer_key)
        row = re.compile(
            rf"^(?:(?:[^:]+):\s*)?(?:[-•*]\s*|\d+[.)]\s*)?{escaped}"
            rf"(?:\s*(?:\+?\d+\s*(?:points?|pts?)?|✓|correct))?$",
            re.I,
        )
        if any(row.fullmatch(line) for line in lines):
            found.append(answer)
    return found


def detect_prompt(extracted_text: str, site: str = "krillion") -> Detection:
    """Select a likely standalone prompt line; keep diagnostics when no match exists.

    No CSS selector is assumed: public page inspection currently exposes only the
    shared shell, not a live game round.
    """
    if not extracted_text or not extracted_text.strip():
        return Detection(None, "empty-page-text", extracted_text or "", "No readable page text was available.")

    lines = _clean_lines(extracted_text)
    # Prefer question/instruction lines and reject common game chrome.
    candidates: list[str] = []
    for line in lines:
        if len(line) < 8 or len(line) > 240 or _NOISE.match(line) or _INSTRUCTION_TEXT.search(line):
            continue
        if _PROMPT_START.match(line):
            candidates.append(line)
    if candidates:
        return Detection(candidates[-1], f"{site}-text-heuristic", extracted_text)

    # A question mark by itself is too broad. Only accept a short interrogative
    # sentence if it is not surrounded by control/status text.
    for line in reversed(lines):
        if len(line) <= 180 and "?" in line and not _NOISE.match(line):
            if re.match(r"^(what|which|who|where|when|why|how)\b", line, re.I):
                return Detection(line, f"{site}-question-heuristic", extracted_text)
    return Detection(None, "no-prompt-candidate", extracted_text)
