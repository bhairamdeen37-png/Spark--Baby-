"""Tests for the 'correct answer is always A' fix and the question-bank format (no network / no AI)."""
import random
import sys
import types
import unittest

from services.quiz_utils import randomize_positions, has_positional_option

# question_bank_online imports aiohttp; stub it only if it isn't installed (pure-logic tests need no network)
try:
    import aiohttp  # noqa: F401
except ImportError:
    sys.modules["aiohttp"] = types.SimpleNamespace(ClientTimeout=lambda **k: None, ClientSession=None)
from services import question_bank_online as qb


def _qs(n):
    return [{"question": f"Q{i}", "options": [f"ans{i}", f"w1_{i}", f"w2_{i}", f"w3_{i}"],
             "correct_index": 0, "explanation": ""} for i in range(n)]   # AI-style: correct is ALWAYS index 0


class TestRandomizePositions(unittest.TestCase):

    def test_correct_answer_not_always_first(self):
        out = randomize_positions(_qs(8), random.Random(1))
        self.assertGreater(len({q["correct_index"] for q in out}), 1)

    def test_four_questions_use_all_four_positions(self):
        for seed in range(30):
            out = randomize_positions(_qs(4), random.Random(seed))
            self.assertEqual(sorted(q["correct_index"] for q in out), [0, 1, 2, 3])

    def test_balanced_for_longer_quiz(self):
        out = randomize_positions(_qs(10), random.Random(7))
        counts = [sum(1 for q in out if q["correct_index"] == p) for p in range(4)]
        self.assertLessEqual(max(counts) - min(counts), 1 + 1)   # 10 questions -> at most 3/3/2/2

    def test_score_key_still_points_to_right_text(self):
        for i, q in enumerate(randomize_positions(_qs(12), random.Random(3))):
            self.assertEqual(q["options"][q["correct_index"]], f"ans{q['question'][1:]}")
            self.assertEqual(len(set(q["options"])), 4)

    def test_all_of_the_above_not_moved(self):
        q = {"question": "x", "options": ["a", "b", "c", "All of the above"], "correct_index": 3, "explanation": ""}
        self.assertTrue(has_positional_option(q["options"]))
        out = randomize_positions([q], random.Random(1))[0]
        self.assertEqual(out["options"], q["options"])
        self.assertEqual(out["correct_index"], 3)


class TestBankFormat(unittest.TestCase):

    def test_letter_answer(self):
        n = qb.normalize({"question": "Q", "options": ["a", "b", "c", "d"], "answer": "C", "subject": "Physics", "level": "Hard"})
        self.assertEqual(n["correct_index"], 2)
        self.assertEqual((n["subject"], n["level"]), ("physics", "hard"))

    def test_dict_options_and_text_answer(self):
        n = qb.normalize({"question": "Q", "options": {"A": "x", "B": "y", "C": "z", "D": "w"}, "answer": "z"})
        self.assertEqual(n["correct_index"], 2)

    def test_rejects_bad_items(self):
        self.assertIsNone(qb.normalize({"question": "Q", "options": ["a", "a", "b", "c"], "answer": "A"}))   # duplicate
        self.assertIsNone(qb.normalize({"question": "Q", "options": ["a", "b", "c"], "answer": "A"}))       # 3 options
        self.assertIsNone(qb.normalize({"question": "Q", "options": ["a", "b", "c", "d"]}))                 # no answer

    def test_shipped_sample_files_are_valid(self):
        import json
        for exam in ("jee", "neet"):
            data = json.loads((qb.LOCAL_DIR / f"{exam}.json").read_text(encoding="utf-8"))
            items = [qb.normalize(i) for i in data["questions"]]
            self.assertTrue(all(items), exam)
            self.assertEqual(len(items), 6)


if __name__ == "__main__":
    unittest.main()


class TestHuggingFaceRows(unittest.TestCase):
    """Column-layout detection for Hugging Face datasets (offline: synthetic rows in common layouts)."""

    def setUp(self):
        from services import hf_dataset_source as hf
        self.hf = hf

    def test_separate_option_columns_letter_answer(self):
        r = {"Question": "Unit of force?", "A": "N", "B": "J", "C": "W", "D": "Pa", "Answer": "A", "Subject": "Physics"}
        n = self.hf.normalize_rows([r])[0]
        self.assertEqual((n["correct_index"], n["subject"], n["trusted"]), (0, "physics", False))

    def test_one_based_ints_detected(self):
        rows = [{"question": f"q{i}", "options": ["a", "b", "c", "d"], "answer": i % 4 + 1} for i in range(8)]
        self.assertFalse(self.hf.detect_zero_based(rows))
        self.assertEqual([n["correct_index"] for n in self.hf.normalize_rows(rows)][:4], [0, 1, 2, 3])

    def test_zero_based_ints_detected(self):
        rows = [{"question": f"q{i}", "options": ["a", "b", "c", "d"], "cop": i % 4} for i in range(8)]
        self.assertTrue(self.hf.detect_zero_based(rows))
        self.assertEqual([n["correct_index"] for n in self.hf.normalize_rows(rows)][:4], [0, 1, 2, 3])

    def test_skips_unusable_rows(self):
        bad = [
            {"question": "Find x", "options": ["1", "2", "3", "4"], "answer": "A, C"},                 # multi-correct
            {"question": "Numerical, answer is an integer", "answer": 42},                              # no options
            {"question": "See the figure shown below", "options": ["a", "b", "c", "d"], "answer": "A"},  # needs picture
            {"question": "Q", "options": ["a", "a", "b", "c"], "answer": "A"},                          # duplicates
        ]
        self.assertEqual(self.hf.normalize_rows(bad), [])

    def test_latex_converted_and_subject_synonyms(self):
        r = {"question": r"Value of $\frac{1}{2}$ is", "choices": ["0.5", "1", "2", "3"], "answer": "A", "subject": "Mathematics"}
        n = self.hf.normalize_rows([r])[0]
        self.assertNotIn("\\", n["question"])
        self.assertEqual(n["subject"], "maths")
