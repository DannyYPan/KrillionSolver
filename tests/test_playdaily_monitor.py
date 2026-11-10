import types
import unittest

from app.playdaily_monitor import detect_playdaily_text, read_playdaily_prompt


class _Locator:
    def __init__(self, texts):
        self._texts = texts

    def all_inner_texts(self):
        return self._texts


class PlaydailyPromptTests(unittest.TestCase):
    def test_prefers_prompt_element_over_editorial_body(self):
        page = types.SimpleNamespace(
            locator=lambda _selector: _Locator(["Name an animal with a shell"])
        )
        result = read_playdaily_prompt(
            page,
            "Krillion\nSay the obvious answer, then bin it.\nPrivacy\nGames",
        )
        self.assertEqual(result.prompt, "Name an animal with a shell")
        self.assertEqual(result.method, "playdaily-prompt-elements")

    def test_body_fallback_keeps_prompt_qualifier(self):
        page = types.SimpleNamespace(locator=lambda _selector: _Locator([]))
        result = read_playdaily_prompt(
            page,
            "Play Daily\nQuestion #4: Name an English word\nending in -type\n00:15",
        )
        self.assertEqual(result.prompt, "Name an English word ending in -type")
        self.assertEqual(result.method, "playdaily-body-fallback")

    def test_editorial_slogan_is_never_a_prompt(self):
        result = detect_playdaily_text("Say the obvious answer, then bin it.\nPlay Daily\nPrivacy")
        self.assertIsNone(result.prompt)

    def test_regular_question_text_is_detected(self):
        result = detect_playdaily_text("Question: Which country has red and white on its flag?")
        self.assertEqual(result.prompt, "Which country has red and white on its flag?")


if __name__ == "__main__":
    unittest.main()
