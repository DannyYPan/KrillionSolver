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

To select another Hugging Face Llama 3.1 Instruct checkpoint, set `KRILLION_BASE_MODEL`. This script fine-tunes an HF/Safetensors checkpoint; an Ollama GGUF file itself is not the input checkpoint.

When you click **Add to training data** in the app, it appends a JSONL example to `%LOCALAPPDATA%\KrillionSolver\training_examples.jsonl`. The trainer reads these rows alongside `training/trivia_data.jsonl` and formats each confirmed answer as a safe first answer. It also imports older entries from `%LOCALAPPDATA%\KrillionSolver\learned_answers.json`, if present, without deleting that file. These examples do not affect the running model until fine-tuning completes and you recreate its Ollama tag. Review the training examples before training: a model memorizes mistakes as readily as correct answers. The trainer requires at least 10 unique examples.

## Import and run with Ollama

The script writes a Q4_K_M GGUF and a matching `training/export/Modelfile`. After export:

```powershell
ollama create krillion-fast -f training/export/Modelfile
ollama run krillion-fast
```

The desktop app calls local Ollama at `http://127.0.0.1:11434` using model name `krillion-fast` by default. `Run KrillionSolver.bat` checks that service and starts `ollama serve` hidden if needed. Change `KRILLION_OLLAMA_MODEL` to use another installed tag, or set it to an empty string to disable local model suggestions. The app labels model answers as unverified and applies deterministic constraints/exclusions where it can.

To run the desktop app with the model tag from PowerShell:

```powershell
$env:KRILLION_OLLAMA_MODEL = "krillion-fast"
..\Run KrillionSolver.bat
```

After adding feedback examples, rerun `python training/finetune_krillion.py` from the separate training environment. When it finishes, run `ollama create krillion-fast -f training/export/Modelfile` to replace the local tag with the newly fine-tuned export. This is an offline fine-tune, not an automatic per-answer model update.

## Data format

One JSON object per line:

```json
{"prompt":"Category: A compound word containing stop","answer":"SAFE: stopwatch\nMORE OPTIONS: stoplight, stopover, stopgap"}
```

Keep answers short. Include explicit conditions/exclusions in the prompt. Only use answers you have checked; never add made-up acceptance or rarity labels. Add many different prompt shapes, and include `UNCERTAIN` examples where no answer is known so the model learns not to bluff.
