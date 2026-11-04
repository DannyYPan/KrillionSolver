import unittest

from app.ollama_provider import parse_suggestions


class OllamaProviderTests(unittest.TestCase):
    def test_parses_safe_and_alternatives_and_deduplicates(self):
        results = parse_suggestions(
            "SAFE: Canada\nMORE OPTIONS: France, canada, Japan",
            "Name a country",
        )
        self.assertEqual([item["answer"] for item in results], ["Canada", "France", "Japan"])
        self.assertTrue(all(set(item) == {"answer"} for item in results))

    def test_enforces_suffix_and_explicit_exclusion(self):
        results = parse_suggestions(
            "SAFE: prototype\nMORE OPTIONS: archetype, dog",
            "Name a word ending in -type — prototype doesn't count",
        )
        self.assertEqual([item["answer"] for item in results], ["archetype"])

    def test_fast_pass_rejects_fragments_and_page_title_text(self):
        prompt = "Name an animal with a shell"
        self.assertEqual(parse_suggestions("SAFE: ab", prompt, check_local=False), [])
        self.assertEqual(parse_suggestions("SAFE: Top listeners this month", prompt, check_local=False), [])
        self.assertEqual(parse_suggestions("SAFE: What", prompt, check_local=False), [])
        self.assertEqual(
            [item["answer"] for item in parse_suggestions("SAFE: Turtle", prompt, check_local=False)],
            ["Turtle"],
        )
        self.assertEqual(
            parse_suggestions(
                "SAFE: goblin", "Name an English word ending in “-ling”", check_local=False,
            ),
            [],
        )

    def test_checked_later_pass_keeps_plausible_unknown_and_short_titles(self):
        shell = parse_suggestions("SAFE: Scaphopod", "Name an animal with a shell", check_local=True)
        movie = parse_suggestions("SAFE: Up", "Name an animated movie", check_local=True)
        self.assertEqual([item["answer"] for item in shell], ["Scaphopod"])
        self.assertEqual([item["answer"] for item in movie], ["Up"])

    def test_lexicon_puts_an_unknown_matching_word_after_a_confirmed_word(self):
        results = parse_suggestions(
            "SAFE: nonsensextype\nMORE OPTIONS: archetype",
            "Name an English word ending in -type",
        )
        self.assertEqual([item["answer"] for item in results], ["archetype", "nonsensextype"])

    def test_does_not_parse_unstructured_hallucinated_output(self):
        self.assertEqual(parse_suggestions("Maybe Canada is valid.", "Name a country"), [])
        self.assertEqual(parse_suggestions("UNCERTAIN", "Name a country"), [])

    def test_accepts_short_direct_answer_when_model_omits_labels(self):
        results = parse_suggestions("Paris", "Name a city")
        self.assertEqual([item["answer"] for item in results], ["Paris"])
        self.assertEqual(results[0], {"answer": "Paris"})

    def test_accepts_answer_prefix_when_model_omits_safe_label(self):
        results = parse_suggestions("The answer is: Paris.", "Name a city")
        self.assertEqual([item["answer"] for item in results], ["Paris"])


if __name__ == "__main__":
    unittest.main()
