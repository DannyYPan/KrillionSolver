import queue
import sys
import types
import unittest
from unittest.mock import patch

from app.browser_manager import BrowserMonitor


class _FakePage:
    url = "https://krillion.io/"
    def __init__(self):
        self.closed = False
    def set_default_timeout(self, _timeout): pass
    def goto(self, *_args, **_kwargs): pass
    def locator(self, _selector):
        return types.SimpleNamespace(inner_text=lambda **_kwargs: "Name an island in the Pacific")
    def is_closed(self): return self.closed


class BrowserMonitorTests(unittest.TestCase):
    def test_monitor_stops_and_closes_browser(self):
        page = _FakePage()
        closed = []
        browser = types.SimpleNamespace(new_page=lambda: page, close=lambda: closed.append(True))
        chromium = types.SimpleNamespace(launch=lambda **_kwargs: browser)
        class PlaywrightContext:
            def __init__(self): self.chromium = chromium
            def __enter__(self): return self
            def __exit__(self, *_args): pass
        fake_module = types.SimpleNamespace(
            Error=type("PlaywrightError", (Exception,), {}),
            sync_playwright=lambda: PlaywrightContext(),
        )
        events = queue.Queue()
        with patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.sync_api": fake_module}):
            monitor = BrowserMonitor("Krillion", "https://krillion.io/", events, interval=0.01)
            monitor.start()
            # A monitor loop event confirms body extraction succeeded; stop it safely.
            while True:
                kind, _value = events.get(timeout=2)
                if kind == "diagnostic":
                    monitor.stop()
                    break
            monitor.join(timeout=2)
        self.assertFalse(monitor.is_alive())
        self.assertEqual(closed, [True])


if __name__ == "__main__":
    unittest.main()
