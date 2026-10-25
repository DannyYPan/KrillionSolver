import queue
import threading
import time
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

    def test_failed_provider_is_cooled_down_until_manual_refresh(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        with patch("app.background_worker.search", side_effect=RuntimeError("rate limited")) as mock_search:
            worker.request("Name a river", 1)
            while True:
                _kind, payload = events.get(timeout=2)
                if payload.get("complete"):
                    break
            deadline = threading.Event()
            while "name a river" in worker._inflight:
                deadline.wait(0.005)

            worker.request("Name a river", 2)
            kind, retry = events.get(timeout=2)

        self.assertEqual(kind, "search")
        self.assertIn("use Refresh Search", retry["error"])
        self.assertEqual(mock_search.call_count, 3)

    def test_complementary_queries_run_concurrently_and_publish_stages(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        lock = threading.Lock()
        active = [0, 0]

        def fake_search(prompt, niche_level=0):
            with lock:
                active[0] += 1
                active[1] = max(active[1], active[0])
            time.sleep(0.03)
            with lock:
                active[0] -= 1
            return [{
                "title": f"Lake {niche_level} examples",
                "snippet": f"Examples include Lake {niche_level} Alpha and Lake {niche_level} Beta.",
                "url": f"https://source{niche_level}.example/lakes",
            }]

        with patch("app.background_worker.search", side_effect=fake_search):
            worker.request("Name a lake", 1)
            messages = []
            while not messages or not messages[-1][1].get("complete"):
                messages.append(events.get(timeout=2))

        self.assertGreaterEqual(active[1], 2)
        self.assertEqual({payload["stage"] for _kind, payload in messages}, {0, 1, 2})
        self.assertTrue(any(payload["candidates"] for _kind, payload in messages))

    def test_cached_result_is_reused(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        worker.cache.put("Name a river", [{"title": "Nile", "snippet": "", "url": ""}])
        with patch("app.background_worker.search", return_value=[]):
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
