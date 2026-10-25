import unittest

from app.search_cache import SearchCache


class SearchCacheTests(unittest.TestCase):
    def test_hit_and_expiration(self):
        now = [0.0]
        cache = SearchCache(10, clock=lambda: now[0])
        cache.put("Name a river", [{"title": "Nile"}])
        self.assertEqual(cache.get(" name A RIVER "), [{"title": "Nile"}])
        now[0] = 10.0
        self.assertIsNone(cache.get("Name a river"))

    def test_returns_copy(self):
        cache = SearchCache()
        cache.put("prompt", [{"title": "A"}])
        found = cache.get("prompt")
        found[0]["title"] = "changed"
        self.assertEqual(cache.get("prompt")[0]["title"], "A")

    def test_caches_and_copies_extracted_candidates(self):
        cache = SearchCache()
        candidates = [{"answer": "Lake Vostok", "sources": [{"url": "https://example.org"}]}]
        cache.put("Name a lake", [{"title": "Lakes"}], candidates)
        found = cache.get_candidates(" name a lake ")
        found[0]["sources"][0]["url"] = "changed"
        self.assertEqual(cache.get_candidates("Name a lake")[0]["sources"][0]["url"], "https://example.org")


if __name__ == "__main__":
    unittest.main()
