import queue
import threading
import unittest
from unittest.mock import patch

from app.background_worker import SearchWorker, result_is_current


def _candidate(answer):
    return {"answer": answer}


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

    def test_ollama_answers_are_emitted(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        with patch("app.background_worker.OLLAMA_MODEL", "test-model"), \
                patch("app.background_worker.suggest_with_ollama", return_value=[_candidate("Paris")]):
            worker.request("Name a city", 1)
            payload = _complete(events)

        self.assertEqual(payload["source"], "ollama")
        self.assertTrue(payload["complete"])
        self.assertEqual([item["answer"] for item in payload["candidates"]], ["Paris"])
        self.assertEqual(payload["results"], [])

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

        def delayed_suggest(prompt, hints=None, excluded_answers=None, on_update=None, fast=False):
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
        # Both listeners share one generation series. The second pass receives
        # Paris as an exclusion and stops when the mock adds nothing new.
        self.assertEqual(mock_ollama.call_count, 2)

    def test_later_passes_append_new_answers_and_exclude_existing_ones(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        returned = iter([[ _candidate("Paris")], [_candidate("Lyon")], []])

        with patch("app.background_worker.OLLAMA_MODEL", "test-model"), \
                patch("app.background_worker.suggest_with_ollama", side_effect=lambda *args, **kwargs: next(returned)) as mock_ollama:
            worker.request("Name a city", 1)
            payload = _complete(events)

        self.assertEqual([item["answer"] for item in payload["candidates"]], ["Paris", "Lyon"])
        self.assertEqual(mock_ollama.call_count, 3)
        self.assertTrue(mock_ollama.call_args_list[0].kwargs["fast"])
        self.assertFalse(mock_ollama.call_args_list[1].kwargs["fast"])
        self.assertIn("Paris", mock_ollama.call_args_list[1].kwargs["excluded_answers"])
        self.assertIn("Lyon", mock_ollama.call_args_list[2].kwargs["excluded_answers"])

    def test_disabled_ollama_uses_dictionary_fallback(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        with patch("app.background_worker.OLLAMA_MODEL", ""):
            worker.request("Name an English word", 1)
            payload = _complete(events)

        self.assertEqual(payload["source"], "local-fallback")
        self.assertTrue(payload["candidates"])
        self.assertIn("disabled", payload["error"])

    def test_live_page_answers_are_excluded_from_generation(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        worker.exclude("Name a city", ["Paris"])
        with patch("app.background_worker.OLLAMA_MODEL", "test-model"), \
                patch("app.background_worker.suggest_with_ollama", return_value=[]) as mock_ollama:
            worker.request("Name a city", 1)
            _complete(events)

        self.assertIn("paris", mock_ollama.call_args.kwargs["excluded_answers"])

    def test_new_game_resets_live_page_exclusions(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        worker.exclude("Name a city", ["Paris"])
        worker.reset_session()
        with patch("app.background_worker.OLLAMA_MODEL", "test-model"), \
                patch("app.background_worker.suggest_with_ollama", return_value=[]) as mock_ollama:
            worker.request("Name a city", 1)
            _complete(events)

        self.assertNotIn("paris", mock_ollama.call_args.kwargs["excluded_answers"])

    def test_first_ollama_pass_does_not_wait_for_local_lookup(self):
        events = queue.Queue()
        worker = SearchWorker(events)
        lexicon_started = threading.Event()
        release_lexicon = threading.Event()
        ollama_started = threading.Event()

        def slow_lexicon(*_args, **_kwargs):
            lexicon_started.set()
            release_lexicon.wait(timeout=2)
            return [_candidate("Turtle")]

        def quick_ollama(*_args, **kwargs):
            if kwargs.get("fast"):
                ollama_started.set()
                return [_candidate("Snail")]
            return []

        with patch("app.background_worker.OLLAMA_MODEL", "test-model"), \
                patch("app.background_worker.local_candidates", side_effect=slow_lexicon), \
                patch("app.background_worker.suggest_with_ollama", side_effect=quick_ollama):
            worker.request("Name an animal with a shell", 1)
            self.assertTrue(lexicon_started.wait(timeout=1))
            self.assertTrue(ollama_started.wait(timeout=1))
            release_lexicon.set()
            payload = _complete(events)

        self.assertEqual(payload["candidates"][0]["answer"], "Snail")


if __name__ == "__main__":
    unittest.main()
