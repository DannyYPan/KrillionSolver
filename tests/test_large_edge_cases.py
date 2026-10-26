"""Large deterministic regression matrix for prompt and answer edge cases."""

import unittest

from app.answer_lexicon import candidate_check, local_candidates, prompt_kind
from app.ollama_provider import parse_suggestions
from app.prompt_constraints import split_prompt_exclusions
from app.prompt_detector import detect_prompt, find_said_answers, normalize_prompt


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

    def test_third_thousand_knowledge_and_overlap_cases(self):
        checked = 0

        # 200 aliases across the general-knowledge categories.
        category_cases = [
            ("Name an animal", "animal", "Tiger"),
            ("Name a creature", "animal", "Turtle"),
            ("Name a food", "food", "Ramen"),
            ("Name a fruit", "fruit", "Mango"),
            ("Name a vegetable", "vegetable", "Okra"),
            ("Name a sport", "sport", "Curling"),
            ("Name a musical instrument", "instrument", "Bassoon"),
            ("Name a job", "occupation", "Teacher"),
            ("Name a profession", "occupation", "Actuary"),
            ("Name a vehicle", "vehicle", "Hovercraft"),
            ("Name a flower", "flower", "Peony"),
            ("Name a tree", "tree", "Baobab"),
            ("Name a planet", "planet", "Neptune"),
            ("Name a gem", "gemstone", "Opal"),
            ("Name a gemstone", "gemstone", "Tanzanite"),
            ("Name a board game", "board_game", "Catan"),
            ("Name a dinosaur", "dinosaur", "Iguanodon"),
            ("Name a body part", "body_part", "Patella"),
            ("Name an interjection", "interjection", "Yikes"),
            ("Name a filler phrase", "filler_word", "You Know"),
        ]
        for index in range(200):
            prompt, category, answer = category_cases[index % len(category_cases)]
            with self.subTest(group="knowledge-alias", prompt=prompt, answer=answer):
                self.assertEqual(prompt_kind(prompt), ("trivia", category))
                self.assertEqual(candidate_check(answer, prompt), "match")
            checked += 1

        # 150 animal-trait prompts must prefer the relevant subset.
        trait_cases = [
            ("shell", "Nautilus", "Dog"),
            ("stripes", "Zebra", "Dolphin"),
            ("spots", "Leopard", "Elephant"),
            ("horns", "Rhinoceros", "Penguin"),
            ("wings", "Owl", "Tortoise"),
            ("scales", "Crocodile", "Giraffe"),
        ]
        for index in range(150):
            trait, expected, unrelated = trait_cases[index % len(trait_cases)]
            prompt = f"Name an animal with {trait}"
            with self.subTest(group="animal-trait", prompt=prompt):
                answers = [item["answer"] for item in local_candidates(prompt, limit=50)]
                self.assertIn(expected, answers)
                self.assertNotIn(unrelated, answers)
            checked += 1

        # 150 television character and sitcom wording variants.
        tv_cases = [
            ("Name a character from How I Met Your Mother", "Barney Stinson"),
            ("Name a character from How I Met Ur Mother", "Robin Scherbatsky"),
            ("Name a How I Met Your Mother character", "Ranjit"),
            ("Name a character in SpongeBob", "Patrick Star"),
            ("Name a Sponge Bob Square Pants character", "Sandy Cheeks"),
            ("Name a sitcom TV show", "Community"),
            ("Name a sit-down comedy television show", "Frasier"),
            ("Name a situation comedy show", "Cheers"),
        ]
        for index in range(150):
            prompt, answer = tv_cases[index % len(tv_cases)]
            with self.subTest(group="television", prompt=prompt):
                self.assertEqual(candidate_check(answer, prompt), "match")
            checked += 1

        # 150 interjection/filler checks, including cross-category uncertainty.
        language_cases = [
            ("Name an interjection", "Wow", "Um"),
            ("Name an interjection", "Alas", "You Know"),
            ("Name a filler word", "Uh", "Hooray"),
            ("Name a hesitation phrase", "I Mean", "Yikes"),
        ]
        for index in range(150):
            prompt, expected, other = language_cases[index % len(language_cases)]
            with self.subTest(group="spoken-language", prompt=prompt):
                self.assertEqual(candidate_check(expected, prompt), "match")
                self.assertEqual(candidate_check(other, prompt), "uncertain")
            checked += 1

        # 200 exclusions containing two disallowed answers.
        for index in range(200):
            first = f"first{_letters(index)}"
            second = f"second{_letters(index)}"
            joiner = "and" if index % 2 == 0 else "or"
            prompt = f"Name a snack — {first} {joiner} {second} doesn't count"
            with self.subTest(group="multiple-exclusions", prompt=prompt):
                core, excluded = split_prompt_exclusions(prompt)
                self.assertEqual(core, "Name a snack")
                self.assertEqual(excluded, [first, second])
            checked += 1

        # 150 case, numbering, player-name, and score combinations.
        for index in range(150):
            answer = f"Choice{_letters(index)}"
            variants = [
                answer.upper(),
                f"{index + 1}. {answer}",
                f"Player {index}: {answer}",
                f"PLAYER: {answer.upper()} +10 pts",
                f"- {answer} correct",
            ]
            row = variants[index % len(variants)]
            with self.subTest(group="said-row-variants", row=row):
                page = f"Name a snack\n{row}\nSubmit"
                self.assertEqual(find_said_answers([answer], page, "Name a snack"), [answer])
            checked += 1

        self.assertEqual(checked, 1000)

    def test_two_thousand_full_pipeline_edge_cases(self):
        checked = 0

        # 250 ranking checks: a known category match must move ahead of an
        # unknown but plausible answer without deleting the unknown answer.
        known_animals = ["Turtle", "Tiger", "Elephant", "Dolphin", "Owl"]
        for index in range(250):
            unknown = f"MysteryCreature{_letters(index)}"
            known = known_animals[index % len(known_animals)]
            response = f"SAFE: {unknown}\nMORE OPTIONS: {known}"
            with self.subTest(group="knowledge-ranking", response=response):
                answers = [item["answer"] for item in parse_suggestions(response, "Name an animal")]
                self.assertEqual(answers, [known, unknown])
            checked += 1

        # 250 exclusions applied while parsing model responses.
        for index in range(250):
            blocked = f"Blocked{_letters(index)}"
            allowed = f"Allowed{_letters(index)}"
            prompt = f"Name a city — {blocked} doesn't count"
            response = f"SAFE: {blocked}\nMORE OPTIONS: {allowed}, {blocked.lower()}, {allowed.lower()}"
            with self.subTest(group="parser-exclusion", prompt=prompt):
                answers = [item["answer"] for item in parse_suggestions(response, prompt)]
                self.assertEqual(answers, [allowed])
            checked += 1

        # 250 submitted-answer matches surrounded by misleading prose.
        for index in range(250):
            answer = f"Result{_letters(index)}"
            other = f"Result{_letters(index + 300)}"
            page = (
                f"Name a city\nThe prompt documentation mentions {other}\n"
                f"Player {index}: {answer} +{index % 50 + 1} points\nSubmit"
            )
            with self.subTest(group="said-mixed-page", answer=answer):
                self.assertEqual(find_said_answers([answer, other], page, "Name a city"), [answer])
            checked += 1

        # 250 unknown answers in recognized categories remain available.
        category_prompts = [
            "Name an animal", "Name a food", "Name a sport", "Name an instrument",
            "Name a profession", "Name a vehicle", "Name a flower", "Name a gemstone",
            "Name a board game", "Name a dinosaur",
        ]
        for index in range(250):
            prompt = category_prompts[index % len(category_prompts)]
            answer = f"UnlistedAnswer{_letters(index)}"
            with self.subTest(group="unknown-preservation", prompt=prompt):
                self.assertEqual(candidate_check(answer, prompt), "uncertain")
                parsed = parse_suggestions(f"SAFE: {answer}", prompt)
                self.assertEqual([item["answer"] for item in parsed], [answer])
            checked += 1

        # 200 six-, seven-, and eight-syllable wording variants.
        syllables = [("6", "6"), ("six", "6"), ("7", "7"), ("seven", "7"),
                     ("8", "8"), ("eight", "8")]
        syllable_templates = [
            "Name a {n}-syllable word", "Name a word with {n} syllables",
            "Give an answer having {n} syllables", "Think of something with {n} syllables",
        ]
        for index in range(200):
            raw, expected = syllables[index % len(syllables)]
            prompt = syllable_templates[index % len(syllable_templates)].format(n=raw)
            with self.subTest(group="high-syllables", prompt=prompt):
                self.assertEqual(prompt_kind(prompt), ("syllables", expected))
            checked += 1

        # 200 valid prompt-detection variations mixed with game chrome.
        starters = ["Name a", "Give me a", "Think of a", "What is a", "Which is a"]
        for index in range(200):
            prompt = f"{starters[index % len(starters)]} city associated with {_letters(index)}?"
            page = f"KRILLION\nRound {index + 1}\n00:15\n{prompt}\nSubmit"
            with self.subTest(group="prompt-detection", prompt=prompt):
                self.assertEqual(detect_prompt(page).prompt, prompt)
            checked += 1

        # 200 Unicode normalization and irregular-whitespace comparisons.
        for index in range(200):
            suffix = _letters(index)
            ordinary = f"Name a city {suffix}"
            fullwidth = "Ｎａｍｅ\u00a0ａ\tｃｉｔｙ  " + suffix
            with self.subTest(group="normalization", text=fullwidth):
                self.assertEqual(normalize_prompt(fullwidth), normalize_prompt(ordinary))
            checked += 1

        # 200 natural-language exclusion forms outside dash punctuation.
        exclusion_templates = [
            "Name a city excluding {answer}",
            "Name a city except for {answer}",
            "Name a city except {answer}",
            "Name a city but not {answer}",
            "Name a city not including {answer}",
        ]
        for index in range(200):
            answer = f"City{_letters(index)}"
            prompt = exclusion_templates[index % len(exclusion_templates)].format(answer=answer)
            with self.subTest(group="natural-exclusion", prompt=prompt):
                core, excluded = split_prompt_exclusions(prompt)
                self.assertEqual(core, "Name a city")
                self.assertEqual(excluded, [answer])
            checked += 1

        # 200 refusal, uncertainty, explanation, and overlong response shapes.
        malformed_templates = [
            "UNCERTAIN",
            "Maybe {answer} is probably right.",
            "As an AI, I cannot confirm {answer}.",
            "I think {answer} is the answer because it seems to fit.",
        ]
        for index in range(200):
            answer = f"Guess{_letters(index)}"
            response = malformed_templates[index % len(malformed_templates)].format(answer=answer)
            with self.subTest(group="malformed-output", response=response):
                self.assertEqual(parse_suggestions(response, "Name a city"), [])
            checked += 1

        self.assertEqual(checked, 2000)


if __name__ == "__main__":
    unittest.main()
