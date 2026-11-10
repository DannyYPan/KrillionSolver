import unittest

from app.ui import should_replenish_answers


class UiHelperTests(unittest.TestCase):
    def test_replenishment_starts_at_five_or_fewer(self):
        self.assertFalse(should_replenish_answers(6))
        self.assertTrue(should_replenish_answers(5))
        self.assertTrue(should_replenish_answers(4))
        self.assertTrue(should_replenish_answers(0))


if __name__ == "__main__":
    unittest.main()
