import unittest

from app.prompt_detector import detect_prompt, normalize_prompt


class PromptDetectionTests(unittest.TestCase):
    def test_question_prompt(self):
        self.assertEqual(detect_prompt("Timer\nWhat is a famous volcano?").prompt, "What is a famous volcano?")

    def test_category_and_non_question_instruction(self):
        self.assertEqual(detect_prompt("Name an island in the Pacific").prompt, "Name an island in the Pacific")

    def test_fill_blank(self):
        self.assertEqual(detect_prompt("Fill in the blank: To be or not to be").prompt, "Fill in the blank: To be or not to be")

    def test_ignores_chrome_and_noise(self):
        text = "KRILLION\nMenu\n2 hearts\n00:18\nSubmit\nJoin room\n"
        self.assertIsNone(detect_prompt(text).prompt)

    def test_ignores_puffer_party_instructions(self):
        text = "Krillion's multiplayer category game. Name an answer and pass the puffer before it pops. Play with friends or join a public room."
        self.assertIsNone(detect_prompt(text, "puffer-party").prompt)

    def test_empty_page_text(self):
        self.assertEqual(detect_prompt("").method, "empty-page-text")

    def test_duplicate_normalization(self):
        self.assertEqual(normalize_prompt("  Name a  river! "), normalize_prompt("name a river!"))


if __name__ == "__main__":
    unittest.main()
