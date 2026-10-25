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


if __name__ == "__main__":
    unittest.main()
