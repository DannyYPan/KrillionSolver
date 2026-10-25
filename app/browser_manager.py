"""Playwright browser monitor. This worker never touches Tkinter widgets."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from .prompt_detector import detect_prompt
from .site_adapters import ADAPTERS


class BrowserMonitor(threading.Thread):
    def __init__(self, site: str, url: str, events: queue.Queue, interval: float = 1.0) -> None:
        super().__init__(name="browser-monitor", daemon=True)
        self.site, self.url, self.events, self.interval = site, url, events, interval
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            from playwright.sync_api import Error as PlaywrightError, sync_playwright

            adapter = ADAPTERS[self.site]
            self.events.put(("browser", "Starting Chromium…"))
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=False)
                page = browser.new_page()
                page.set_default_timeout(2500)
                page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
                self.events.put(("browser", f"Open · {page.url}"))
                last_normalized = None
                while not self._stop_event.is_set():
                    try:
                        extracted = page.locator("body").inner_text(timeout=2500)
                        detection = detect_prompt(extracted, adapter.key)
                        self.events.put(("diagnostic", {
                            "text": detection.extracted_text,
                            "prompt": detection.prompt,
                            "method": detection.method,
                            "error": detection.error,
                            "url": page.url,
                        }))
                        from .prompt_detector import normalize_prompt
                        current = normalize_prompt(detection.prompt) if detection.prompt else None
                        if current and current != last_normalized:
                            last_normalized = current
                            self.events.put(("prompt", detection.prompt))
                    except PlaywrightError as exc:
                        if page.is_closed():
                            break
                        self.events.put(("browser-error", str(exc)))
                    self._stop_event.wait(self.interval)
                try:
                    browser.close()
                except PlaywrightError:
                    pass
            self.events.put(("browser", "Stopped"))
        except Exception as exc:
            self.events.put(("browser-error", f"{type(exc).__name__}: {exc}"))
            self.events.put(("browser", "Closed"))
