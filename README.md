# KrillionSolver

KrillionSolver is a Windows Tkinter companion that opens a visible Chromium browser, polls the selected game page about once per second, and searches the web with the free `ddgs` package when it detects a prompt. Its main view shows candidate answers with copy buttons; the Sources section expands to show titles, snippets, and links. Snippet-supported candidates are distinguished from title-only unverified suggestions. It never fills in or submits a game answer.

## Setup

The easiest way to start is to double-click **Run KrillionSolver.bat** in this folder. On first launch it creates a private `.venv`, installs the required packages and Chromium, then starts the app. Later launches start the app directly. It changes to the project folder automatically, so you do not need to run commands from `C:\Windows\System32`.

If you prefer PowerShell, open it in this project folder and run:

```powershell
.\Run KrillionSolver.bat
```

Tkinter comes with the standard Windows Python installer. If `tkinter` is missing, repair/reinstall Python with the Tcl/Tk option enabled.

## Use

1. Choose **Krillion** or **Puffer Party**. The defaults are `https://krillion.io/` and `https://krillion.io/party`.
2. Press **Start**. A visible Chromium window opens. Navigate and play there.
3. KrillionSolver polls readable page text every second. A detected prompt triggers a search if **Automatic search** is enabled.
4. Use **Refresh Answer** to ask Ollama again. **Clear Results** clears the displayed candidates and sources. Web search is currently skipped, so Sources will usually be empty.
5. **Restart** closes and reopens the monitored browser. **Always on top** is optional. **Diagnostics** shows the page text, selected prompt, detection method, current URL, and errors.

Answer generation runs off the Tkinter thread; outdated prompts are ignored, repeated prompt detections do not trigger duplicate requests, and identical concurrent requests are shared. Ollama streams suggestions into the answer list as complete candidates arrive, and the app does not wait for web search. Answers are labeled as unverified model suggestions; sources are empty because the result path skips DDGS. Use **Wrong** beside a candidate to save it as rejected, remove it, and immediately ask Ollama for alternatives that exclude it for the current prompt. Every rejection is used by the next fine-tuning run. When no confirmed replacement exists, training prefers `UNCERTAIN` over the rejected answer; when you add a correct answer, training prefers that correction. Ollama's default request timeout is 60 seconds (`KRILLION_OLLAMA_TIMEOUT_SECONDS` can override it). The app asks Ollama to keep the model loaded for 10 minutes after a request, avoiding reload delays between rounds (`KRILLION_OLLAMA_KEEP_ALIVE` can override this, for example `30m` or `0` to unload immediately). Keeping a model loaded uses memory while Ollama is idle.

Ollama is integrated as the primary answer generator. The launcher starts its local service if needed, then uses the fine-tuned `krillionsolver:8b` tag when installed or falls back to base `llama3.1:latest` (Llama 3.1 8B). If Ollama is unavailable or returns an unreadable answer, the app falls back to clearly labeled local dictionary/country suggestions. The default response timeout is 60 seconds (`KRILLION_OLLAMA_TIMEOUT_SECONDS` can override it). The app asks Ollama to keep the model loaded for 10 minutes after a request, avoiding reload delays between rounds (`KRILLION_OLLAMA_KEEP_ALIVE` can override this, for example `30m` or `0` to unload immediately). Keeping a model loaded uses memory while Ollama is idle. See [training/README.md](training/README.md) for how confirmed and rejected answers become fine-tuning examples and how to rebuild the Ollama model.

Click **Add to training data** to add a confirmed prompt/answer example to `%LOCALAPPDATA%\KrillionSolver\training_examples.jsonl`. This does not change model weights immediately. To train, use the separate training environment described in [training/README.md](training/README.md), then recreate the Ollama tag from the exported Modelfile. Fine-tuning needs at least 10 examples and can take substantial time and GPU memory. The trainer also imports the old `learned_answers.json` file if it exists; it leaves that file untouched.

Double-click **Train KrillionSolver.bat** for a complete preview of the model settings and data. It requires typing `TRAIN` before it starts the GPU training script.

### Running it as an overlay

For the simplest launch, double-click **Run KrillionSolver.bat**. It performs first-run setup automatically. Once setup has finished, you can also start the app from PowerShell in the project folder with:

```powershell
.\.venv\Scripts\python.exe prompt_assistant.py
```

In the app, choose the game and press **Start**. The app opens its own visible Chromium window; it does not attach to an existing browser tab. When the browser opens, KrillionSolver switches to a compact answer view. Use **Full view** to return to settings and source details. **Always on top** stays in the toolbar in both views. The results are shown in a separate desktop window, not a transparent in-game overlay. The app never types or submits answers.

The main candidates come directly from Ollama. For common constrained categories, the app provides local English dictionary and country-list examples as hints; it recognizes English word starts/ends/contains/compound patterns and country prompts about regions, flags, coastlines, and larger populations. Ollama suggestions are unverified and do not imply game acceptance. Use **Copy** beside a candidate to copy it.

## Game prompt detection status

I opened `https://krillion.io/` and `https://krillion.io/party` in Playwright Chromium and inspected their loaded DOM text. Krillion showed its Daily Dive lobby/depth screen with no active round question. Puffer Party showed its lobby, help text, and public room list, not an active room's category. I could not verify a selector against a live prompt for either mode, so the app does not claim a verified prompt selector. It scans readable body text for standalone question and category instruction patterns (such as “Name a…” and “What…”), filtering common navigation, timer, score, and button text as well as Puffer Party's visible “Name an answer and pass the puffer” instruction. This heuristic may miss prompts rendered only in canvas/images, hidden frames, or differently worded text; it needs tuning against an actual round.

To finish site-specific selector tuning, provide a live round page for each mode with a prompt visible (and, if possible, the relevant prompt element's **Copy selector** value from Chromium DevTools). In Puffer Party, that means a room after a category has appeared; for Krillion, a prompt after a dive begins. If the text is not available in the DOM, a screenshot and confirmation that it is rendered as an image/canvas are useful for deciding whether an optional OCR adapter is needed. Until then, enable **Diagnostics** and confirm that “Selected” matches the prompt before relying on automatic searches.

## Tests

Run the unit tests from the project folder:

```bash
py -m unittest discover -s tests -v
```

Tests mock the search service; running them does not make live search requests.

## Troubleshooting

- **Chromium does not launch:** from the project folder, run `.\\.venv\\Scripts\\python.exe -m playwright install chromium`.
- **Search errors / no search results:** check network connectivity, then use **Refresh Search**. The free search provider may rate-limit requests or fail to respond before the hard timeout; use **Refresh Search** to retry after the provider recovers.
- **Prompt is missed or unrelated text is selected:** enable **Diagnostics** and review extracted text, selected text, and the method. Send those details with the game mode and a live prompt so the matching adapter can be improved.
- **Page looks blank:** wait for the site to finish loading. The monitor uses visible Chromium and continues polling; navigation to another URL in that browser tab is monitored too.

## Project layout

```text
prompt_assistant.py
requirements.txt
app/
  browser_manager.py
  prompt_detector.py
  site_adapters.py
  search_provider.py
  ollama_provider.py
  answer_lexicon.py
  learned_answers.py           # saves confirmed examples for the next fine-tune
  search_cache.py
  background_worker.py
  ui.py
training/
  finetune_krillion.py
  trivia_data.jsonl
tests/
```
