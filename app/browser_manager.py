"""Playwright browser monitor. This worker never touches Tkinter widgets."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from .prompt_detector import detect_prompt
from .site_adapters import ADAPTERS


_ACCEPTED_TEXT_SCRIPT = r"""
() => {
  const blocked = 'input, textarea, select, form, [contenteditable="true"], [role="textbox"]';
  const selectors = [
    '[data-answer]', '[data-testid*="answer" i]', '[data-testid*="result" i]',
    '[class*="accepted" i]', '[class*="correct" i]', '[class*="answer" i]',
    '[class*="result" i]', '[id*="accepted" i]', '[id*="answer" i]',
    '[aria-label*="accepted" i]', '[aria-label*="correct" i]'
  ];
  const nodes = new Set(document.querySelectorAll(selectors.join(',')));
  document.querySelectorAll('body *').forEach((node) => {
    const text = (node.innerText || '').trim();
    if (text && text.length <= 160 &&
        /(?:\bcorrect\b|\baccepted\b|[+]?\d+\s*(?:points?|pts?)\b|✓)/i.test(text)) {
      nodes.add(node);
    }
  });
  return [...nodes]
    .filter((node) => !node.matches(blocked) && !node.closest(blocked) && !node.querySelector(blocked))
    .map((node) => (node.innerText || node.textContent || '').trim())
    .filter((text) => text && text.length <= 500)
    .join('\n');
}
"""


def extract_accepted_text(page: Any) -> str:
    """Read only DOM regions that look like submitted/accepted answer rows."""
    try:
        return str(page.evaluate(_ACCEPTED_TEXT_SCRIPT) or "")
    except (AttributeError, TypeError, ValueError):
        return ""


def extract_editable_values(page: Any) -> list[str]:
    """Return live typed values so they cannot be mistaken for submissions."""
    try:
        values = page.evaluate(r"""
        () => [...document.querySelectorAll(
          'input, textarea, [contenteditable="true"], [role="textbox"]'
        )].map((node) => (node.value || node.innerText || node.textContent || '').trim())
          .filter(Boolean)
        """)
        return [str(value) for value in (values or []) if str(value).strip()]
    except (AttributeError, TypeError, ValueError):
        return []


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
                        accepted_text = extract_accepted_text(page)
                        editable_values = extract_editable_values(page)
                        detection = detect_prompt(extracted, adapter.key)
                        self.events.put(("diagnostic", {
                            "text": detection.extracted_text,
                            "accepted_text": accepted_text,
                            "editable_values": editable_values,
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
