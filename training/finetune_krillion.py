"""QLoRA fine-tune a Llama 3.1 Instruct checkpoint for concise trivia suggestions."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path

from datasets import Dataset
from trl import DPOConfig, DPOTrainer, SFTConfig, SFTTrainer
from unsloth import FastLanguageModel, is_bfloat16_supported


ROOT = Path(__file__).resolve().parent
DATA_FILE = Path(os.environ.get("KRILLION_TRAIN_DATA", ROOT / "trivia_data.jsonl"))
OUTPUT_DIR = Path(os.environ.get("KRILLION_OUTPUT_DIR", ROOT / "outputs"))
EXPORT_DIR = Path(os.environ.get("KRILLION_EXPORT_DIR", ROOT / "export"))
MODEL_NAME = os.environ.get(
    "KRILLION_BASE_MODEL", "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"
)
MAX_SEQ_LENGTH = int(os.environ.get("KRILLION_MAX_SEQ_LENGTH", "512"))

SYSTEM_PROMPT = """You help with fast open-answer trivia. Return a concise, directly usable answer.
For constrained prompts, obey every stated condition and exclusion. Prefer a safe, category-matching answer first; then provide a few less-obvious alternatives only when you can name them confidently. Keep each answer short, usually one word or a short proper name. Do not explain, invent acceptance, or claim rarity/validity is verified. If uncertain, say UNCERTAIN instead of making up an answer.
Use exactly this format:
SAFE: <one quick candidate>
MORE OPTIONS: <up to four comma-separated alternatives>"""


def _supported_kwargs(callable_obj, candidates: dict) -> dict:
    """Keep the example usable across nearby Transformers/TRL releases."""
    try:
        signature = inspect.signature(callable_obj)
        return {key: value for key, value in candidates.items() if key in signature.parameters}
    except (TypeError, ValueError):
        return candidates


def load_training_dataset(tokenizer) -> Dataset:
    rows = []
    with DATA_FILE.open(encoding="utf-8") as data_file:
        for line_number, line in enumerate(data_file, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            prompt, answer = row.get("prompt"), row.get("answer")
            if not isinstance(prompt, str) or not isinstance(answer, str) or not prompt.strip() or not answer.strip():
                raise ValueError(f"Invalid prompt/answer on {DATA_FILE.name}:{line_number}")
            rows.append((prompt.strip(), answer.strip()))
    local_app_data = os.environ.get("LOCALAPPDATA")
    user_data_dir = Path(local_app_data) / "KrillionSolver" if local_app_data else None
    training_file = user_data_dir / "training_examples.jsonl" if user_data_dir else None
    if training_file and training_file.is_file():
        try:
            for line_number, line in enumerate(training_file.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                example = json.loads(line)
                prompt, answer = example.get("prompt"), example.get("answer")
                if isinstance(prompt, str) and prompt.strip() and isinstance(answer, str) and answer.strip():
                    rows.append((prompt.strip(), f"SAFE: {answer.strip()}\nMORE OPTIONS:"))
                else:
                    print(f"Skipping invalid training example on line {line_number}.")
        except (OSError, ValueError) as exc:
            print(f"Could not load confirmed training examples ({exc}); continuing with the curated dataset.")
    # Import feedback created by older app versions without deleting the original file.
    learned_file = user_data_dir / "learned_answers.json" if user_data_dir else None
    if learned_file and learned_file.is_file():
        try:
            learned = json.loads(learned_file.read_text(encoding="utf-8"))
            for prompt, answers in learned.items():
                if isinstance(prompt, str) and isinstance(answers, list):
                    for answer in answers:
                        if isinstance(answer, str) and answer.strip():
                            rows.append((f"Category: {prompt}\nUse the confirmed answer first; give no unsupported alternatives.", f"SAFE: {answer.strip()}\nMORE OPTIONS:"))
        except (OSError, ValueError) as exc:
            print(f"Could not import legacy saved answers ({exc}); continuing with the training JSONL data.")
    rows = list(dict.fromkeys(rows))
    if len(rows) < 10:
        raise ValueError("Add at least 10 reviewed examples before training; tiny datasets overfit quickly.")

    def format_row(row):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": row["prompt"]},
            {"role": "assistant", "content": row["answer"]},
        ]
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)

    dataset = Dataset.from_dict({"prompt": [row[0] for row in rows], "answer": [row[1] for row in rows]})
    return dataset.map(lambda row: {"text": format_row(row)}, remove_columns=["prompt", "answer"])


def load_preference_dataset(tokenizer) -> Dataset | None:
    """Pair wrong model answers with manually confirmed answers for that prompt."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    user_data_dir = Path(local_app_data) / "KrillionSolver" if local_app_data else None
    if not user_data_dir:
        return None
    confirmed_file = user_data_dir / "training_examples.jsonl"
    rejected_file = user_data_dir / "rejected_answers.jsonl"
    if not confirmed_file.is_file() or not rejected_file.is_file():
        return None

    def key(value: str) -> str:
        return " ".join(value.split()).casefold()

    confirmed: dict[str, list[str]] = {}
    for line in confirmed_file.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        prompt, answer = row.get("prompt"), row.get("answer")
        if isinstance(prompt, str) and isinstance(answer, str) and prompt.strip() and answer.strip():
            confirmed.setdefault(key(prompt), []).append(answer.strip())

    preference_rows = []
    seen = set()
    for line in rejected_file.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        prompt, rejected = row.get("prompt"), row.get("answer")
        if not isinstance(prompt, str) or not isinstance(rejected, str):
            continue
        for chosen in confirmed.get(key(prompt), []):
            if chosen.casefold() == rejected.casefold():
                continue
            signature = (key(prompt), chosen.casefold(), rejected.casefold())
            if signature in seen:
                continue
            seen.add(signature)
            formatted_prompt = tokenizer.apply_chat_template(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt.strip()},
                ],
                tokenize=False,
                add_generation_prompt=True,
            )
            preference_rows.append({
                "prompt": formatted_prompt,
                "chosen": f"SAFE: {chosen}\nMORE OPTIONS:",
                "rejected": f"SAFE: {rejected.strip()}\nMORE OPTIONS:",
            })
    return Dataset.from_list(preference_rows) if preference_rows else None


