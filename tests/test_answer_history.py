import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app.answer_history import accepted, delete, details, export_csv, record, rejected, search, update


class AnswerHistoryTests(unittest.TestCase):
    def test_records_deduplicates_and_counts_observations(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            self.assertTrue(record("Name a city", "New York", "accepted", source="game-page"))
            self.assertTrue(record(" name a CITY? ", "new york", "accepted", source="game-page"))
            self.assertEqual(accepted("Name a city"), ["New York"])
            rows = details("Name a city")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["observations"], 2)
            self.assertEqual(rows[0]["source"], "game-page")

    def test_latest_feedback_reconciles_status(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            record("Name a city", "Paris", "rejected", source="feedback-button")
            self.assertEqual(accepted("Name a city"), [])
            self.assertEqual(rejected("Name a city"), ["Paris"])
            record("Name a city", "Paris", "accepted", source="game-page")
            self.assertEqual(accepted("Name a city"), ["Paris"])
            self.assertEqual(rejected("Name a city"), [])
            self.assertEqual(details("Name a city")[0]["status"], "accepted")

    def test_modes_are_separate_and_exclusions_apply(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            record("Name a city", "Paris", "accepted", mode="Krillion", source="game-page")
            record("Name a city", "Tokyo", "accepted", mode="Puffer Party", source="game-page")
            self.assertEqual(accepted("Name a city", mode="Krillion"), ["Paris"])
            self.assertEqual(accepted("Name a city", mode="Puffer Party"), ["Tokyo"])
            self.assertEqual(accepted("Name a city", mode="Krillion", excluded=["PARIS"]), [])

    def test_search_edit_delete_and_export(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            record("Name a city", "Paris", "accepted", source="game-page")
            record("Name an animal", "Dog", "rejected", source="feedback-button")
            rows = search("city", status="accepted")
            self.assertEqual(len(rows), 1)
            record_id = int(rows[0]["id"])
            self.assertTrue(update(
                record_id, mode="Puffer Party", prompt="Name a capital city",
                answer="Paris, France", status="accepted",
            ))
            edited = search("Paris, France", mode="Puffer Party")
            self.assertEqual(edited[0]["prompt"], "Name a capital city")
            export_path = Path(directory) / "history.csv"
            self.assertEqual(export_csv(export_path, edited), 1)
            self.assertIn("Paris, France", export_path.read_text(encoding="utf-8-sig"))
            self.assertTrue(delete(record_id))
            self.assertEqual(search("Paris, France"), [])


if __name__ == "__main__":
    unittest.main()
