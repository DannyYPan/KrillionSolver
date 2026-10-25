"""Store user-confirmed answers as examples for the next Ollama fine-tune."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .prompt_detector import normalize_prompt

_lock = threading.Lock()


def _training_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "KrillionSolver" / "training_examples.jsonl"


def _rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        with _training_path().open(encoding="utf-8") as data_file:
            for line in data_file:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and isinstance(row.get("prompt"), str) and isinstance(row.get("answer"), str):
                    rows.append({"prompt": row["prompt"], "answer": row["answer"]})
    except OSError:
        pass
    return rows


def get_learned(prompt: str, excluded: list[str] | None = None) -> list[str]:
    """Compatibility reader for training examples; the live solver does not call this."""
    key = normalize_prompt(prompt)
    excluded_keys = {value.casefold().strip() for value in (excluded or [])}
    with _lock:
        answers = [row["answer"] for row in _rows() if normalize_prompt(row["prompt"]) == key]
    return list(dict.fromkeys(answer for answer in answers if answer.casefold().strip() not in excluded_keys))


def remember(prompt: str, answer: str) -> bool:
    """Append a manually confirmed answer to the fine-tuning corpus."""
    clean_prompt = " ".join(prompt.split())
    clean_answer = " ".join(answer.split())
    if (not normalize_prompt(clean_prompt) or not clean_answer or len(clean_answer) > 100
            or any(ord(char) < 32 for char in clean_answer)):
        return False
    key = (normalize_prompt(clean_prompt), clean_answer.casefold())
    with _lock:
        if any((normalize_prompt(row["prompt"]), row["answer"].casefold()) == key for row in _rows()):
            return True
        path = _training_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as data_file:
            data_file.write(json.dumps({"prompt": clean_prompt, "answer": clean_answer}, ensure_ascii=False) + "\n")
            data_file.flush()
            os.fsync(data_file.fileno())
    return True
