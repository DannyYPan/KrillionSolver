# Fine-tune the local trivia response style

This optional training setup tunes Llama 3.1 8B Instruct to answer in a compact format: one quick candidate first, followed by a few plausible alternatives. It teaches response style and constraint-following; it cannot guarantee Krillion acceptance, rarity tier, or factual correctness. The example JSONL is starter data, not Krillion's answer bank. Replace or supplement it with examples you have reviewed.

## Before training

- Use Python 3.10–3.12 in a separate environment. Do not install training packages into the desktop app's `.venv`.
- Use Unsloth's current platform-specific install guide for Windows/WSL and your GPU/PyTorch combination. Its dependencies are large and CUDA-specific: [Unsloth Windows installation](https://docs.unsloth.ai/get-started/installing-%2B-updating/windows-installation).
- The default model is `unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit`. The first run downloads the Hugging Face checkpoint. If gated access is required, accept Meta's model terms and log in to Hugging Face first.
- An 8B QLoRA run still needs substantial RAM/VRAM and disk space. If your machine cannot train it, use a GPU notebook/host, then copy the exported GGUF back to this PC.

Example, after setting up a separate training environment and installing Unsloth according to its guide:

```powershell
python -m pip install -r training/requirements.txt
python training/finetune_krillion.py
```

For the guided launcher, double-click **Train KrillionSolver.bat** in the project folder. It prints the model and training settings, every curated and user-confirmed example, every usable correct-versus-wrong preference pair, and rejected answers that still need a confirmed correction. Training starts only after you type `TRAIN`. The launcher expects the training environment at `.training-venv\Scripts\python.exe`; alternatively, set `KRILLION_TRAINING_PYTHON` to the full path of a prepared Python executable.

To select another Hugging Face Llama 3.1 Instruct checkpoint, set `KRILLION_BASE_MODEL`. This script fine-tunes an HF/Safetensors checkpoint; an Ollama GGUF file itself is not the input checkpoint.

When you click **Add to training data**, it appends a confirmed answer to `%LOCALAPPDATA%\KrillionSolver\training_examples.jsonl`. Clicking **Wrong** saves the rejected candidate to `%LOCALAPPDATA%\KrillionSolver\rejected_answers.jsonl`. For the trainer to learn a preference, save at least one correct answer for that same prompt too. The trainer first runs supervised fine-tuning on confirmed examples, then applies a DPO preference step pairing confirmed answers as preferred and rejected answers as dispreferred. Wrong answers without a confirmed answer for the same prompt are saved but cannot form a preference pair. The training set requires at least 10 unique examples. None of this changes the running model until training completes and you recreate its Ollama tag.

## Import and run with Ollama

The script writes a Q4_K_M GGUF and a matching `training/export/Modelfile`. After export:

```powershell
ollama create krillionsolver:8b -f training/export/Modelfile
ollama run krillionsolver:8b
```

The desktop launcher checks local Ollama at `http://127.0.0.1:11434`, starts `ollama serve` hidden if needed, and selects `krillionsolver:8b` when that fine-tuned tag is installed. Otherwise it uses `llama3.1:latest` (the base 8B model). Both choices stay on Llama 3.1 8B. Answers are still labeled as unverified, and the app applies deterministic constraints/exclusions where it can.

To run the desktop app with the fine-tuned tag directly from PowerShell:

```powershell
$env:KRILLION_OLLAMA_MODEL = "krillionsolver:8b"
..\Run KrillionSolver.bat
```

After collecting confirmed and wrong-answer feedback, rerun `python training/finetune_krillion.py` from the separate training environment. It prints the `ollama create` command for the new `krillionsolver:8b` model. The launcher will pick it up on its next start. This is offline fine-tuning, not an immediate per-click weight update.

## Data format

One JSON object per line:

```json
{"prompt":"Category: A compound word containing stop","answer":"SAFE: stopwatch\nMORE OPTIONS: stoplight, stopover, stopgap"}
```

Keep answers short. Include explicit conditions/exclusions in the prompt. Only use answers you have checked; never add made-up acceptance or rarity labels. Add many different prompt shapes, and include `UNCERTAIN` examples where no answer is known so the model learns not to bluff.
