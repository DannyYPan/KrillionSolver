"""Large deterministic regression matrix for prompt and answer edge cases."""

import unittest

from app.answer_lexicon import candidate_check, prompt_kind
from app.ollama_provider import parse_suggestions
from app.prompt_constraints import split_prompt_exclusions
from app.prompt_detector import detect_prompt, find_said_answers


def _letters(number: int) -> str:
    """Return a stable alphabetic identifier suitable for prompt tokens."""
    value = ""
    while True:
        number, remainder = divmod(number, 26)
        value = chr(97 + remainder) + value
        if number == 0:
            return value
        number -= 1


class LargeEdgeCaseMatrixTests(unittest.TestCase):
    def test_one_thousand_prompt_and_answer_cases(self):
        checked = 0

        # 250 semantic uses of "with" must not become spelling constraints.
        subjects = [
            "animal", "vehicle", "food", "instrument", "building",
            "plant", "insect", "bird", "fish", "reptile",
            "mammal", "tool", "toy", "sport", "job",
            "movie", "song", "city", "landmark", "device",
            "clothing item", "drink", "dessert", "tree", "flower",
        ]
        attributes = [
            "a shell", "red fur", "a long tail", "four legs", "wings",
            "stripes", "spots", "horns", "scales", "feathers",
        ]
        for subject in subjects:
            for attribute in attributes:
                prompt = f"Name a {subject} with {attribute}"
                with self.subTest(group="semantic-with", prompt=prompt):
                    kind = prompt_kind(prompt)
                    self.assertTrue(kind is None or kind[0] != "contains")
                checked += 1

        # 200 explicit word-containment requests must retain their token.
        for index in range(200):
            token = _letters(index + 26)
            wording = (
                f"Name a word containing {token}"
                if index % 2 == 0
                else f"Give me a word with the letters {token}"
            )
            with self.subTest(group="contains", prompt=wording):
                self.assertEqual(prompt_kind(wording), ("contains", token))
            checked += 1

        # 200 exclusions with punctuation/case variations must be separated.
        separators = [" — ", " - ", "; ", ", "]
        suffixes = ["doesn't count", "does not count", "doesnt count", "is not count"]
        for index in range(200):
            answer = f"item{_letters(index)}"
            separator = separators[index % len(separators)]
            suffix = suffixes[index % len(suffixes)]
            prompt = f"Name a useful object{separator}{answer} {suffix}"
            with self.subTest(group="exclusion", prompt=prompt):
                core, excluded = split_prompt_exclusions(prompt)
                self.assertEqual(core, "Name a useful object")
                self.assertEqual(excluded, [answer])
            checked += 1

        # 150 model responses must deduplicate case variants while preserving options.
        for index in range(150):
            first = f"Place{_letters(index)}"
            second = f"Town{_letters(index)}"
            response = f"SAFE: {first}\nMORE OPTIONS: {first.lower()}, {first.upper()}, {second}"
            with self.subTest(group="model-dedup", response=response):
                answers = [item["answer"] for item in parse_suggestions(response, "Name a city")]
                self.assertEqual(answers, [first, second])
            checked += 1

        # 150 common page-row shapes must identify an already submitted answer.
        row_templates = [
            "{answer}", "1. {answer}", "- {answer}", "Player: {answer}",
            "Player: {answer} +20 points", "{answer} correct",
        ]
        for index in range(150):
            answer = f"Answer{_letters(index)}"
            other = f"Other{_letters(index)}"
            row = row_templates[index % len(row_templates)].format(answer=answer)
            page = f"Name a city\n{row}\nSubmit"
            with self.subTest(group="already-said", row=row):
                self.assertEqual(find_said_answers([answer, other], page, "Name a city"), [answer])
            checked += 1

        # 50 numeric and written syllable prompt variants.
        numbers = [("1", "1"), ("one", "1"), ("2", "2"), ("two", "2"), ("3", "3"),
                   ("three", "3"), ("4", "4"), ("four", "4"), ("5", "5"), ("five", "5")]
        templates = ["Name a {n}-syllable word", "Name a word with {n} syllables",
                     "Give an answer having {n} syllables", "Think of a {n} syllable word",
                     "Name something with {n} syllables"]
        for raw, expected in numbers:
            for template in templates:
                prompt = template.format(n=raw)
                with self.subTest(group="syllables", prompt=prompt):
                    self.assertEqual(prompt_kind(prompt), ("syllables", expected))
                checked += 1

        self.assertEqual(checked, 1000)

    def test_second_thousand_different_edge_cases(self):
        checked = 0

        # 200 starts/ends constraints: matching unknown words remain available,
        # while definite spelling violations are rejected.
        for index in range(100):
            token = _letters(index + 26)
            prompt = f"Name a word starting with {token}"
            with self.subTest(group="starts", prompt=prompt):
                self.assertNotEqual(candidate_check(f"{token}word", prompt), "reject")
                self.assertEqual(candidate_check(f"word{token}", prompt), "reject")
            checked += 1
        for index in range(100):
            token = _letters(index + 26)
            prompt = f"Name a word ending with {token}"
            with self.subTest(group="ends", prompt=prompt):
                self.assertNotEqual(candidate_check(f"word{token}", prompt), "reject")
                self.assertEqual(candidate_check(f"{token}word", prompt), "reject")
            checked += 1

        # 150 known country/region combinations.
        regional = [
            ("France", "European"), ("Japan", "Asian"), ("Kenya", "African"),
            ("Canada", "North American"), ("Brazil", "South American"),
            ("Australia", "Oceanian"),
        ]
        for index in range(150):
            country, region = regional[index % len(regional)]
            prompt = f"Name a {region} country"
            with self.subTest(group="country-region", prompt=prompt, answer=country):
                self.assertEqual(candidate_check(country, prompt), "match")
            checked += 1

        # 150 malformed or explanatory model outputs must produce no candidates.
        for index in range(150):
            label = _letters(index)
            response = (
                f"Maybe Place{label} is valid because it is well known."
                if index % 2 == 0
                else f"UNCERTAIN: Place{label}"
            )
            with self.subTest(group="malformed-model", response=response):
                self.assertEqual(parse_suggestions(response, "Name a city"), [])
            checked += 1

        # 150 parenthetical and natural-language exclusion forms.
        for index in range(150):
            answer = f"choice{_letters(index)}"
            if index % 2 == 0:
                prompt = f"Name a food ({answer} doesn't count)"
            else:
                prompt = f"Name a food except {answer}"
            with self.subTest(group="alternate-exclusion", prompt=prompt):
                core, excluded = split_prompt_exclusions(prompt)
                self.assertEqual(core, "Name a food")
                self.assertEqual(excluded, [answer])
            checked += 1

        # 150 mentions in prompts/prose must not be mistaken for submitted rows.
        for index in range(150):
            answer = f"Answer{_letters(index)}"
            prompt = f"Name something related to {answer}"
            page = f"{prompt}\nA player is thinking about {answer} but has not submitted it\nSubmit"
            with self.subTest(group="said-false-positive", answer=answer):
                self.assertEqual(find_said_answers([answer], page, prompt), [])
            checked += 1

        # 200 pieces of common game chrome must not become prompts.
        noise_templates = [
            "Player {n}", "{n} points", "Round {n}", "Score {n}", "{n} seconds",
            "Submit", "Skip", "Ready", "Waiting", "Menu",
        ]
        for index in range(200):
            noise = noise_templates[index % len(noise_templates)].format(n=index + 1)
            page = f"KRILLION\n{noise}\nPlay\nBack"
            with self.subTest(group="prompt-noise", page=page):
                self.assertIsNone(detect_prompt(page).prompt)
            checked += 1

        self.assertEqual(checked, 1000)


if __name__ == "__main__":
    unittest.main()
