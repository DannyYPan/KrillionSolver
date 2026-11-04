# KrillionSolver

KrillionSolver is a Windows desktop companion for **Krillion** and **Puffer Party**. It opens the game in a monitored Chromium window, detects each question, and streams concise answers from a local Llama 3.1 8B model through Ollama.

The application uses no web search, cloud AI API, or paid API credits. It never types or submits an answer. You decide which answer to use and copy it into the game.

## What it does

- Detects questions from the visible game-page text.
- Shows one speed-focused Ollama answer first.
- Continues generating additional answers across five passes by default.
- Runs local dictionary and category lookup alongside the first Ollama request.
- Removes duplicate suggestions.
- Removes answers already submitted by you or another player during the current round.
- Resets submitted-answer tracking for every new question and game.
- Keeps the answer list scrollable and returns it to the top for each question.
- Supports correct and wrong feedback for future fine-tuning.
- Provides local fallback answers when Ollama is unavailable for a supported category.

## Requirements

Install these before the first launch:

1. **64-bit Python for Windows** with the Python Launcher and Tcl/Tk options enabled.
2. **Ollama for Windows**.
3. Enough RAM or GPU memory to run Llama 3.1 8B.

Install the base 8B model once from PowerShell or Command Prompt:

```powershell
ollama pull llama3.1:latest
```

If you already created the fine-tuned model below, the launcher will use `krillionsolver:8b` automatically.

## Install and start

Double-click [Run KrillionSolver.bat](Run%20KrillionSolver.bat).

The launcher automatically:

1. Changes to the KrillionSolver project directory.
2. Creates the app environment at `.venv` when missing.
3. Installs [requirements.txt](requirements.txt).
4. Installs Playwright Chromium.
5. Finds or starts the local Ollama service.
6. Selects `krillionsolver:8b` when installed, otherwise `llama3.1:latest`.
7. Loads the selected model and reports when it is ready.
8. Opens the desktop application.

The initial setup and first model load can take several minutes. Later launches are faster. The batch file works from any starting directory, so do not create the environment from `C:\Windows\System32` yourself.

You can also run the launcher from PowerShell opened in this project folder:

```powershell
.\Run KrillionSolver.bat
```

After first-run setup, you can start the Python application directly:

```powershell
.\.venv\Scripts\python.exe prompt_assistant.py
```

Direct launch expects Ollama to already be running.

## Play a game

1. Open KrillionSolver.
2. Choose **Krillion** or **Puffer Party**.
3. Leave the supplied URL unchanged unless the game address has changed.
4. Press **Start**.
5. Use the visible Chromium window opened by KrillionSolver to join or begin the game.
6. When a question appears, confirm that it is shown under **Detected prompt**.
7. Copy a suggested answer with `⧉` and submit it yourself in the game.

When the monitored browser opens, KrillionSolver changes to compact view. It is a separate always-available desktop window rather than a transparent layer drawn inside the game.

## Interface controls

### Browser controls

- **Start** opens and monitors the selected game.
- **Stop** closes the monitored browser session and clears round state.
- **Restart** closes and reopens the browser with a clean game session.
- **Automatic answers** generates answers whenever a new prompt is detected.
- **Diagnostics** shows the URL, extracted page text, selected prompt, detection method, and browser errors.

### Answer controls

- **Refresh Answer** starts a fresh five-pass generation for the current prompt.
- **Clear** clears the displayed answer list.
- **Compact view / Full view** switches between the game view and configuration view.
- **Always on top** keeps the solver window above the game browser.
- `⧉` copies that answer.
- `✓` records that answer as correct training feedback.
- `✕` records that answer as wrong, removes it, and requests replacements.

The answer list supports the mouse wheel. A new question clears the previous list and scrolls back to the first answer.

## How answer generation works

The solver uses up to five Ollama passes:

1. **Pass 1 prioritizes speed.** It asks for one answer with a small token limit. It does not wait for the local lexicon.
2. Local dictionary and category lookup runs simultaneously on another worker thread.
3. **Passes 2 through 5** request more answers, use the local hints, and exclude answers already produced.
4. A new question cancels the remaining passes for the previous question.

Later Ollama passes remain sequential because simultaneous 8B generations can increase VRAM use and reduce responsiveness. The first model request and local lookup already run concurrently.

Successful results are cached for 10 minutes. Repeated detections do not start duplicate requests, the Tkinter interface is never blocked, and events belonging to an older question are ignored.

