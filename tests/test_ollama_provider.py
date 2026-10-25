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

    def test_accepts_short_direct_answer_when_model_omits_labels(self):
        results = parse_suggestions("Paris", "Name a city")
        self.assertEqual([item["answer"] for item in results], ["Paris"])
        self.assertEqual(results[0]["evidence_status"], "Local model suggestion · unverified")

    def test_accepts_answer_prefix_when_model_omits_safe_label(self):
        results = parse_suggestions("The answer is: Paris.", "Name a city")
        self.assertEqual([item["answer"] for item in results], ["Paris"])


if __name__ == "__main__":
    unittest.main()
