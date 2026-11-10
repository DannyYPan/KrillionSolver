import json
import sys
import os
import tempfile
import types
import unittest
from unittest.mock import patch

from app.answer_lexicon import (
    _syllable_counts, _word_list, _words, candidate_check, local_candidates,
    prompt_kind, satisfies_constraint,
)
from app import learned_answers


class AnswerLexiconTests(unittest.TestCase):
    def test_one_thousand_dictionary_constraint_cases(self):
        """Exercise real dictionary entries without relying on hand-picked words."""
        words = [word for word in _word_list() if len(word) >= 4][:1000]
        self.assertEqual(len(words), 1000)
        for index, word in enumerate(words):
            # Cycle through all three spelling rules while keeping each case
            # deterministic and guaranteed to describe the selected word.
            rule = index % 3
            if rule == 0:
                fragment = word[-2:]
                prompt = f"Name an English word ending in -{fragment}"
                broken = word + "x"
            elif rule == 1:
                fragment = word[:2]
                prompt = f"Name an English word starting with {fragment}"
                broken = "zz" + word[2:]
            else:
                start = max(0, (len(word) - 2) // 2)
                fragment = word[start:start + 2]
                prompt = f"Name an English word containing {fragment}"
                broken = word.replace(fragment, "zz")
            with self.subTest(case=index, word=word, prompt=prompt):
                self.assertEqual(candidate_check(word, prompt), "match")
                self.assertEqual(candidate_check(broken, prompt), "reject")

    def test_previous_wrong_answer_regressions(self):
        """Keep failures observed in the game from returning via broad lists."""
        cases = (
            ("Name an animal with a shell", {"ab", "ac", "ad", "dog"}),
            ("Name a sea animal that isn't a fish or a bird", {"kangaroo", "giraffe", "zebra", "tiger"}),
            ("Name an item used for eating or serving food (like a plate or spoon)", {"pizza", "sushi", "curry"}),
            ("Name a Scandinavian or Nordic country or territory", {"united states", "canada", "china", "india"}),
            ("Name a combat sport", {"soccer", "basketball", "baseball", "tennis"}),
            ("Name an island country", {"united states", "canada", "china", "india"}),
            ("Name a country that borders China", {"united states", "canada", "china", "brazil"}),
            ("Name the most widely spoken language of an Asian country", {"china", "india", "japan"}),
            ("Name an English word containing ject", {"apple", "bridge", "candle", "dragon"}),
            ("Name a country with a monarchy", {"united states", "china", "india", "brazil"}),
            ("Name a country whose name starts with S", {"sa", "se", "sh", "si"}),
            ("Name an English word ending in a double letter", {"ba", "ca", "da", "ga", "ha"}),
            ("Name an English word containing fire", {"safire"}),
            ("Name an English word ending in -less", {"kless", "gless"}),
        )
        for prompt, forbidden in cases:
            with self.subTest(prompt=prompt):
                answers = {
                    item["answer"].casefold()
                    for item in local_candidates(prompt, limit=80)
                }
                self.assertTrue(answers.isdisjoint(forbidden), answers & forbidden)

    def test_previous_round_specific_rejections_use_exact_exclusions(self):
        """Valid English words rejected by one round remain dictionary words."""
        cases = (
            ("Name an English word containing atch", "batch"),
            ("Name an English word containing fire", "fired"),
            ("Name an English word ending in -ling", "goblin"),
        )
        for prompt, rejected in cases:
            with self.subTest(prompt=prompt, rejected=rejected):
                answers = local_candidates(prompt, excluded=[rejected], limit=80)
                self.assertNotIn(rejected, [item["answer"].casefold() for item in answers])

    def test_general_english_dictionary_is_compact_and_clean(self):
        words = _words()
        self.assertGreater(len(words), 20_000)
        self.assertLess(len(words), 35_000)
        for common in ("apple", "goblin", "prototype", "careless", "firefighter"):
            self.assertIn(common, words)
        for noisy in ("kless", "gless", "safire", "lymphadenopathy"):
            self.assertNotIn(noisy, words)

    def test_general_dictionary_preserves_frequency_order(self):
        words = _word_list()
        self.assertEqual(len(words), len(set(words)))
        self.assertLess(words.index("watch"), words.index("watching"))
        answers = [
            item["answer"] for item in local_candidates(
                "Name an English word containing atch", limit=8,
            )
        ]
        self.assertEqual(answers[:4], ["watch", "match", "watching", "catch"])

    def test_dictionary_constraints_and_exclusions_are_applied(self):
        cases = {
            "Name an English word ending in -less": lambda word: word.endswith("less"),
            "Name an English word starting with proto": lambda word: word.startswith("proto"),
            "Name an English word containing fire": lambda word: "fire" in word,
        }
        for prompt, matches in cases.items():
            with self.subTest(prompt=prompt):
                answers = [item["answer"] for item in local_candidates(prompt, limit=12)]
                self.assertTrue(answers)
                self.assertTrue(all(matches(answer.casefold()) for answer in answers))
                excluded = local_candidates(prompt, excluded=[answers[0].upper()], limit=12)
                self.assertNotIn(answers[0].casefold(), [item["answer"].casefold() for item in excluded])

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
        self.assertEqual(prompt_kind(prompt), ("trivia", "animal"))
        answers = [item["answer"] for item in local_candidates(prompt)]
        self.assertIn("Turtle", answers)
        self.assertNotIn("ab", answers)

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

    def test_country_letter_constraint_keeps_country_as_subject(self):
        answers = [
            item["answer"] for item in local_candidates(
                "Name a country whose name starts with S", limit=30,
            )
        ]
        self.assertIn("Sweden", answers)
        self.assertTrue(all(answer.casefold().startswith("s") for answer in answers))

    def test_double_letter_word_requires_an_actual_repeated_ending(self):
        prompt = "Name an English word ending in a double letter"
        self.assertEqual(candidate_check("ba", prompt), "reject")
        self.assertEqual(candidate_check("class", prompt), "match")

    def test_tv_character_prompts_and_show_aliases(self):
        himym = local_candidates("Name a character from How I Met Ur Mother")
        sponge = local_candidates("Name a character in SpongeBob SquarePants")
        self.assertIn("Barney Stinson", [item["answer"] for item in himym])
        self.assertIn("Patrick Star", [item["answer"] for item in sponge])
        self.assertEqual(candidate_check("Ted Mosby", "Name a How I Met Your Mother character"), "match")
        self.assertEqual(candidate_check("Obscure Guest", "Name a SpongeBob character"), "uncertain")

    def test_sitcom_and_sitdown_comedy_wording(self):
        for prompt in ("Name a sitcom TV show", "Name a sitdown comedy genre TV show", "Name a situation comedy television show"):
            with self.subTest(prompt=prompt):
                answers = local_candidates(prompt)
                self.assertIn("Community", [item["answer"] for item in answers])
                self.assertEqual(candidate_check("Frasier", prompt), "match")
                self.assertEqual(candidate_check("Unknown Show", prompt), "uncertain")

    def test_general_trivia_lists_and_animal_traits(self):
        categories = {
            "Name a musical instrument": "Oboe",
            "Name a gemstone": "Amethyst",
            "Name a board game": "Chess",
            "Name a dinosaur": "Triceratops",
            "Name a flower": "Orchid",
            "Name a profession": "Architect",
        }
        for prompt, expected in categories.items():
            with self.subTest(prompt=prompt):
                answers = [item["answer"] for item in local_candidates(prompt, limit=20)]
                self.assertIn(expected, answers)
                self.assertEqual(candidate_check(expected, prompt), "match")
        shell_answers = [item["answer"] for item in local_candidates("Name an animal with a shell", limit=20)]
        self.assertIn("Turtle", shell_answers)
        self.assertIn("Nautilus", shell_answers)
        self.assertNotIn("Dog", shell_answers)
        self.assertEqual(candidate_check("Unknown Shelled Animal", "Name an animal with a shell"), "uncertain")

    def test_qualifiers_do_not_replace_the_requested_subject(self):
        sea_prompt = "Name a sea animal that isn't a fish or a bird"
        sea_answers = [item["answer"] for item in local_candidates(sea_prompt, limit=30)]
        self.assertIn("Octopus", sea_answers)
        self.assertNotIn("Kangaroo", sea_answers)
        self.assertNotIn("Shark", sea_answers)
        item_prompt = "Name an item used for eating or serving food (like a plate or spoon)"
        self.assertIsNone(prompt_kind(item_prompt))
        emotion_prompt = "Name one of the emotions from Inside Out or Inside Out 2"
        self.assertIsNone(prompt_kind(emotion_prompt))
        self.assertEqual(prompt_kind("Name a food"), ("trivia", "food"))

    def test_exact_flag_colors_reject_flags_with_missing_or_extra_colors(self):
        prompt = "Name a country whose flag uses all three of red, white, and blue, and no other colors"
        answers = [item["answer"] for item in local_candidates(prompt, limit=40)]
        self.assertIn("France", answers)
        self.assertNotIn("Japan", answers)
        self.assertEqual(candidate_check("Japan", prompt), "uncertain")

    def test_country_symbol_and_multiple_region_qualifiers(self):
        star_prompt = "Name a country whose flag has a star on it"
        star_answers = [item["answer"] for item in local_candidates(star_prompt, limit=80)]
        self.assertIn("United States", star_answers)
        self.assertNotIn("India", star_answers)

        region_prompt = "Name a Scandinavian or Nordic country or territory"
        region_answers = [item["answer"] for item in local_candidates(region_prompt, limit=80)]
        self.assertIn("Norway", region_answers)
        self.assertIn("Finland", region_answers)
        self.assertIn("Greenland", region_answers)
        self.assertNotIn("United States", region_answers)

    def test_country_island_and_border_qualifiers(self):
        island = [item["answer"] for item in local_candidates("Name an island country", limit=80)]
        self.assertIn("Japan", island)
        self.assertNotIn("United States", island)

        china_border = [
            item["answer"] for item in local_candidates("Name a country that borders China", limit=80)
        ]
        self.assertIn("Mongolia", china_border)
        self.assertNotIn("China", china_border)
        self.assertNotIn("United States", china_border)

        self.assertEqual(local_candidates("Name a country with a monarchy", limit=80), [])

        self.assertEqual(
            local_candidates("Name a country with an unsupported mystery property", limit=20), [],
        )

    def test_specific_trivia_qualifiers_do_not_use_generic_lists(self):
        self.assertEqual(local_candidates("Name a combat sport", limit=20), [])
        self.assertEqual(
            local_candidates("Name a food you'd buy at a state fair or carnival", limit=20), [],
        )
        self.assertEqual(
            local_candidates("Name an animal that lives in swamps or wetlands", limit=20), [],
        )
        self.assertEqual(local_candidates("Name an animal that is nocturnal", limit=20), [])
        self.assertEqual(local_candidates("Name a sport with a ball", limit=20), [])
        self.assertEqual(local_candidates("Name a red food", limit=20), [])

    def test_later_nouns_and_negated_constraints_do_not_replace_the_subject(self):
        language = "Name the most widely spoken language of an Asian country"
        self.assertIsNone(prompt_kind(language))
        self.assertEqual(local_candidates(language, limit=20), [])

        negated = "Name an adverb that doesnâ€™t end in -ly (like â€œsoonâ€)"
        self.assertNotEqual(prompt_kind(negated), ("ending", "ly"))
        self.assertEqual(local_candidates(negated, limit=20), [])

    def test_encoded_curly_quotes_preserve_contains_constraint(self):
        prompt = "Name an English word containing â€œjectâ€"
        self.assertEqual(prompt_kind(prompt), ("contains", "ject"))
        answers = [item["answer"].casefold() for item in local_candidates(prompt, limit=30)]
        self.assertTrue(answers)
        self.assertTrue(all("ject" in answer for answer in answers))
        self.assertNotIn("apple", answers)

    def test_interjection_and_filler_word_lists_are_separate(self):
        interjections = [item["answer"] for item in local_candidates("Name an interjection", limit=30)]
        fillers = [item["answer"] for item in local_candidates("Name a filler word", limit=30)]
        self.assertIn("Yikes", interjections)
        self.assertIn("Alas", interjections)
        self.assertIn("Uh", fillers)
        self.assertIn("You Know", fillers)
        self.assertNotIn("Uh", interjections)
        self.assertEqual(candidate_check("Phew", "Name an interjection"), "match")
        self.assertEqual(candidate_check("I Mean", "Name a filler phrase"), "match")

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
        populated_all = [
            item["answer"] for item in local_candidates(
                "Name a country with a population over 100,000", limit=250,
            )
        ]
        self.assertIn("Kiribati", populated_all)
        self.assertIn("Seychelles", populated_all)
        self.assertFalse(satisfies_constraint("Monaco", "Name a country with a population over 100,000"))

    def test_indian_flag_does_not_match_red_or_yellow(self):
        self.assertNotIn(
            "India",
            [item["answer"] for item in local_candidates("Name a country with red in its flag", limit=250)],
        )
        self.assertNotIn(
            "India",
            [item["answer"] for item in local_candidates("Name a country with yellow in its flag", limit=250)],
        )

    def test_user_confirmed_answers_persist_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            self.assertTrue(learned_answers.remember("Name a city", "New York"))
            self.assertTrue(learned_answers.remember(" name a CITY? ", "new york"))
            self.assertEqual(learned_answers.get_learned("Name a city"), ["New York"])
            self.assertEqual(learned_answers.get_learned("Name a city", ["new york"]), [])
            self.assertFalse(learned_answers.remember("Name a city", "   "))

    def test_game_accepted_answer_writes_full_prompt_to_training_data(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            prompt = "Name a country that borders China"
            self.assertTrue(learned_answers.remember(prompt, "Mongolia", source="game-page"))
            rows = [
                json.loads(line) for line in learned_answers._training_path().read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn({"prompt": prompt, "answer": "Mongolia"}, rows)

    def test_saved_answer_is_an_instant_local_candidate_for_any_prompt(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            prompt = "Name a moon of a dwarf planet"
            self.assertTrue(learned_answers.remember(prompt, "Charon"))
            candidates = local_candidates(prompt)
            self.assertEqual(candidates[0], {"answer": "Charon", "confirmed": True})
            self.assertNotIn(
                "Charon",
                [item["answer"] for item in local_candidates(prompt, excluded=["charon"])],
            )

    def test_saved_answer_precedes_builtin_lexicon_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            prompt = "Name an animal with a shell"
            self.assertTrue(learned_answers.remember(prompt, "Nautilus"))
            candidates = local_candidates(prompt)
            answers = [item["answer"] for item in candidates]
            self.assertEqual(answers[0], "Nautilus")
            self.assertEqual(sum(answer.casefold() == "nautilus" for answer in answers), 1)
            self.assertTrue(candidates[0]["confirmed"])


if __name__ == "__main__":
    unittest.main()