## Local knowledge and checking

The local lexicon supplies quick hints and ranks answers for supported prompt types:

- English words that start with, end with, or contain specified text.
- Compound words.
- Words with a requested syllable count, using CMU pronunciation data.
- Countries, geographic regions, flag colors, coastlines, and the supported population condition.
- Characters from *How I Met Your Mother* and *SpongeBob SquarePants*.
- Sitcom, situation-comedy, and “sitdown comedy” TV-show prompts.
- Animals and traits such as shells, stripes, spots, horns, wings, and scales.
- Foods, fruits, vegetables, sports, instruments, occupations, vehicles, flowers, trees, planets, gemstones, board games, dinosaurs, and body parts.
- Interjections and filler words or phrases.
- Explicit exclusions such as `prototype doesn't count`.

Local data acts as a ranking aid rather than a complete answer bank. A locally confirmed match moves toward the top. A plausible answer missing from the local data remains lower in the list to avoid false negatives. Definite spelling-rule violations, malformed output, explicit exclusions, and duplicates are removed.

## Already-submitted answers

Every second, the browser monitor compares displayed candidates with answer rows visible on the game page. It recognizes common formats such as:

```text
London
2. Tokyo
Alex: Paris
Alex: Paris +20 points
```

If you or another player already submitted an answer during the current round, KrillionSolver removes it and excludes it from later Ollama passes. It also saves that prompt-and-answer pair as correct training data. When the same normalized prompt appears in the future, the learned answer is available immediately from the local lexicon and is ranked before built-in suggestions. Duplicate observations are stored only once. This is separate from wrong-answer feedback and is not added to the rejected training data.

The submitted-answer list resets when:

- A new question is detected.
- The monitored browser starts.
- The browser stops or closes.
- The game is restarted.
- You switch between game modes.

## Performance settings

The defaults are suitable for normal use. Set variables in PowerShell before a direct Python launch when you need to change them:

```powershell
$env:KRILLION_OLLAMA_MODEL = "krillionsolver:8b"
$env:KRILLION_OLLAMA_PASSES = "5"
$env:KRILLION_OLLAMA_TIMEOUT_SECONDS = "60"
$env:KRILLION_OLLAMA_KEEP_ALIVE = "10m"
.\.venv\Scripts\python.exe prompt_assistant.py
```

| Variable | Default | Purpose |
| --- | ---: | --- |
| `KRILLION_OLLAMA_MODEL` | `llama3.1:latest` | Local Ollama model used during direct Python launch. |
| `KRILLION_OLLAMA_PASSES` | `5` | Generation passes; accepted range is 1 through 8. |
| `KRILLION_OLLAMA_TIMEOUT_SECONDS` | `60` | Timeout for one Ollama request. |
| `KRILLION_OLLAMA_KEEP_ALIVE` | `10m` | How long Ollama keeps the model loaded after a request. Use `0` to unload immediately. |

The batch launcher selects `krillionsolver:8b` or `llama3.1:latest` itself to guarantee an 8B model. Use direct Python launch for another local tag.

## Feedback files

Feedback is stored outside the repository so reinstalling or updating the project does not erase it:

```text
%LOCALAPPDATA%\KrillionSolver\training_examples.jsonl
%LOCALAPPDATA%\KrillionSolver\rejected_answers.jsonl
```

- `training_examples.jsonl` contains prompt-and-answer pairs confirmed with `✓` or accepted on the monitored game page.
- `rejected_answers.jsonl` contains answers rejected with `✕`.

Feedback does not modify the running model immediately. It becomes training data the next time you fine-tune and recreate the Ollama model.

Use **Edit Training Data.bat** to review or correct saved data. Keep one valid JSON object per line. Delete a whole line to remove a bad entry.

## Fine-tune on this PC

Training is optional and requires a compatible NVIDIA CUDA GPU. Keep training packages separate from the desktop app environment.

1. Install 64-bit Python 3.12.
2. Create the training environment from this project folder:

   ```powershell
   py -3.12 -m venv .training-venv
   .\.training-venv\Scripts\python.exe -m pip install --upgrade pip
   ```

3. Follow the current Unsloth Windows/WSL installation instructions for the PyTorch and CUDA versions on this computer.
4. Install the remaining training packages:

   ```powershell
   .\.training-venv\Scripts\python.exe -m pip install -r training\requirements.txt
   ```

