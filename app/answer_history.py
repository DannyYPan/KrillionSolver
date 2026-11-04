"""Structured local history for accepted and rejected game answers."""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import csv
from pathlib import Path

from .prompt_detector import normalize_prompt

_lock = threading.RLock()


def _prompt_key(prompt: str) -> str:
    return re.sub(r"[^\w\s]", " ", normalize_prompt(prompt), flags=re.UNICODE).strip()


def history_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "KrillionSolver" / "answer_history.sqlite3"


def _connect() -> sqlite3.Connection:
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS answer_history (
            id INTEGER PRIMARY KEY,
            mode TEXT NOT NULL,
            prompt TEXT NOT NULL,
            normalized_prompt TEXT NOT NULL,
            answer TEXT NOT NULL,
            normalized_answer TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('accepted', 'rejected')),
            source TEXT NOT NULL,
            level TEXT,
            reporter TEXT,
            note TEXT,
            observations INTEGER NOT NULL DEFAULT 1,
            first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(mode, normalized_prompt, normalized_answer)
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS answer_history_lookup
        ON answer_history(mode, normalized_prompt, status, observations DESC)
    """)
    return connection


def record(
    prompt: str,
    answer: str,
    status: str,
    *,
    mode: str = "Krillion",
    source: str = "feedback",
    level: str | None = None,
    reporter: str | None = None,
    note: str | None = None,
) -> bool:
    """Insert or update one normalized answer observation."""
    clean_prompt = " ".join(prompt.split())
    clean_answer = " ".join(answer.split())
    prompt_key = _prompt_key(clean_prompt)
    answer_key = clean_answer.casefold()
    if (not prompt_key or not clean_answer or len(clean_answer) > 100
            or status not in {"accepted", "rejected"}
            or any(ord(char) < 32 for char in clean_answer)):
        return False
    with _lock:
        connection = _connect()
        try:
            connection.execute("""
            INSERT INTO answer_history (
                mode, prompt, normalized_prompt, answer, normalized_answer,
                status, source, level, reporter, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mode, normalized_prompt, normalized_answer) DO UPDATE SET
                prompt=answer_history.prompt,
                answer=answer_history.answer,
                status=excluded.status,
                source=excluded.source,
                level=COALESCE(excluded.level, answer_history.level),
                reporter=COALESCE(excluded.reporter, answer_history.reporter),
                note=COALESCE(excluded.note, answer_history.note),
                observations=answer_history.observations + 1,
                last_seen=CURRENT_TIMESTAMP
            """, (
                mode.strip() or "Krillion", clean_prompt, prompt_key, clean_answer,
                answer_key, status, source.strip() or "feedback", level, reporter, note,
            ))
            connection.commit()
        finally:
            connection.close()
    return True


def import_record(
    prompt: str, answer: str, status: str, *, mode: str = "Krillion", source: str = "legacy-jsonl",
) -> bool:
    """Import an older feedback row without increasing an existing observation count."""
    clean_prompt = " ".join(prompt.split())
    clean_answer = " ".join(answer.split())
    prompt_key = _prompt_key(clean_prompt)
    if (not prompt_key or not clean_answer or len(clean_answer) > 100
            or status not in {"accepted", "rejected"}):
        return False
    with _lock:
        connection = _connect()
        try:
            connection.execute("""
                INSERT OR IGNORE INTO answer_history (
                    mode, prompt, normalized_prompt, answer, normalized_answer, status, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                mode.strip() or "Krillion", clean_prompt, prompt_key, clean_answer,
                clean_answer.casefold(), status, source,
            ))
            connection.commit()
        finally:
            connection.close()
    return True


def accepted(prompt: str, *, mode: str = "Krillion", excluded: list[str] | None = None) -> list[str]:
    """Return accepted answers, prioritizing those observed most often."""
    prompt_key = _prompt_key(prompt)
    blocked = {value.casefold().strip() for value in (excluded or [])}
    if not prompt_key:
        return []
    try:
        with _lock:
            connection = _connect()
            try:
                rows = connection.execute("""
                SELECT answer FROM answer_history
                WHERE mode=? AND normalized_prompt=? AND status='accepted'
                ORDER BY observations DESC, last_seen DESC, id ASC
                """, (mode.strip() or "Krillion", prompt_key)).fetchall()
            finally:
                connection.close()
    except sqlite3.Error:
        return []
    return [row["answer"] for row in rows if row["answer"].casefold().strip() not in blocked]


def details(prompt: str, *, mode: str = "Krillion") -> list[dict[str, object]]:
    """Return report metadata for diagnostics and future export tools."""
    try:
        with _lock:
            connection = _connect()
            try:
                rows = connection.execute("""
                SELECT answer, status, source, level, reporter, note,
                       observations, first_seen, last_seen
                FROM answer_history
                WHERE mode=? AND normalized_prompt=?
                ORDER BY status='accepted' DESC, observations DESC, last_seen DESC
                """, (mode.strip() or "Krillion", _prompt_key(prompt))).fetchall()
            finally:
                connection.close()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def search(query: str = "", *, mode: str = "", status: str = "") -> list[dict[str, object]]:
    """Search history rows for the desktop history manager."""
    clauses: list[str] = []
    params: list[str] = []
    if mode:
        clauses.append("mode=?")
        params.append(mode)
    if status in {"accepted", "rejected"}:
        clauses.append("status=?")
        params.append(status)
    if query.strip():
        clauses.append("(prompt LIKE ? OR answer LIKE ?)")
        pattern = f"%{query.strip()}%"
        params.extend([pattern, pattern])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _lock:
        connection = _connect()
        try:
            rows = connection.execute(f"""
                SELECT id, mode, prompt, answer, status, observations
                FROM answer_history{where}
                ORDER BY normalized_prompt, status='accepted' DESC, observations DESC, answer
            """, params).fetchall()
        finally:
            connection.close()
    return [dict(row) for row in rows]


def update(record_id: int, *, mode: str, prompt: str, answer: str, status: str) -> bool:
    """Edit one history row while preserving its observation count."""
    clean_prompt = " ".join(prompt.split())
    clean_answer = " ".join(answer.split())
    if (not _prompt_key(clean_prompt) or not clean_answer or len(clean_answer) > 100
            or status not in {"accepted", "rejected"}):
        return False
    with _lock:
        connection = _connect()
        try:
            try:
                cursor = connection.execute("""
                    UPDATE answer_history SET
                        mode=?, prompt=?, normalized_prompt=?, answer=?, normalized_answer=?,
                        status=?, source='history-editor', last_seen=CURRENT_TIMESTAMP
                    WHERE id=?
                """, (
                    mode.strip() or "Krillion", clean_prompt, _prompt_key(clean_prompt),
                    clean_answer, clean_answer.casefold(), status, record_id,
                ))
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
                return False
        finally:
            connection.close()
    return cursor.rowcount == 1


def delete(record_id: int) -> bool:
    with _lock:
        connection = _connect()
        try:
            cursor = connection.execute("DELETE FROM answer_history WHERE id=?", (record_id,))
            connection.commit()
        finally:
            connection.close()
    return cursor.rowcount == 1


def export_csv(path: str | Path, rows: list[dict[str, object]] | None = None) -> int:
    """Export the visible history fields to a spreadsheet-compatible CSV."""
    exported = rows if rows is not None else search()
    with Path(path).open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output, fieldnames=["mode", "prompt", "answer", "status", "observations"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(exported)
    return len(exported)
