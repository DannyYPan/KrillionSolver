import queue
import threading
import unittest
from unittest.mock import patch

from app.background_worker import SearchWorker, result_is_current


def _candidate(answer):
    return {
        "answer": answer,
        "evidence": "Suggested by local Ollama.",
        "title": "Local Ollama suggestion",
        "url": "",
        "sources": [],
        "evidence_status": "Local model suggestion · unverified",
        "evidence_score": 0,
        "source_count": 0,
    }


def _complete(events, request_id=1):
    while True:
        kind, payload = events.get(timeout=3)
        if kind == "search" and payload["request_id"] == request_id and payload.get("complete"):
            return payload


class BackgroundWorkerTests(unittest.TestCase):
    def test_stale_result_is_rejected(self):
        self.assertFalse(result_is_current(2, 3, "old prompt", "new prompt"))
        self.assertFalse(result_is_current(3, 3, "old prompt", "new prompt"))
        self.assertTrue(result_is_current(3, 3, "Current?", " current? "))

    def test_ollama_answers_are_emitted_without_waiting_for_web_search(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        with patch("app.background_worker.OLLAMA_MODEL", "test-model"), \
                patch("app.background_worker.suggest_with_ollama", return_value=[_candidate("Paris")]), \
                patch("app.search_provider.search") as mock_search:
            worker.request("Name a city", 1)
            payload = _complete(events)

        self.assertEqual(payload["source"], "ollama")
        self.assertTrue(payload["complete"])
        self.assertEqual([item["answer"] for item in payload["candidates"]], ["Paris"])
        self.assertEqual(payload["results"], [])
        mock_search.assert_not_called()

    def test_unavailable_ollama_returns_dictionary_fallback_instead_of_crashing(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        with patch("app.background_worker.OLLAMA_MODEL", "test-model"), \
                patch("app.background_worker.suggest_with_ollama", side_effect=RuntimeError("offline")):
            worker.request("Name an English word", 1)
            payload = _complete(events)

        self.assertEqual(payload["source"], "local-fallback")
        self.assertTrue(payload["candidates"])
        self.assertIn("Ollama unavailable", payload["error"])

    def test_cache_reuses_a_model_answer(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        answer = _candidate("Paris")
        worker.cache.put("Name a city", [], [answer])
        with patch("app.background_worker.OLLAMA_MODEL", "test-model"), \
                patch("app.background_worker.suggest_with_ollama") as mock_ollama:
            worker.request("Name a city", 7)
            payload = _complete(events, 7)

        self.assertEqual(payload["source"], "cached")
        self.assertEqual(payload["candidates"][0]["answer"], "Paris")
        mock_ollama.assert_not_called()

    def test_identical_concurrent_prompt_shares_one_ollama_request(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        entered = threading.Event()
        release = threading.Event()

        def delayed_suggest(prompt, hints=None):
            entered.set()
            release.wait(timeout=2)
            return [_candidate("Paris")]

        with patch("app.background_worker.OLLAMA_MODEL", "test-model"), \
                patch("app.background_worker.suggest_with_ollama", side_effect=delayed_suggest) as mock_ollama:
            worker.request("Name a city", 10)
            self.assertTrue(entered.wait(timeout=2))
            worker.request(" name a CITY ", 11)
            release.set()
            results = {}
            while len(results) < 2:
                kind, payload = events.get(timeout=3)
                if kind == "search" and payload.get("complete"):
                    results[payload["request_id"]] = payload

        self.assertEqual(set(results), {10, 11})
        self.assertEqual(mock_ollama.call_count, 1)

    def test_disabled_ollama_uses_dictionary_fallback(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        with patch("app.background_worker.OLLAMA_MODEL", ""):
            worker.request("Name an English word", 1)
            payload = _complete(events)

        self.assertEqual(payload["source"], "local-fallback")
        self.assertTrue(payload["candidates"])
        self.assertIn("disabled", payload["error"])


if __name__ == "__main__":
    unittest.main()
