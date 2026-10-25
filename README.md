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
4. Use **Refresh Search** to search the current prompt again. **Clear Results** clears the displayed candidates and sources. Expand **Sources** to review page titles, snippets, and links.
5. **Restart** closes and reopens the monitored browser. **Always on top** is optional. **Diagnostics** shows the page text, selected prompt, detection method, current URL, and errors.

Searches run off the Tkinter thread; outdated prompt results are ignored, repeated prompt detections do not trigger new searches, and identical concurrent requests are shared. Three complementary DDGS queries run concurrently against the Bing backend with four results per query, a ten-second HTTP timeout, and a 30-second request limit. The client uses a certificate bundle rather than relying on the Windows user certificate store. Candidate names are extracted deterministically from titles and snippets, deduplicated, and ranked by snippet support from independent domains, query relevance, and broad-to-niche search stage. The cache stores successful pages and extracted candidates for 10 minutes. Defaults can be configured with `KRILLION_SEARCH_TIMEOUT_SECONDS`, `KRILLION_SEARCH_WALL_TIMEOUT_SECONDS`, `KRILLION_SEARCH_RESULTS_PER_QUERY`, and `KRILLION_DDGS_BACKEND`. Failed searches are not automatically retried; a 60-second cooldown prevents repeated automatic attempts, while **Refresh Search** retries immediately.

### Running it as an overlay

For the simplest launch, double-click **Run KrillionSolver.bat**. It performs first-run setup automatically. Once setup has finished, you can also start the app from PowerShell in the project folder with:

```powershell
.\.venv\Scripts\python.exe prompt_assistant.py
```

In the app, choose the game and press **Start**. The app opens its own visible Chromium window; it does not attach to an existing browser tab. When the browser opens, KrillionSolver switches to a compact answer view. Use **Full view** to return to settings and source details. Select **Always on top** in full view to keep the results window above the game. It is a separate desktop window, not a transparent in-game overlay. The app never types or submits answers.

Candidate names come from explicit lists or numbered entries in snippets and short entity-like headings in titles. A snippet-supported label means a source snippet contains the candidate; it does not verify game acceptance or rarity. Title-only suggestions are labeled unverified. Expand **Sources** for the titles, brief snippets, and links. Use **Copy** beside a candidate to copy it. If the available evidence does not identify a reliable answer, the app says so instead of inventing one.

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
  search_cache.py
  background_worker.py
  ui.py
tests/
```
