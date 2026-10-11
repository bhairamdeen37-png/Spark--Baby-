"""
Sanity checks for config and pure-logic helpers that don't need aiogram or
network access — safe to run in any environment, including CI without
installed dependencies beyond aiosqlite/aiohttp.
"""
import unittest

from config import PREMIUM_PLANS, FREE_TEXT_DAILY_LIMIT, FREE_IMAGE_DAILY_LIMIT
from services.quiz_service import _extract_json


class TestConfig(unittest.TestCase):

    def test_premium_plans_shape(self):
        for key, plan in PREMIUM_PLANS.items():
            self.assertIn("label", plan)
            self.assertIn("days", plan)
            self.assertIn("stars", plan)
            self.assertGreater(plan["days"], 0)
            self.assertGreater(plan["stars"], 0)

    def test_default_limits_are_positive(self):
        self.assertGreater(FREE_TEXT_DAILY_LIMIT, 0)
        self.assertGreater(FREE_IMAGE_DAILY_LIMIT, 0)


class TestQuizJsonExtraction(unittest.TestCase):

    def test_strips_markdown_fences(self):
        raw = "```json\n[{\"a\": 1}]\n```"
        self.assertEqual(_extract_json(raw), '[{"a": 1}]')

    def test_plain_json_passes_through(self):
        raw = '[{"a": 1}]'
        self.assertEqual(_extract_json(raw), '[{"a": 1}]')


if __name__ == "__main__":
    unittest.main()
