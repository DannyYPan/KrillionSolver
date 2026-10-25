import sys
import os
import tempfile
import types
import unittest
from unittest.mock import patch

from app.answer_lexicon import _syllable_counts, _words, candidate_check, local_candidates, prompt_kind, satisfies_constraint
from app import learned_answers


class AnswerLexiconTests(unittest.TestCase):
    def test_ending_prompt_returns_dictionary_words_matching_suffix(self):
        fake = types.SimpleNamespace(words=lambda: ["cat", "hat", "dog", "what"])
        _words.cache_clear()
        with patch.dict(sys.modules, {"cmudict": fake}):
            answers = local_candidates("What ends in -at?")
        _words.cache_clear()
        self.assertTrue(answers)
        self.assertTrue(all(item["answer"].endswith("at") for item in answers))

    def test_starts_contains_and_multiword_suffix_constraints(self):
        fake = types.SimpleNamespace(words=lambda: ["prototype", "stereotype", "seafood", "foodtruck", "stopwatch", "watch", "non", "nonstop"])
        _words.cache_clear()
        with patch.dict(sys.modules, {"cmudict": fake}):
            suffix = local_candidates("Name something ending with -type")
            contains = local_candidates("Name a word that contains food")
            starts = local_candidates("Name a word starting with proto")
        _words.cache_clear()
        self.assertIn("prototype", [item["answer"] for item in suffix])
        self.assertIn("seafood", [item["answer"] for item in contains])
        self.assertIn("prototype", [item["answer"] for item in starts])
        self.assertTrue(satisfies_constraint("seafood", "Name a word that contains food"))
        self.assertTrue(satisfies_constraint("prototype", "Name something ending with -type"))

    def test_semantic_with_prompt_is_not_misread_as_letter_containment(self):
        prompt = "Name an animal with a shell"
        self.assertIsNone(prompt_kind(prompt))
        self.assertEqual(local_candidates(prompt), [])

    def test_word_constraints_keep_unknown_matching_text_as_uncertain(self):
        fake = types.SimpleNamespace(words=lambda: ["prototype", "seafood"])
        _words.cache_clear()
        with patch.dict(sys.modules, {"cmudict": fake}):
            self.assertEqual(candidate_check("nonsensextype", "Name a word ending in -type"), "uncertain")
            self.assertEqual(candidate_check("foodxyz", "Name a word containing food"), "uncertain")
            self.assertEqual(candidate_check("dog", "Name a word ending in -type"), "reject")
        _words.cache_clear()

    def test_compound_prompt_without_word_token(self):
        fake = types.SimpleNamespace(words=lambda: ["stop", "watch", "stopwatch", "non", "nonstop"])
        _words.cache_clear()
        with patch.dict(sys.modules, {"cmudict": fake}):
            answers = local_candidates("Name a compound containing stop")
            self.assertTrue(satisfies_constraint("stopwatch", "Name a compound containing stop"))
        _words.cache_clear()
        self.assertIn("stopwatch", [item["answer"] for item in answers])

    def test_syllable_prompts_use_pronunciations(self):
        fake = types.SimpleNamespace(dict=lambda: {
            "cat": [["K", "AE1", "T"]],
            "banana": [["B", "AH0", "N", "AE1", "N", "AH0"]],
            "computer": [["K", "AH0", "M", "P", "Y", "UW1", "T", "ER0"]],
        })
        _syllable_counts.cache_clear()
        with patch.dict(sys.modules, {"cmudict": fake}):
            self.assertEqual(prompt_kind("Name a word with three syllables"), ("syllables", "3"))
            self.assertEqual(candidate_check("banana", "Name a 3-syllable word"), "match")
            self.assertEqual(candidate_check("cat", "Name a 3-syllable word"), "reject")
            answers = local_candidates("Name a word with 3 syllables")
        _syllable_counts.cache_clear()
        self.assertEqual({item["answer"] for item in answers}, {"banana", "computer"})

    def test_compound_prompt_checks_dictionary_components(self):
        fake = types.SimpleNamespace(words=lambda: ["sun", "flower", "sunflower", "sunny", "flowering"])
        with patch.dict(sys.modules, {"cmudict": fake}):
            self.assertTrue(satisfies_constraint("sunflower", "Name a compound word with sun"))
            self.assertFalse(satisfies_constraint("sunny", "Name a compound word with sun"))

    def test_country_list_and_regional_filter(self):
        self.assertTrue(satisfies_constraint("Canada", "Name a country"))
        self.assertFalse(satisfies_constraint("Canada", "Name a European country"))
        self.assertTrue(satisfies_constraint("France", "Name a European country"))
        self.assertEqual(prompt_kind("Name a European country")[0], "country_region")
        self.assertTrue(local_candidates("Name a European country"))

    def test_country_exclusion_applies_to_local_results(self):
        answers = local_candidates("Name a country", excluded=["Afghanistan"])
        self.assertNotIn("Afghanistan", [item["answer"] for item in answers])

    def test_country_flag_coastline_and_population_qualifiers(self):
        red_flags = local_candidates("Name a country with red in its flag")
        self.assertIn("Canada", [item["answer"] for item in red_flags])
        self.assertFalse(satisfies_constraint("Finland", "Name a country with red in its flag"))
        self.assertTrue(satisfies_constraint("France", "Name a country with red and blue in its flag"))
        self.assertFalse(satisfies_constraint("Canada", "Name a country with blue and yellow in its flag"))
        europe_red = local_candidates("Name a European country with red in its flag")
        self.assertIn("France", [item["answer"] for item in europe_red])
        self.assertNotIn("Canada", [item["answer"] for item in europe_red])
        landlocked = local_candidates("Name a country without a coastline")
        self.assertIn("Austria", [item["answer"] for item in landlocked])
        self.assertFalse(satisfies_constraint("Canada", "Name a country without a coastline"))
        populated = local_candidates("Name a country with a population over 100,000")
        self.assertIn("Canada", [item["answer"] for item in populated])
        self.assertFalse(satisfies_constraint("Monaco", "Name a country with a population over 100,000"))

    def test_user_confirmed_answers_persist_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            self.assertTrue(learned_answers.remember("Name a city", "New York"))
            self.assertTrue(learned_answers.remember(" name a CITY? ", "new york"))
            self.assertEqual(learned_answers.get_learned("Name a city"), ["New York"])
            self.assertEqual(learned_answers.get_learned("Name a city", ["new york"]), [])
            self.assertFalse(learned_answers.remember("Name a city", "   "))


if __name__ == "__main__":
    unittest.main()
