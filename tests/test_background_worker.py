import queue
import threading
import unittest
from unittest.mock import patch

from app.background_worker import SearchWorker, result_is_current


class BackgroundWorkerTests(unittest.TestCase):
    def test_stale_result_is_rejected(self):
        self.assertFalse(result_is_current(2, 3, "old prompt", "new prompt"))
        self.assertFalse(result_is_current(3, 3, "old prompt", "new prompt"))
        self.assertTrue(result_is_current(3, 3, "Current?", " current? "))

    def test_search_exception_is_delivered_as_error(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        with patch("app.background_worker.search", side_effect=RuntimeError("offline")):
            worker.request("Name a river", 1)
            kind, payload = events.get(timeout=2)
        self.assertEqual(kind, "search")
        self.assertEqual(payload["error"], "RuntimeError: offline")
        self.assertEqual(payload["results"], [])

    def test_cached_result_is_reused(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        worker.cache.put("Name a river", [{"title": "Nile", "snippet": "", "url": ""}])
        worker.request("Name a river", 7)
        _, payload = events.get(timeout=2)
        self.assertEqual(payload["source"], "cached")

    def test_concurrent_same_prompt_uses_one_search(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        entered, release = threading.Event(), threading.Event()
        calls = []
        def delayed(prompt):
            calls.append(prompt)
            entered.set()
            release.wait(timeout=2)
            return []
        with patch("app.background_worker.search", side_effect=delayed):
            worker.request("Name a river", 10)
            self.assertTrue(entered.wait(timeout=2))
            worker.request(" name a RIVER ", 11)
            release.set()
            messages = [events.get(timeout=2), events.get(timeout=2)]
        self.assertEqual(calls, ["Name a river"])
        self.assertEqual({payload["request_id"] for _kind, payload in messages}, {10, 11})


if __name__ == "__main__":
    unittest.main()