5. Double-click **Train KrillionSolver.bat**.
6. Review every confirmed and rejected example printed by the preview.
7. Type `EDIT` to edit the data, `TRAIN` to begin, or anything else to cancel.
8. Wait for training and Q4_K_M GGUF export to finish.
9. Run the `ollama create` command printed by the trainer.
10. Restart KrillionSolver.

The local export is normally written under `training\export` and includes a `Modelfile`.

## Fine-tune with Google Colab

Use Colab when this PC does not have a supported CUDA training setup:

1. Double-click **Prepare Colab Training.bat**.
2. Locate `KrillionSolver-Colab-Training.zip` in the project folder.
3. Open [training/KrillionSolver_Colab_Training.ipynb](training/KrillionSolver_Colab_Training.ipynb) in Google Colab.
4. Select **Runtime → Change runtime type → T4 GPU**.
5. Run the notebook cells in order.
6. Upload `KrillionSolver-Colab-Training.zip` when requested.
7. Download the trained export ZIP produced by the final cell.
8. Extract that ZIP on this computer.
9. Open PowerShell in the extracted directory and run:

   ```powershell
   ollama create krillionsolver:8b -f Modelfile
   ```

10. Run **Run KrillionSolver.bat** again. It will detect and load `krillionsolver:8b`.

Do not delete the downloaded export until `ollama create` succeeds. Colab runtimes are temporary, so download the export before closing or resetting the runtime. Detailed training notes are in [training/README.md](training/README.md).

## Prompt detection and diagnostics

The monitor reads visible page text about once per second and selects likely standalone questions or category instructions. It filters common navigation, timers, scores, and game controls.

If the detected prompt is wrong or missing:

1. Enable **Diagnostics**.
2. Check **Selected** and **Extracted page text**.
3. Confirm the question is visible as text in the monitored Chromium window.
4. Restart the browser if the page stopped updating.

A prompt rendered only as an image or canvas may require a future OCR adapter.

## Troubleshooting

### Ollama was not found

Install Ollama for Windows, close and reopen the terminal, and verify:

```powershell
ollama --version
```

### The model is missing

Install the base model:

```powershell
ollama pull llama3.1:latest
```

List installed models with:

```powershell
ollama list
```

### No answers appear

1. Confirm `ollama list` shows `krillionsolver:8b` or `llama3.1:latest`.
2. Confirm the launcher reports that the model is running and ready.
3. Confirm **Detected prompt** contains the real game question.
4. Press **Refresh Answer**.
5. Enable **Diagnostics** and inspect any error.

### The first answer is slow

The first launch may need to load several gigabytes of model data. Later questions are faster while the model remains loaded. Keep `KRILLION_OLLAMA_KEEP_ALIVE=10m` or raise it if memory permits.

### Chromium does not launch

From the project folder, run:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

### Tkinter is missing

Repair or reinstall Python for Windows with the Tcl/Tk component enabled.

### PowerShell opened in `C:\Windows\System32`

Run the batch launcher directly. It changes to the correct project folder automatically:

```powershell
& "C:\Users\danny\OneDrive\Desktop\KrillionSolver\KrillionSolver\Run KrillionSolver.bat"
```

### A valid answer disappears

Open **Diagnostics** and check whether the same answer appears as a standalone row in the page text. Already-submitted detection intentionally removes exact answer rows, but does not treat ordinary prose or the question itself as a submission.

## Tests

Run the complete offline suite from the project folder:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite currently includes **5,000 generated edge cases** covering prompt recognition, exclusions, dictionary constraints, local knowledge, model-output parsing, duplicate handling, submitted-answer detection, Unicode normalization, and false-positive prevention. Tests do not call Ollama or the internet.

## Project layout

```text
KrillionSolver/
├── Run KrillionSolver.bat
├── Train KrillionSolver.bat
├── Prepare Colab Training.bat
├── Edit Training Data.bat
├── prompt_assistant.py
├── requirements.txt
├── app/
│   ├── answer_lexicon.py
│   ├── background_worker.py
│   ├── browser_manager.py
│   ├── learned_answers.py
│   ├── ollama_provider.py
│   ├── prompt_constraints.py
│   ├── prompt_detector.py
│   ├── search_cache.py
│   ├── site_adapters.py
│   └── ui.py
├── training/
│   ├── finetune_krillion.py
│   ├── preview_training.py
│   ├── prepare_colab_bundle.py
│   ├── trivia_data.jsonl
│   └── KrillionSolver_Colab_Training.ipynb
└── tests/
```
