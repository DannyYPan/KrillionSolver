import queue
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from app.browser_manager import BrowserMonitor, extract_accepted_text


class _FakePage:
    def __init__(self):
        self.url = ""
        self.closed = False
    def set_default_timeout(self, _timeout):
        pass
    def goto(self, url, **_kwargs):
        self.url = url
    def locator(self, _selector):
        return types.SimpleNamespace(inner_text=lambda **_kwargs: "Name an island in the Pacific")
    def evaluate(self, _script):
        if "input, textarea, [contenteditable" in _script:
            return []
        return "Alice: Fiji +60 points"
    def is_closed(self): return self.closed


class BrowserMonitorTests(unittest.TestCase):
    def test_both_game_adapters_open_detect_and_close(self):
        for site, url in (
            ("Krillion", "https://krillion.io/"),
            ("Puffer Party", "https://krillion.io/party"),
        ):
            with self.subTest(site=site):
                page = _FakePage()
                closed = []
                browser = types.SimpleNamespace(
                    pages=[page],
                    new_page=lambda: page,
                    close=lambda: closed.append(True),
                )
                chromium = types.SimpleNamespace(
                    launch_persistent_context=lambda *_args, **_kwargs: browser
                )

                class PlaywrightContext:
                    def __init__(self):
                        self.chromium = chromium
                    def __enter__(self):
                        return self
                    def __exit__(self, *_args):
                        pass

                fake_module = types.SimpleNamespace(
                    Error=type("PlaywrightError", (Exception,), {}),
                    sync_playwright=lambda: PlaywrightContext(),
                )
                events = queue.Queue()
                with tempfile.TemporaryDirectory() as local_data, \
                     patch.dict(os.environ, {"LOCALAPPDATA": local_data}), \
                     patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.sync_api": fake_module}):
                    monitor = BrowserMonitor(site, url, events, interval=0.01)
                    monitor.start()
                    observed = []
                    while True:
                        kind, value = events.get(timeout=2)
                        observed.append((kind, value))
                        if kind == "diagnostic":
                            monitor.stop()
                        if kind == "browser" and value == "Stopped":
                            break
                    monitor.join(timeout=2)
                self.assertFalse(monitor.is_alive())
                self.assertEqual(closed, [True])
                self.assertIn(("browser", f"Open · {url}"), observed)
                self.assertIn(("prompt", "Name an island in the Pacific"), observed)
                diagnostic = next(value for kind, value in observed if kind == "diagnostic")
                self.assertEqual(diagnostic["accepted_text"], "Alice: Fiji +60 points")

    def test_accepted_text_gracefully_requires_dom_support(self):
        self.assertEqual(extract_accepted_text(object()), "")


if __name__ == "__main__":
    unittest.main()
