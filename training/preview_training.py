"""Print the exact datasets and settings used by the KrillionSolver trainer."""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CURATED_FILE = Path(os.environ.get("KRILLION_TRAIN_DATA", ROOT / "trivia_data.jsonl"))
MODEL_NAME = os.environ.get(
    "KRILLION_BASE_MODEL", "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"
)
OUTPUT_DIR = Path(os.environ.get("KRILLION_OUTPUT_DIR", ROOT / "outputs"))
EXPORT_DIR = Path(os.environ.get("KRILLION_EXPORT_DIR", ROOT / "export"))
USER_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "KrillionSolver"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not path.is_file():
        return rows
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            rows.append({"_error": f"line {line_number}: {exc}"})
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _key(text: object) -> str:
    return " ".join(str(text or "").split()).casefold()


def _display(title: str, rows: list[dict[str, object]]) -> None:
    print(f"\n{title} ({len(rows)})")
    print("-" * 72)
    if not rows:
        print("  None")
        return
    for number, row in enumerate(rows, start=1):
        if "_error" in row:
            print(f"  {number}. INVALID: {row['_error']}")
            continue
        prompt = " ".join(str(row.get("prompt", "")).split())
        answer = " | ".join(str(row.get("answer", "")).splitlines())
        print(f"  {number}. Prompt: {prompt}")
        print(f"     Answer: {answer}")


def main() -> None:
    curated = _read_jsonl(CURATED_FILE)
    confirmed = _read_jsonl(USER_DIR / "training_examples.jsonl")
    rejected = _read_jsonl(USER_DIR / "rejected_answers.jsonl")
    legacy: list[dict[str, object]] = []
    legacy_file = USER_DIR / "learned_answers.json"
    if legacy_file.is_file():
        try:
            legacy_data = json.loads(legacy_file.read_text(encoding="utf-8"))
            if isinstance(legacy_data, dict):
                for prompt, answers in legacy_data.items():
                    if isinstance(answers, list):
                        for answer in answers:
                            if isinstance(prompt, str) and isinstance(answer, str):
                                legacy.append({"prompt": prompt, "answer": answer})
        except (OSError, ValueError) as exc:
            legacy.append({"_error": str(exc)})

    confirmed_by_prompt: dict[str, list[str]] = {}
    for row in confirmed:
        prompt, answer = row.get("prompt"), row.get("answer")
        if isinstance(prompt, str) and isinstance(answer, str) and prompt.strip() and answer.strip():
            confirmed_by_prompt.setdefault(_key(prompt), []).append(answer.strip())

    pairs: list[dict[str, object]] = []
    unpaired: list[dict[str, object]] = []
    for row in rejected:
        prompt, rejected_answer = row.get("prompt"), row.get("answer")
        preferred = confirmed_by_prompt.get(_key(prompt), [])
        usable = [answer for answer in preferred if answer.casefold() != str(rejected_answer).casefold()]
        if usable:
            for answer in usable:
                pairs.append({"prompt": prompt, "answer": f"PREFER {answer} | REJECT {rejected_answer}"})
        else:
            unpaired.append(row)

    print("KRILLIONSOLVER TRAINING PREVIEW")
    print("=" * 72)
    print(f"Base model:       {MODEL_NAME}")
    print("Method:           3 epochs QLoRA supervised fine-tuning")
    print("Preference step:  1 epoch DPO when usable correction pairs exist")
    print("Sequence length:  " + os.environ.get("KRILLION_MAX_SEQ_LENGTH", "512"))
    print(f"Training output:  {OUTPUT_DIR.resolve()}")
    print(f"GGUF export:      {EXPORT_DIR.resolve()}")
    print("Ollama tag:       krillionsolver:8b (created after training)")
    _display("CURATED SUPERVISED EXAMPLES", curated)
    _display("YOUR CONFIRMED SUPERVISED EXAMPLES", confirmed)
    _display("LEGACY SAVED EXAMPLES", legacy)
    _display("USABLE WRONG-ANSWER PREFERENCE PAIRS", pairs)
    _display("REJECTED ANSWERS WITHOUT A CONFIRMED REPLACEMENT (saved, not trained)", unpaired)
    print("\nSUMMARY")
    print("-" * 72)
    print(f"  Supervised rows available before deduplication: {len(curated) + len(confirmed) + len(legacy)}")
    print(f"  Preference pairs available: {len(pairs)}")
    print(f"  Rejections skipped until a correction is supplied: {len(unpaired)}")
    print("  Training can use substantial GPU memory, RAM, disk space, and time.")


if __name__ == "__main__":
    main()
