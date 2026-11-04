"""Store user-confirmed answers as examples for the next Ollama fine-tune."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path

from .answer_history import accepted as accepted_history, import_records, record, rejected as rejected_history
from .prompt_detector import normalize_prompt

_lock = threading.Lock()
_migration_attempted: set[Path] = set()


def _training_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "KrillionSolver" / "training_examples.jsonl"


def _rejected_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "KrillionSolver" / "rejected_answers.jsonl"


def _migration_marker() -> Path:
    return _training_path().parent / ".answer_history_migrated"


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
    except (OSError, sqlite3.Error):
        pass
    return rows


def _read_feedback_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        with path.open(encoding="utf-8") as data_file:
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


def _ensure_history_migrated() -> None:
    """Import existing JSONL once, then allow database edits to remain authoritative."""
    marker = _migration_marker()
    if marker in _migration_attempted or marker.exists():
        return
    _migration_attempted.add(marker)
    try:
        rows = [
            (row["prompt"], row["answer"], "accepted") for row in _rows()
        ]
        rows.extend(
            (row["prompt"], row["answer"], "rejected")
            for row in _read_feedback_rows(_rejected_path())
        )
        import_records(rows)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except (OSError, sqlite3.Error):
        # Local history improves answers but must never prevent dictionary or
        # Ollama generation when the profile directory is unavailable.
        return


def migrate_legacy_history() -> None:
    """Public startup hook used by the history manager."""
    with _lock:
        _ensure_history_migrated()


def get_learned(
    prompt: str, excluded: list[str] | None = None, mode: str = "Krillion",
) -> list[str]:
    """Read accepted structured history plus legacy JSONL training examples."""
    excluded_keys = {value.casefold().strip() for value in (excluded or [])}
    with _lock:
        _ensure_history_migrated()
        answers = accepted_history(prompt, mode=mode, excluded=excluded)
    return list(dict.fromkeys(answer for answer in answers if answer.casefold().strip() not in excluded_keys))


def get_rejected(prompt: str, mode: str = "Krillion") -> list[str]:
    """Read answers previously marked wrong so generation cannot repeat them."""
    with _lock:
        _ensure_history_migrated()
        return rejected_history(prompt, mode=mode)


def remember(
    prompt: str, answer: str, *, mode: str = "Krillion", source: str = "feedback",
) -> bool:
    """Append a manually confirmed answer to the fine-tuning corpus."""
    clean_prompt = " ".join(prompt.split())
    clean_answer = " ".join(answer.split())
    if (not normalize_prompt(clean_prompt) or not clean_answer or len(clean_answer) > 100
            or any(ord(char) < 32 for char in clean_answer)):
        return False
    key = (normalize_prompt(clean_prompt), clean_answer.casefold())
    with _lock:
        if not record(clean_prompt, clean_answer, "accepted", mode=mode, source=source):
            return False
        if any((normalize_prompt(row["prompt"]), row["answer"].casefold()) == key for row in _rows()):
            return True
        path = _training_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as data_file:
            data_file.write(json.dumps({"prompt": clean_prompt, "answer": clean_answer}, ensure_ascii=False) + "\n")
            data_file.flush()
            os.fsync(data_file.fileno())
    return True


def reject_answer(
    prompt: str, answer: str, *, mode: str = "Krillion", source: str = "feedback",
) -> bool:
    """Persist a user-rejected model answer for preference fine-tuning."""
    clean_prompt = " ".join(prompt.split())
    clean_answer = " ".join(answer.split())
    if (not normalize_prompt(clean_prompt) or not clean_answer or len(clean_answer) > 100
            or any(ord(char) < 32 for char in clean_answer)):
        return False
    key = (normalize_prompt(clean_prompt), clean_answer.casefold())
    path = _rejected_path()
    with _lock:
        if not record(clean_prompt, clean_answer, "rejected", mode=mode, source=source):
            return False
        try:
            with path.open(encoding="utf-8") as data_file:
                for line in data_file:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if (normalize_prompt(str(row.get("prompt", ""))),
                            str(row.get("answer", "")).casefold()) == key:
                        return True
        except FileNotFoundError:
            pass
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as data_file:
            data_file.write(json.dumps({"prompt": clean_prompt, "answer": clean_answer}, ensure_ascii=False) + "\n")
            data_file.flush()
            os.fsync(data_file.fileno())
    return True
