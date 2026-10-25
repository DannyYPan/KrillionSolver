"""Compact Tkinter interface for monitoring game prompts and search results."""

from __future__ import annotations

import queue
import tkinter as tk
import webbrowser
from tkinter import ttk

from .background_worker import SearchWorker, result_is_current
from .browser_manager import BrowserMonitor
from .prompt_detector import normalize_prompt
from .learned_answers import reject_answer, remember
from .site_adapters import ADAPTERS


class KrillionSolverApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("KrillionSolver")
        self.geometry("650x680")
        self.minsize(520, 460)
        self.compact = False
        self.events: queue.Queue = queue.Queue()
        self.search_worker = SearchWorker(self.events)
        self.monitor: BrowserMonitor | None = None
        self.current_prompt = ""
        self.request_id = 0
        self.sources_expanded = False
        self.source_count = 0
        self.auto_search = tk.BooleanVar(value=True)
        self.always_on_top = tk.BooleanVar(value=False)
        self.diagnostics = tk.BooleanVar(value=False)
        self.site = tk.StringVar(value="Krillion")
        self.url = tk.StringVar(value=ADAPTERS["Krillion"].default_url)
        self.browser_status = tk.StringVar(value="Stopped")
        self.search_status = tk.StringVar(value="Waiting for a prompt")
        self.prompt_var = tk.StringVar(value="No prompt detected yet")
        self.query_var = tk.StringVar(value="")
        self.learned_answer_var = tk.StringVar(value="")
        self.current_candidates: list[dict] = []
        self.rejected_answers: list[str] = []
        self._build()
        self.bind_all("<MouseWheel>", self._route_mousewheel, add="+")
        self.bind_all("<Button-4>", lambda event: self._route_scroll_button(event, -1), add="+")
        self.bind_all("<Button-5>", lambda event: self._route_scroll_button(event, 1), add="+")
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._poll_events)

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(6, weight=1)
        controls = ttk.Frame(self, padding=10)
        self.controls_frame = controls
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Game").grid(row=0, column=0, sticky="w")
        selector = ttk.Combobox(controls, textvariable=self.site, values=list(ADAPTERS), state="readonly", width=16)
        selector.grid(row=0, column=1, sticky="w", padx=(8, 16))
        selector.bind("<<ComboboxSelected>>", self._site_changed)
        ttk.Label(controls, text="URL").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(controls, textvariable=self.url).grid(row=1, column=1, columnspan=4, sticky="ew", padx=(8, 0), pady=(8, 0))
        buttons = ttk.Frame(controls)
        buttons.grid(row=2, column=0, columnspan=5, sticky="w", pady=(10, 0))
        ttk.Button(buttons, text="Start", command=self.start).pack(side="left")
        ttk.Button(buttons, text="Stop", command=self.stop).pack(side="left", padx=5)
        ttk.Button(buttons, text="Restart", command=self.restart).pack(side="left")
        ttk.Label(buttons, text="Browser:").pack(side="left", padx=(18, 4))
        ttk.Label(buttons, textvariable=self.browser_status).pack(side="left")

        options = ttk.Frame(self, padding=(10, 0, 10, 6))
        self.options_frame = options
        options.grid(row=1, column=0, sticky="ew")
        ttk.Checkbutton(options, text="Automatic search", variable=self.auto_search).pack(side="left")
        ttk.Checkbutton(options, text="Diagnostics", variable=self.diagnostics).pack(side="left")

        prompt = ttk.LabelFrame(self, text="Detected prompt", padding=8)
        prompt.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        prompt.columnconfigure(0, weight=1)
        self.prompt_label = ttk.Label(prompt, textvariable=self.prompt_var, wraplength=590, justify="left")
        self.prompt_label.grid(row=0, column=0, sticky="ew")
        self.query_label = ttk.Label(prompt, text="Search query")
        self.query_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.query_value = ttk.Label(prompt, textvariable=self.query_var, wraplength=590)
        self.query_value.grid(row=2, column=0, sticky="w")
        learn_row = ttk.Frame(prompt)
        learn_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        learn_row.columnconfigure(0, weight=1)
        ttk.Entry(learn_row, textvariable=self.learned_answer_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(learn_row, text="Add to training data", command=self._remember_answer).grid(row=0, column=1, padx=(6, 0))

        actions = ttk.Frame(self, padding=(10, 4))
        actions.grid(row=3, column=0, sticky="ew")
        ttk.Label(actions, textvariable=self.search_status).pack(side="left")
        ttk.Button(actions, text="Refresh Answer", command=self.refresh_search).pack(side="right")
        ttk.Button(actions, text="Clear Results", command=self.clear_results).pack(side="right", padx=6)
        self.view_button = ttk.Button(actions, text="Compact view", command=self._toggle_compact)
        self.view_button.pack(side="right", padx=6)
        ttk.Checkbutton(actions, text="Always on top", variable=self.always_on_top, command=self._top_changed).pack(side="right", padx=6)

        ideas_frame = ttk.LabelFrame(self, text="Answer ideas", padding=6)
        self.ideas_frame = ideas_frame
        ideas_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 6))
        ideas_frame.configure(height=195)
        ideas_frame.grid_propagate(False)
        ideas_frame.rowconfigure(0, weight=1)
        ideas_frame.columnconfigure(0, weight=1)
        self.ideas_canvas = tk.Canvas(ideas_frame, height=175, highlightthickness=0, yscrollincrement=24)
        ideas_scrollbar = ttk.Scrollbar(ideas_frame, orient="vertical", command=self.ideas_canvas.yview)
        self.ideas_canvas.configure(yscrollcommand=ideas_scrollbar.set)
        self.ideas_canvas.grid(row=0, column=0, sticky="nsew")
        ideas_scrollbar.grid(row=0, column=1, sticky="ns")
        self.ideas_inner = ttk.Frame(self.ideas_canvas)
        self.ideas_window = self.ideas_canvas.create_window((0, 0), window=self.ideas_inner, anchor="nw")
        self.ideas_inner.bind("<Configure>", lambda _e: self.ideas_canvas.configure(scrollregion=self.ideas_canvas.bbox("all")))
        self.ideas_canvas.bind("<Configure>", lambda e: self.ideas_canvas.itemconfigure(self.ideas_window, width=e.width))

        self.sources_toggle = ttk.Button(self, text="▶ Sources", command=self._toggle_sources)
        self.sources_toggle.grid(row=5, column=0, sticky="w", padx=12, pady=(0, 4))
        results_frame = ttk.LabelFrame(self, text="Search sources", padding=6)
        self.results_frame = results_frame
        results_frame.grid(row=6, column=0, sticky="nsew", padx=10, pady=(0, 6))
        results_frame.grid_remove()
        results_frame.rowconfigure(0, weight=1)
        results_frame.columnconfigure(0, weight=1)
        self.results_canvas = tk.Canvas(results_frame, highlightthickness=0, yscrollincrement=48)
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_canvas.yview)
        self.results_canvas.configure(yscrollcommand=scrollbar.set)
        self.results_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_inner = ttk.Frame(self.results_canvas)
        self.canvas_window = self.results_canvas.create_window((0, 0), window=self.results_inner, anchor="nw")
        self.results_inner.bind("<Configure>", lambda _e: self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all")))
        self.results_canvas.bind("<Configure>", lambda e: self.results_canvas.itemconfigure(self.canvas_window, width=e.width))

        self.diag_frame = ttk.LabelFrame(self, text="Detection diagnostics", padding=6)
        self.diag_text = tk.Text(self.diag_frame, height=8, wrap="word", state="disabled")
        self.diag_scroll = ttk.Scrollbar(self.diag_frame, orient="vertical", command=self.diag_text.yview)
        self.diag_text.configure(yscrollcommand=self.diag_scroll.set)
        self.diag_text.pack(side="left", fill="both", expand=True)
        self.diag_scroll.pack(side="right", fill="y")
        self.diagnostics.trace_add("write", lambda *_: self._show_diagnostics())

    def _toggle_compact(self) -> None:
        self._set_compact(not self.compact)

    def _toggle_sources(self) -> None:
        self.sources_expanded = not self.sources_expanded
        marker = "▼" if self.sources_expanded else "▶"
        self.sources_toggle.configure(text=f"{marker} Sources ({self.source_count})")
        if self.sources_expanded:
            self.results_frame.grid()
            self.rowconfigure(6, weight=1)
        else:
            self.results_frame.grid_remove()
            self.rowconfigure(6, weight=0)

    def _set_compact(self, enabled: bool) -> None:
        if self.compact == enabled:
            return
        self.compact = enabled
        if enabled:
            self.controls_frame.grid_remove()
            self.options_frame.grid_remove()
            self.query_label.grid_remove()
            self.query_value.grid_remove()
            self.sources_toggle.grid_remove()
            self.results_frame.grid_remove()
            self.diag_frame.grid_remove()
            self.rowconfigure(6, weight=0)
            self.rowconfigure(4, weight=1)
            self.ideas_frame.grid_configure(sticky="nsew")
            self.prompt_label.configure(wraplength=350)
            self.geometry("500x430")
            self.minsize(450, 350)
            self.view_button.configure(text="Full view")
        else:
            self.controls_frame.grid()
            self.options_frame.grid()
            self.query_label.grid()
            self.query_value.grid()
            self.sources_toggle.grid()
            if self.sources_expanded:
                self.results_frame.grid()
                self.rowconfigure(6, weight=1)
            self.rowconfigure(4, weight=0)
            self.ideas_frame.grid_configure(sticky="ew")
            self.prompt_label.configure(wraplength=590)
            self.geometry("650x680")
            self.minsize(520, 460)
            self.view_button.configure(text="Compact view")
            self._show_diagnostics()
        self.ideas_frame.configure(height=275 if enabled else 195)

    def _site_changed(self, _event=None) -> None:
        self.url.set(ADAPTERS[self.site.get()].default_url)
        if self.monitor and self.monitor.is_alive():
            self.restart()

    def _top_changed(self) -> None:
        self.attributes("-topmost", self.always_on_top.get())

    def _show_diagnostics(self) -> None:
        if self.diagnostics.get():
            self.diag_frame.grid(row=7, column=0, sticky="nsew", padx=10, pady=(0, 10))
            self.rowconfigure(7, weight=1)
        else:
            self.diag_frame.grid_remove()
            self.rowconfigure(7, weight=0)

    def start(self) -> None:
        if self.monitor and self.monitor.is_alive():
            return
        self.monitor = BrowserMonitor(self.site.get(), self.url.get().strip(), self.events)
        self.monitor.start()

    def stop(self) -> None:
        if self.monitor:
            self.monitor.stop()
            self.browser_status.set("Stopping…")

    def restart(self) -> None:
        self.stop()
        self.after(250, self._restart_when_stopped)

    def _restart_when_stopped(self) -> None:
        if self.monitor and self.monitor.is_alive():
            self.after(150, self._restart_when_stopped)
        else:
            self.start()

    def _new_prompt(self, prompt: str) -> None:
        if normalize_prompt(prompt) == normalize_prompt(self.current_prompt):
            return
        self.current_prompt = prompt
        self.current_candidates = []
        self.rejected_answers = []
        self.prompt_var.set(prompt)
        self.query_var.set(prompt.rstrip("?.! "))
        self.request_id += 1
        self.clear_results()
        if self.auto_search.get():
            self.search_worker.request(prompt, self.request_id)
            self.search_status.set("Asking Ollama…")

    def _remember_answer(self) -> None:
        answer = self.learned_answer_var.get()
        if not self.current_prompt:
            self.search_status.set("Wait for a prompt before saving an answer")
            return
        if not remember(self.current_prompt, answer):
            self.search_status.set("Enter an answer of 1 to 100 characters")
            return
        self.learned_answer_var.set("")
        if not any(item.get("answer", "").casefold() == answer.strip().casefold() for item in self.current_candidates):
            self.current_candidates.insert(0, {
                "answer": " ".join(answer.split()),
                "evidence": "Previously entered and confirmed by you for this prompt.",
                "evidence_status": "You confirmed this answer",
                "evidence_score": 0,
                "source_count": 0,
                "sources": [],
            })
        self._render_candidates(self.current_candidates, searching=self.search_status.get().startswith("Searching"))
        self.search_status.set("Added to training data · fine-tune Ollama to apply")

    def refresh_search(self) -> None:
        if not self.current_prompt:
            self.search_status.set("No prompt to search")
            return
        self.request_id += 1
        self.search_worker.request(
            self.current_prompt, self.request_id, force=True,
            excluded_answers=self.rejected_answers,
        )
        self.search_status.set("Asking Ollama again…")

    def _reject_answer(self, answer: str) -> None:
        if self.current_prompt and not reject_answer(self.current_prompt, answer):
            self.search_status.set("Could not save feedback for fine-tuning")
            return
        if not any(item.casefold() == answer.casefold() for item in self.rejected_answers):
            self.rejected_answers.append(answer)
        self.current_candidates = [
            item for item in self.current_candidates
            if item.get("answer", "").casefold() != answer.casefold()
        ]
        self._render_candidates(self.current_candidates, searching=True)
        if self.current_prompt:
            self.refresh_search()
            self.search_status.set(f"Marked {answer} wrong · saved for the next training run")

    def clear_results(self) -> None:
        for child in self.results_inner.winfo_children():
            child.destroy()
        for child in self.ideas_inner.winfo_children():
            child.destroy()
        self.source_count = 0
        marker = "▼" if self.sources_expanded else "▶"
        self.sources_toggle.configure(text=f"{marker} Sources (0)")

    def _render_candidates(self, candidates: list[dict], searching: bool = False) -> None:
        rejected = {answer.casefold() for answer in self.rejected_answers}
        candidates = [item for item in candidates if item.get("answer", "").casefold() not in rejected]
        self.current_candidates = list(candidates)
        for child in self.ideas_inner.winfo_children():
            child.destroy()
        if not candidates:
            message = "Waiting for Ollama's answer…" if searching else "No answer was returned. Check that Ollama is running and the configured model is installed."
            ttk.Label(self.ideas_inner, text=message).pack(anchor="w", padx=6, pady=6)
            return
        for number, candidate in enumerate(candidates, start=1):
            card = ttk.Frame(self.ideas_inner, padding=(6, 2))
            card.pack(fill="x", anchor="w")
            name = ttk.Label(card, text=f"{number}. {candidate['answer']}", font=("Segoe UI", 10, "bold"))
            name.pack(side="left", anchor="w")
            ttk.Button(card, text="Copy", command=lambda answer=candidate["answer"]: self._copy_answer(answer)).pack(side="right")
            ttk.Button(card, text="Wrong", command=lambda answer=candidate["answer"]: self._reject_answer(answer)).pack(side="right", padx=(0, 5))
            evidence = candidate.get("evidence_status", "Title only · unverified")
            source_count = candidate.get("source_count", 0)
            if evidence.startswith("Web mention found") and source_count:
                evidence += f" · {source_count} source{'s' if source_count != 1 else ''}"
            elif evidence == "Snippet-supported" and source_count:
                evidence = f"Snippet-supported · {source_count} independent source{'s' if source_count != 1 else ''}"
            ttk.Label(self.ideas_inner, text=evidence, foreground="#555").pack(anchor="w", padx=24)

    def _scroll_canvas_under_pointer(self, event) -> tk.Canvas | None:
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget is self.ideas_canvas or widget is self.results_canvas:
                return widget
            widget = getattr(widget, "master", None)
        return None

    def _route_mousewheel(self, event):
        canvas = self._scroll_canvas_under_pointer(event)
        if canvas is None:
            return None
        delta = getattr(event, "delta", 0)
        if delta:
            canvas.yview_scroll(-1 if delta > 0 else 1, "units")
            return "break"
        return None

    def _route_scroll_button(self, event, direction: int):
        canvas = self._scroll_canvas_under_pointer(event)
        if canvas is not None:
            canvas.yview_scroll(direction, "units")
            return "break"
        return None

    def _copy_answer(self, answer: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(answer)
        self.search_status.set("Answer copied")

    def _show_evidence(self, item: dict[str, str]) -> None:
        window = tk.Toplevel(self)
        window.title(item.get("answer") or item.get("title") or "Search evidence")
        window.geometry("520x260")
        window.transient(self)
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=item.get("answer") or item.get("title", "Source"), font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(body, text=item.get("evidence") or item.get("snippet") or "No snippet was provided.", wraplength=490, justify="left").pack(anchor="w", pady=12)
        if item.get("url"):
            ttk.Button(body, text="Open source", command=lambda: webbrowser.open(item["url"])).pack(anchor="w")

    def _render_sources(self, results: list[dict]) -> None:
        for child in self.results_inner.winfo_children():
            child.destroy()
        self.source_count = len(results)
        self.sources_toggle.configure(text=f"{'▼' if self.sources_expanded else '▶'} Sources ({self.source_count})")
        for result in results:
            card = ttk.Frame(self.results_inner, padding=8, relief="ridge")
            card.pack(fill="x", pady=4)
            title = ttk.Label(card, text=result["title"], font=("Segoe UI", 10, "bold"), wraplength=560, justify="left")
            title.pack(anchor="w")
            providers = result.get("search_providers") or ([result["search_provider"]] if result.get("search_provider") else [])
            if providers:
                ttk.Label(card, text=f"Found via {', '.join(providers)}", foreground="#555").pack(anchor="w")
            if result.get("snippet"):
                ttk.Label(card, text=result["snippet"], wraplength=560, justify="left").pack(anchor="w", pady=(3, 0))
            actions = ttk.Frame(card)
            actions.pack(fill="x", pady=(3, 0))
            if result["url"]:
                ttk.Button(actions, text="Open source", command=lambda url=result["url"]: webbrowser.open(url)).pack(side="left")
        if not results:
            ttk.Label(self.results_inner, text="No source pages returned.").pack(anchor="w", padx=8, pady=8)

    def _render_results(self, payload: dict) -> None:
        searching = not payload.get("complete", True)
        self._render_candidates(payload.get("candidates", []), searching=searching)
        self._render_sources(payload.get("results", []))
        error = payload.get("error")
        if searching:
            count = len(payload.get("candidates", []))
            status = f"Searching… · {count} candidates ready" if count else "Searching…"
            if error:
                status += " · one search unavailable"
            self.search_status.set(status)
        elif payload.get("source") == "ollama" and payload.get("candidates"):
            self.search_status.set("Ollama answer ready · web search skipped")
        elif payload.get("source") == "local-fallback" and payload.get("candidates"):
            self.search_status.set("Local dictionary suggestions · Ollama unavailable")
        elif error and not payload.get("results"):
            self.search_status.set(error)
        elif not payload.get("results"):
            self.search_status.set("No answer returned · check Ollama and its model")
        elif not payload.get("candidates"):
            self.search_status.set("Pages found · no reliable answer identified")
        else:
            self.search_status.set(f"Results ready · {len(payload['candidates'])} candidates · {len(payload['results'])} sources")

    def _poll_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "browser":
                    self.browser_status.set(value)
                    if str(value).startswith("Open"):
                        self._set_compact(True)
                    elif value in {"Stopped", "Closed"}:
                        self._set_compact(False)
                elif kind == "browser-error":
                    self.browser_status.set("Error")
                    self.search_status.set(f"Browser error: {value}")
                elif kind == "prompt":
                    self._new_prompt(value)
                elif kind == "diagnostic" and self.diagnostics.get():
                    self.diag_text.configure(state="normal")
                    self.diag_text.delete("1.0", "end")
                    self.diag_text.insert("1.0", f"URL: {value['url']}\nMethod: {value['method']}\nSelected: {value['prompt'] or '(none)'}\nError: {value['error'] or '(none)'}\n\nExtracted page text:\n{value['text']}")
                    self.diag_text.configure(state="disabled")
                elif kind == "search":
                    if result_is_current(value["request_id"], self.request_id, value["prompt"], self.current_prompt):
                        self.query_var.set(value["query"])
                        self._render_results(value)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll_events)

    def _close(self) -> None:
        self.stop()
        self.destroy()
