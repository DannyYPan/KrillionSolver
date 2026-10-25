import sys
import types
import unittest
from unittest.mock import patch

from app.search_provider import extract_candidates, make_query, search


class SearchProviderTests(unittest.TestCase):
    def test_maps_ddgs_fields(self):
        class FakeDDGS:
            def text(self, query, **kwargs):
                self.query, self.kwargs = query, kwargs
                return [{"title": "A", "body": "A snippet", "href": "https://example.org"}]
        fake = FakeDDGS()
        init_kwargs = {}
        def create_ddgs(**kwargs):
            init_kwargs.update(kwargs)
            return fake
        with patch.dict(sys.modules, {"ddgs": types.SimpleNamespace(DDGS=create_ddgs)}):
            result = search("Name a river?")
        self.assertEqual(make_query("Name a river?"), "examples of river")
        self.assertEqual(fake.query, "examples of river")
        self.assertEqual(init_kwargs, {"timeout": 2})
        self.assertEqual(fake.kwargs, {"region": "us-en", "max_results": 5, "backend": "auto"})
        self.assertEqual(result[0], {"title": "A", "snippet": "A snippet", "url": "https://example.org"})

    def test_extracts_only_snippet_supported_candidates(self):
        result = extract_candidates([{
            "title": "Lesser-known lakes of the world",
            "snippet": "Some lesser-known lakes, including Lake Vostok, Lake Baikal, and Lake Tanganyika are especially remote.",
            "url": "https://example.org/lakes",
        }])
        self.assertEqual([item["answer"] for item in result], ["Lake Vostok", "Lake Baikal", "Lake Tanganyika"])
        self.assertTrue(all(item["url"] == "https://example.org/lakes" for item in result))
        self.assertTrue(all("including Lake Vostok" in item["evidence"] for item in result))

    def test_does_not_guess_candidate_without_explicit_support(self):
        result = extract_candidates([{
            "title": "List of rare rivers",
            "snippet": "A guide to remote waterways around the world.",
            "url": "https://example.org",
        }])
        self.assertEqual(result, [])

    def test_never_uses_site_title_as_answer(self):
        result = extract_candidates([{
            "title": "ExampleLake.org - List of rare lakes",
            "snippet": "ExampleLake.org has a full guide to lakes around the world.",
            "url": "https://examplelake.org",
        }])
        self.assertEqual(result, [])

    def test_extracts_answer_from_source_numbered_list(self):
        result = extract_candidates([{
            "title": "Rivers most travelers never hear about - Example Travel",
            "snippet": "Here are four examples of hidden rivers. 1. Yarlung Tsangpo Photo: Boqiang Liao, Wikimedia. 2. Rio Ca\u00f1o Cristales winds through Colombia.",
            "url": "https://example.org/rivers",
        }])
        self.assertEqual([item["answer"] for item in result], ["Yarlung Tsangpo", "Rio Ca\u00f1o Cristales"])

    def test_broad_examples_precede_more_obscure_examples(self):
        result = extract_candidates([
            {"title": "Lakes", "snippet": "Examples include Lake Erie and Lake Ontario.", "url": "https://example.org/common"},
            {"title": "Lesser-known lakes", "snippet": "Lesser-known lakes include Lake Vostok and Lake Nyos.", "url": "https://example.org/niche"},
        ])
        self.assertEqual(result[0]["answer"], "Lake Erie")
        self.assertEqual(result[2]["answer"], "Lake Vostok")

    def test_empty_results_and_errors(self):
        class EmptyDDGS:
            def text(self, *_args, **_kwargs): return []
        with patch.dict(sys.modules, {"ddgs": types.SimpleNamespace(DDGS=lambda **_kwargs: EmptyDDGS())}):
            self.assertEqual(search("question"), [])
        class BrokenDDGS:
            def text(self, *_args, **_kwargs): raise RuntimeError("offline")
        with patch.dict(sys.modules, {"ddgs": types.SimpleNamespace(DDGS=lambda **_kwargs: BrokenDDGS())}):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                search("question")


if __name__ == "__main__":
    unittest.main()