def main() -> None:
    if not DATA_FILE.is_file():
        raise FileNotFoundError(f"Training data not found: {DATA_FILE}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading {MODEL_NAME}. First run downloads the base model.")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )
    dataset = load_training_dataset(tokenizer)
    print(f"Training on {len(dataset)} reviewed examples.")

    training_options = _supported_kwargs(SFTConfig, {
        "output_dir": str(OUTPUT_DIR),
        "per_device_train_batch_size": 2,
        "gradient_accumulation_steps": 4,
        "warmup_ratio": 0.05,
        "num_train_epochs": 3,
        "learning_rate": 1e-4,
        "fp16": not is_bfloat16_supported(),
        "bf16": is_bfloat16_supported(),
        "logging_steps": 1,
        "optim": "adamw_8bit",
        "weight_decay": 0.01,
        "lr_scheduler_type": "linear",
        "seed": 3407,
        "report_to": "none",
        "save_strategy": "epoch",
        "dataset_text_field": "text",
        "max_seq_length": MAX_SEQ_LENGTH,
        "max_length": MAX_SEQ_LENGTH,
        "packing": False,
    })
    train_args = SFTConfig(**training_options)
    trainer_options = _supported_kwargs(SFTTrainer, {
        "processing_class": tokenizer,
        "tokenizer": tokenizer,
        "dataset_text_field": "text",
        "max_seq_length": MAX_SEQ_LENGTH,
        "max_length": MAX_SEQ_LENGTH,
    })
    # Only pass one tokenizer argument. Current TRL calls it processing_class;
    # older TRL releases call it tokenizer.
    trainer_signature = inspect.signature(SFTTrainer)
    if "processing_class" in trainer_signature.parameters:
        trainer_options.pop("tokenizer", None)
    elif "tokenizer" in trainer_signature.parameters:
        trainer_options.pop("processing_class", None)
    else:
        trainer_options["processing_class"] = tokenizer
    trainer = SFTTrainer(
        model=model,
        args=train_args,
        train_dataset=dataset,
        **trainer_options,
    )
    trainer.train()

    preferences = load_preference_dataset(tokenizer)
    if preferences is not None:
        print(f"Applying {len(preferences)} wrong-answer preferences paired with your confirmed answers.")
        preference_options = _supported_kwargs(DPOConfig, {
            "output_dir": str(OUTPUT_DIR / "preferences"),
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 4,
            "num_train_epochs": 1,
            "learning_rate": 5e-6,
            "beta": 0.1,
            "fp16": not is_bfloat16_supported(),
            "bf16": is_bfloat16_supported(),
            "optim": "adamw_8bit",
            "logging_steps": 1,
            "report_to": "none",
            "save_strategy": "no",
            "max_length": MAX_SEQ_LENGTH,
            "max_prompt_length": MAX_SEQ_LENGTH - 128,
        })
        preference_args = DPOConfig(**preference_options)
        preference_trainer_options = _supported_kwargs(DPOTrainer, {
            "processing_class": tokenizer,
            "tokenizer": tokenizer,
        })
        preference_signature = inspect.signature(DPOTrainer)
        if "processing_class" in preference_signature.parameters:
            preference_trainer_options.pop("tokenizer", None)
        elif "tokenizer" in preference_signature.parameters:
            preference_trainer_options.pop("processing_class", None)
        preference_trainer = DPOTrainer(
            model=model,
            ref_model=None,
            args=preference_args,
            train_dataset=preferences,
            **preference_trainer_options,
        )
        preference_trainer.train()
    else:
        print("No preference pairs found. To teach a correction, mark an answer wrong and add a confirmed answer for the same prompt.")

    print("Exporting quantized GGUF; this needs additional disk/RAM and can take a while.")
    model.save_pretrained_gguf(str(EXPORT_DIR), tokenizer, quantization_method="q4_k_m")
    gguf_files = sorted(EXPORT_DIR.rglob("*.gguf"))
    if not gguf_files:
        raise FileNotFoundError(f"No GGUF file was created inside {EXPORT_DIR}")
    model_file = gguf_files[0].resolve()
    modelfile = EXPORT_DIR / "Modelfile"
    modelfile.write_text(
        f'FROM "{model_file.as_posix()}"\n'
        f'SYSTEM """{SYSTEM_PROMPT}"""\n'
        "PARAMETER temperature 0.2\n"
        "PARAMETER num_predict 80\n",
        encoding="utf-8",
    )
    print(f"GGUF ready: {model_file}")
    print(f"Next: ollama create krillionsolver:8b -f \"{modelfile.resolve()}\"")
    print("Then launch Run KrillionSolver.bat; it will use krillionsolver:8b when installed.")


if __name__ == "__main__":
    main()
