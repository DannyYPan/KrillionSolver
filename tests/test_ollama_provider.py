import unittest

from app.ollama_provider import parse_suggestions


class OllamaProviderTests(unittest.TestCase):
    def test_parses_safe_and_alternatives_and_deduplicates(self):
        results = parse_suggestions(
            "SAFE: Canada\nMORE OPTIONS: France, canada, Japan",
            "Name a country",
        )
        self.assertEqual([item["answer"] for item in results], ["Canada", "France", "Japan"])
        self.assertTrue(all("unverified" in item["evidence_status"] for item in results))

    def test_enforces_suffix_and_explicit_exclusion(self):
        results = parse_suggestions(
            "SAFE: prototype\nMORE OPTIONS: archetype, dog",
            "Name a word ending in -type — prototype doesn't count",
        )
        self.assertEqual([item["answer"] for item in results], ["archetype"])

    def test_does_not_parse_unstructured_hallucinated_output(self):
        self.assertEqual(parse_suggestions("Maybe Canada is valid.", "Name a country"), [])
        self.assertEqual(parse_suggestions("UNCERTAIN", "Name a country"), [])


if __name__ == "__main__":
    unittest.main()
