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
        self.assertEqual(make_query("Name a river?"), "examples of rivers")
        self.assertEqual(fake.query, "examples of rivers")
        self.assertEqual(make_query("Name a car brand?"), "examples of car brands")
        self.assertEqual(init_kwargs["timeout"], 10)
        self.assertTrue(init_kwargs["verify"].endswith("cacert.pem"))
        self.assertEqual(fake.kwargs, {"region": "us-en", "max_results": 4, "backend": "bing"})
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
            {"title": "Lesser-known lakes", "snippet": "Lesser-known lakes include Lake Vostok and Lake Nyos.", "url": "https://example.org/niche", "search_stage": "2"},
        ])
        self.assertEqual(result[0]["answer"], "Lake Erie")
        self.assertEqual(result[2]["answer"], "Lake Vostok")

    def test_candidates_rank_by_independent_evidence_and_label_title_only(self):
        results = extract_candidates([
            {"title": "Common lakes", "snippet": "Examples include Lake Erie and Lake Ontario.", "url": "https://common.example/a", "search_stage": "0"},
            {"title": "Rare lake examples", "snippet": "Examples include Lake Vostok and Lake Nyos.", "url": "https://source-one.example/a", "search_stage": "1"},
            {"title": "Lake Vostok", "snippet": "Other unusual lakes include Lake Vostok.", "url": "https://source-two.example/a", "search_stage": "2"},
            {"title": "Socotra Island — Travel magazine", "snippet": "An isolated island in the Indian Ocean.", "url": "https://travel.example/a", "search_stage": "1"},
        ], prompt="Name a lake")

        self.assertEqual(results[0]["answer"], "Lake Vostok")
        self.assertEqual(results[0]["source_count"], 2)
        title_only = next(item for item in results if item["answer"] == "Socotra Island")
        self.assertEqual(title_only["evidence_status"], "Title only · unverified")
        self.assertEqual(title_only["source_count"], 0)

    def test_evidence_points_follow_title_snippet_independence_and_category_signals(self):
        result = extract_candidates([
            {"title": "Lake Vostok: rare lake", "snippet": "Examples include Lake Vostok.", "url": "https://one.example/a"},
            {"title": "Antarctic lakes", "snippet": "Other lakes include Lake Vostok.", "url": "https://two.example/a"},
            {"title": "Travel guide to remote destinations", "snippet": "Visit this remote destination.", "url": "https://irrelevant.example/a"},
        ], prompt="Name a lake")
        candidate = next(item for item in result if item["answer"] == "Lake Vostok")
        # Title +3, snippets +4, extra independent source +2, category +3.
        self.assertEqual(candidate["evidence_score"], 12)

    def test_deduplicates_answer_case_and_spacing_variants(self):
        result = extract_candidates([
            {"title": "Popular dog breeds", "snippet": "Examples include Golden retrievers.", "url": "https://one.example/a"},
            {"title": "Dog breeds", "snippet": "Other examples include golden  retrievers.", "url": "https://two.example/a"},
        ], prompt="Name a dog breed")
        matches = [item for item in result if item["answer"].casefold().replace("  ", " ") == "golden retrievers"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["source_count"], 2)

    def test_title_candidate_is_never_marked_as_verified(self):
        result = extract_candidates([{
            "title": "Socotra Island — Travel magazine",
            "snippet": "An isolated island in the Indian Ocean.",
            "url": "https://travel.example/socotra",
        }], prompt="Name an island")
        self.assertEqual(result[0]["answer"], "Socotra Island")
        self.assertEqual(result[0]["evidence_status"], "Title only · unverified")

    def test_extracts_entities_from_a_colon_list_in_a_snippet(self):
        result = extract_candidates([{
            "title": "List of islands in the Pacific Ocean - Wikipedia",
            "snippet": "The islands are categorized into three major island groups: Melanesia, Micronesia, and Polynesia.",
            "url": "https://example.org/islands",
        }], prompt="Name an island group in the Pacific")
        self.assertEqual([item["answer"] for item in result], ["Melanesia", "Micronesia", "Polynesia"])
        self.assertTrue(all(item["evidence_status"] == "Snippet-supported" for item in result))
        self.assertTrue(all("confidence" not in item for item in result))

    def test_extracts_a_candidate_from_a_relevant_type_definition(self):
        result = extract_candidates([{
            "title": "About beagles",
            "snippet": "A beagle is a type of dog known for its sense of smell.",
            "url": "https://dogs.example/beagle",
        }], prompt="Name a dog breed")
        self.assertTrue(any(item["answer"].casefold() == "beagle" for item in result))

    def test_does_not_mistake_groups_for_individual_islands(self):
        result = extract_candidates([{
            "title": "List of islands in the Pacific Ocean - Wikipedia",
            "snippet": "The islands are categorized into three major island groups: Melanesia, Micronesia, and Polynesia.",
            "url": "https://example.org/islands",
        }], prompt="Name an island in the Pacific")
        self.assertEqual(result, [])

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
