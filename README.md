# KrillionSolver

KrillionSolver is a Windows desktop companion for Krillion and Puffer Party. It opens the selected game in Chromium, detects the current prompt, and streams concise answers from a local Llama 3.1 8B model through Ollama. It does not use web search, AI credits, or a cloud API.

The solver never types or submits an answer. You choose an answer and copy it into the game.

## Start the app

Double-click **Run KrillionSolver.bat**. The launcher:

1. Changes to the project folder.
2. Creates `.venv` and installs the app dependencies when needed.
3. Installs Playwright Chromium when needed.
4. Starts the local Ollama service.
5. Loads `krillionsolver:8b` when installed, otherwise `llama3.1:latest`.
6. Opens KrillionSolver.

You can also launch it from PowerShell in the project folder:

```powershell
.\Run KrillionSolver.bat
```

Tkinter is included with the standard Windows Python installer. Repair Python with the Tcl/Tk option enabled if Tkinter is missing.

## Use the overlay window

1. Select **Krillion** or **Puffer Party**.
2. Press **Start**. The app opens a visible Chromium window for the game.
3. Join or begin a game in that browser.
4. When a prompt is detected, the solver switches to compact view and starts generating answers.
5. Scroll through the answer list. Each new prompt automatically returns the list to the top.

The controls beside each answer are:

- `⧉` copies the answer.
- `✓` saves the answer as correct training feedback.
- `✕` saves the answer as wrong, removes it, and asks Ollama for replacements.

Use **Refresh Answer** to generate another set, **Clear** to empty the list, and **Full view** to show browser settings. **Always on top** keeps the solver above the game window.

The solver is a separate compact desktop window rather than a transparent layer drawn inside the game.

## How answers are checked

Ollama generates the main answer list. The local lexicon is actively used before and after generation:

- It gives Ollama matching dictionary words and countries as hints.
- It checks English word prompts against the CMU pronunciation dictionary.
- It enforces starts-with, ends-with, contains, compound-word, and syllable-count conditions.
- It checks country names, regions, flag colors, coastlines, and the supported population condition.
- It supplies characters for supported recurring TV-show prompts and sitcom/situation-comedy show prompts.
- It provides quick local hints for common trivia categories such as animals, foods, fruits, vegetables, sports, instruments, occupations, vehicles, plants, planets, gemstones, board games, dinosaurs, body parts, interjections, and filler words.
- It removes explicit exclusions such as `prototype doesn't count`.
- It rejects duplicate, malformed, and definite rule-breaking model output.

Local data is used as a ranking aid rather than an absolute answer bank. Confirmed dictionary or country matches appear first. A candidate that follows the prompt but is missing from the local data stays in the list after the confirmed matches, preventing a limited lexicon from hiding a valid rare answer.

When Ollama is unavailable, matching local dictionary or country entries are shown as a fallback. General knowledge categories that the lexicon does not recognize are answered by Ollama directly.

Generation runs outside the Tkinter main thread. Results from an old prompt are ignored, duplicate requests for the same prompt are shared, and successful answers are cached for 10 minutes. Ollama remains loaded for 10 minutes by default to reduce delays between rounds.

The solver uses up to five Ollama passes. The first pass is speed-focused: it requests one answer with a very small generation limit so something useful can appear quickly. Local dictionary and category lookup runs simultaneously, so it cannot hold up that first model request. Passes two through five use the normal multi-answer format, incorporate the local hints, and exclude answers already found. A new prompt stops further passes for the previous prompt. Set `KRILLION_OLLAMA_PASSES` from `1` to `8` to change the limit.

While a round is active, the solver also compares its candidates with standalone answer rows visible on the game page. Answers that have already been said are removed from the list and excluded from later Ollama passes. This does not record them as wrong training feedback.

The already-said list resets when a new question is detected and whenever the monitored browser starts, stops, or restarts. Answers from an earlier round or game therefore do not carry into the next one.

Optional environment settings:

- `KRILLION_OLLAMA_TIMEOUT_SECONDS` changes the 60-second response timeout.
- `KRILLION_OLLAMA_KEEP_ALIVE` changes how long Ollama retains the model, such as `30m` or `0`.
- `KRILLION_OLLAMA_MODEL` selects a different local model tag.

## Feedback and training

Correct feedback is stored in `%LOCALAPPDATA%\KrillionSolver\training_examples.jsonl`. Wrong feedback is stored in `%LOCALAPPDATA%\KrillionSolver\rejected_answers.jsonl`. Clicking a feedback button records data for the next training run; it does not immediately change the loaded model.

Double-click **Train KrillionSolver.bat** to preview the training configuration and data. Type `TRAIN` when ready. If this computer does not have a compatible CUDA GPU, double-click **Prepare Colab Training.bat** and follow [training/README.md](training/README.md).

After exporting the trained model, create the local Ollama tag from the export directory:

```powershell
ollama create krillionsolver:8b -f Modelfile
```

The launcher will use that tag the next time it starts.

## Prompt detection

The browser monitor reads visible page text about once per second and looks for standalone questions and category instructions. **Diagnostics** shows the current URL, extracted text, selected prompt, detection method, and browser errors.

Detection may need adjustment if a game renders its prompt only in an image or canvas. If a live prompt is missed, open **Diagnostics** and provide the selected text and extracted page text.

## Troubleshooting

- **No answers appear:** confirm Ollama is running and that `krillionsolver:8b` or `llama3.1:latest` exists. Then press **Refresh Answer**.
- **Chromium does not launch:** run `.\.venv\Scripts\python.exe -m playwright install chromium` from the project folder.
- **The wrong text is detected:** enable **Diagnostics** and inspect the selected prompt.
- **The browser page is blank:** wait for navigation to finish or press **Restart**.
- **The first answer is slow:** the initial Ollama model load commonly takes longer. Later rounds are faster while the model remains loaded.

## Tests

Run the offline test suite from the project folder:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Project layout

```text
prompt_assistant.py
Run KrillionSolver.bat
requirements.txt
app/
  answer_lexicon.py
  background_worker.py
  browser_manager.py
  learned_answers.py
  ollama_provider.py
  prompt_constraints.py
  prompt_detector.py
  search_cache.py
  site_adapters.py
  ui.py
training/
  finetune_krillion.py
  trivia_data.jsonl
  KrillionSolver_Colab_Training.ipynb
tests/
```
