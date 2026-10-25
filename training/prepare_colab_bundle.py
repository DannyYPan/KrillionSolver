"""Package the trainer and current local feedback for the Colab notebook."""

from __future__ import annotations

import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
TRAINING = ROOT / "training"
USER_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "KrillionSolver"
OUTPUT = ROOT / "KrillionSolver-Colab-Training.zip"


def main() -> None:
    members = [
        (TRAINING / "finetune_krillion.py", "training/finetune_krillion.py"),
        (TRAINING / "trivia_data.jsonl", "training/trivia_data.jsonl"),
    ]
    feedback_names = ("training_examples.jsonl", "rejected_answers.jsonl", "learned_answers.json")
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as bundle:
        for source, archive_name in members:
            bundle.write(source, archive_name)
        for name in feedback_names:
            source = USER_DATA / name
            archive_name = f"user_data/KrillionSolver/{name}"
            if source.is_file():
                bundle.write(source, archive_name)
            else:
                bundle.writestr(archive_name, "" if name.endswith(".jsonl") else "{}")
    print(f"Created: {OUTPUT}")
    print("Upload this ZIP when the Colab notebook asks for it.")


if __name__ == "__main__":
    main()
