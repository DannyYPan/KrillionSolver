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

The trainer also reads confirmed answer entries from `%LOCALAPPDATA%\KrillionSolver\learned_answers.json` when present. Those entries are marked in the examples as safe answers, with no invented rarity labels. Review `training/trivia_data.jsonl` before training: a model memorizes mistakes as readily as correct examples. The sample set is intentionally small and demonstrates the style; expand it with diverse, verified prompts and answers before expecting factual improvement.

## Import and run with Ollama

The script writes a Q4_K_M GGUF and a matching `training/export/Modelfile`. After export:

```powershell
ollama create krillion-fast -f training/export/Modelfile
ollama run krillion-fast
```

The desktop app calls local Ollama at `http://127.0.0.1:11434` using model name `krillion-fast`. Keep Ollama running. Change `KRILLION_OLLAMA_MODEL` to use another installed tag, or set it to an empty string to disable local model suggestions. The app labels these as unverified and applies its deterministic constraints/exclusions where it can.

To run the desktop app with the model tag from PowerShell:

```powershell
$env:KRILLION_OLLAMA_MODEL = "krillion-fast"
..\Run KrillionSolver.bat
```

## Data format

One JSON object per line:

```json
{"prompt":"Category: A compound word containing stop","answer":"SAFE: stopwatch\nMORE OPTIONS: stoplight, stopover, stopgap"}
```

Keep answers short. Include explicit conditions/exclusions in the prompt. Only use answers you have checked; never add made-up acceptance or rarity labels. Add many different prompt shapes, and include `UNCERTAIN` examples where no answer is known so the model learns not to bluff.
