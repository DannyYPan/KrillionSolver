"""Independent Playdaily browser and prompt detector.

This module intentionally does not call the Krillion/Puffer prompt detector.  A
Playdaily markup change therefore cannot change either existing game path.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import queue
import re
import threading
from pathlib import Path
from typing import Any

from .browser_manager import extract_accepted_text, extract_editable_values, extract_rejected_text
from .prompt_detector import normalize_prompt


PLAYDAILY_URL = "https://playdaily.org/krillion"
PROMPT_SELECTOR = (
    "[data-testid*='prompt' i], [data-testid*='question' i], "
    "[aria-label*='prompt' i], [aria-label*='question' i], "
    "[class*='prompt' i], [class*='question' i], [aria-live]"
)

_STARTS_PROMPT = re.compile(
    r"^(?:name|give|list|think of|what|which|who|where|how|find|say|enter|type|identify|choose)\b",
    re.IGNORECASE,
)
_NOISE = re.compile(
    r"^(?:play daily|krillion|home|games?|privacy|terms|share|sign in|log in|"
    r"say the obvious answer,? then bin it[.!]?|\d{1,2}:\d{2}|\d+\s*seconds?)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PlaydailyDetection:
    prompt: str | None
    method: str
    extracted_text: str
    error: str | None = None


def detect_playdaily_text(text: str, *, method: str = "playdaily-text") -> PlaydailyDetection:
    """Find a short game prompt using rules owned only by Playdaily."""
    lines = [re.sub(r"\s+", " ", line).strip(" \t|•") for line in str(text or "").splitlines()]
    lines = [line for line in lines if line and not _NOISE.fullmatch(line)]
    candidates: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        clean = re.sub(r"^(?:question|prompt|category)\s*(?:#\s*\d+)?\s*[:\-]\s*", "", line, flags=re.I)
        clean = re.sub(r"^#\s*\d+\s*[:.\-]?\s*", "", clean).strip()
        if not (5 <= len(clean) <= 240) or _NOISE.fullmatch(clean):
            continue
        score = 0
        if _STARTS_PROMPT.match(clean):
            score += 8
        if clean.endswith("?"):
            score += 3
        if re.search(r"\b(?:word|country|animal|character|show|movie|song|food|ends? with|contains?|syllables?)\b", clean, re.I):
            score += 2
        if re.match(r"^(?:question|prompt|category)\b", line, re.I):
            score += 4
        if score >= 4:
            # Playdaily sometimes renders a qualifier on the immediately following line.
            if index + 1 < len(lines):
                following = lines[index + 1]
                if (len(following) <= 100 and re.match(
                    r"^(?:starting|beginning|ending|containing|with|without|that|it must|do not|doesn't|does not)\b",
                    following, re.I,
                )):
                    clean = f"{clean} {following}"
            candidates.append((score, index, clean))
    if not candidates:
        return PlaydailyDetection(None, method, str(text or ""), "No Playdaily prompt found")
    return PlaydailyDetection(max(candidates)[2], method, str(text or ""))


def read_playdaily_prompt(page: Any, body_text: str) -> PlaydailyDetection:
    """Prefer dedicated prompt elements, falling back to Playdaily page text."""
    try:
        selected = page.locator(PROMPT_SELECTOR).all_inner_texts()
        selected_text = "\n".join(str(item) for item in selected if str(item).strip())
        detection = detect_playdaily_text(selected_text, method="playdaily-prompt-elements")
        if detection.prompt:
            return detection
    except Exception:
        pass
    return detect_playdaily_text(body_text, method="playdaily-body-fallback")


class PlaydailyMonitor(threading.Thread):
    """Browser worker dedicated to Playdaily; it shares only the event format."""

    def __init__(self, events: queue.Queue, interval: float = 0.6) -> None:
        super().__init__(name="playdaily-browser-monitor", daemon=True)
        self.events, self.interval = events, interval
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            from playwright.sync_api import Error as PlaywrightError, sync_playwright

            self.events.put(("browser", "Starting Playdaily…"))
            with sync_playwright() as playwright:
                local_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
                profile = local_data / "KrillionSolver" / "playdaily-browser-profile"
                profile.mkdir(parents=True, exist_ok=True)
                browser = playwright.chromium.launch_persistent_context(str(profile), headless=False)
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.set_default_timeout(2500)
                page.goto(PLAYDAILY_URL, wait_until="domcontentloaded", timeout=30000)
                self.events.put(("browser", f"Open · {page.url}"))
                last_normalized = None
                while not self._stop_event.is_set():
                    try:
                        body = page.locator("body").inner_text(timeout=2500)
                        detection = read_playdaily_prompt(page, body)
                        self.events.put(("diagnostic", {
                            "text": detection.extracted_text,
                            "accepted_text": extract_accepted_text(page),
                            "rejected_text": extract_rejected_text(page),
                            "editable_values": extract_editable_values(page),
                            "prompt": detection.prompt,
                            "method": detection.method,
                            "error": detection.error,
                            "url": page.url,
                        }))
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
