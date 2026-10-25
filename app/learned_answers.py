"""Persistent answers explicitly confirmed by the user for a prompt."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from .prompt_detector import normalize_prompt

_lock = threading.Lock()


def _store_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "KrillionSolver" / "learned_answers.json"


def _read() -> dict[str, list[str]]:
    try:
        raw = json.loads(_store_path().read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {str(key): list(dict.fromkeys(str(value) for value in values if isinstance(value, str)))
                for key, values in raw.items() if isinstance(values, list)}
    except (OSError, ValueError, TypeError):
        return {}


def get_learned(prompt: str, excluded: list[str] | None = None) -> list[str]:
    key = normalize_prompt(prompt)
    excluded_keys = {value.casefold().strip() for value in (excluded or [])}
    with _lock:
        answers = _read().get(key, [])
    return [answer for answer in answers if answer.casefold().strip() not in excluded_keys]


def remember(prompt: str, answer: str) -> bool:
    """Save an explicitly user-confirmed answer, returning False for invalid input."""
    key = normalize_prompt(prompt)
    answer = " ".join(answer.split())
    if not key or not answer or len(answer) > 100 or any(ord(char) < 32 for char in answer):
        return False
    with _lock:
        data = _read()
        values = data.setdefault(key, [])
        if any(value.casefold() == answer.casefold() for value in values):
            return True
        values.append(answer)
        path = _store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix="learned-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            Path(temporary_name).replace(path)
        finally:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
    return True
