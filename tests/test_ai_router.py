"""
Tests the sequential-fallback contract using mocked providers — no live
API keys needed or used.
"""
import asyncio
import unittest
from unittest.mock import patch, AsyncMock

from services import ai_router


class FakeError(Exception):
    def __init__(self, msg, retryable=True):
        super().__init__(msg)
        self.retryable = retryable


class TestAiRouter(unittest.IsolatedAsyncioTestCase):

    async def test_gemini_success_skips_others(self):
        with patch("services.gemini_provider.generate", new=AsyncMock(return_value="gemini answer")) as gem, \
             patch("services.groq_provider.generate", new=AsyncMock()) as groq, \
             patch("services.openrouter_provider.generate", new=AsyncMock()) as openr:
            result = await ai_router.generate_answer([{"role": "user", "content": "hi"}], "sys")
            self.assertEqual(result, "gemini answer")
            gem.assert_called_once()
            groq.assert_not_called()
            openr.assert_not_called()

    async def test_gemini_fail_falls_to_groq(self):
        with patch("services.gemini_provider.generate",
                   new=AsyncMock(side_effect=FakeError("down", retryable=False))), \
             patch("services.groq_provider.generate", new=AsyncMock(return_value="groq answer")) as groq, \
             patch("services.openrouter_provider.generate", new=AsyncMock()) as openr:
            result = await ai_router.generate_answer([{"role": "user", "content": "hi"}], "sys")
            self.assertEqual(result, "groq answer")
            groq.assert_called_once()
            openr.assert_not_called()

    async def test_all_fail_raises(self):
        with patch("services.gemini_provider.generate",
                   new=AsyncMock(side_effect=FakeError("down", retryable=False))), \
             patch("services.groq_provider.generate",
                   new=AsyncMock(side_effect=FakeError("down", retryable=False))), \
             patch("services.openrouter_provider.generate",
                   new=AsyncMock(side_effect=FakeError("down", retryable=False))):
            with self.assertRaises(ai_router.AllProvidersFailedError):
                await ai_router.generate_answer([{"role": "user", "content": "hi"}], "sys")

    async def test_image_request_skips_text_only_provider(self):
        # groq_provider.SUPPORTS_IMAGES is False — it must never be called for an image request
        with patch("services.gemini_provider.generate",
                   new=AsyncMock(side_effect=FakeError("down", retryable=False))), \
             patch("services.groq_provider.generate", new=AsyncMock(return_value="should not be called")) as groq, \
             patch("services.openrouter_provider.generate", new=AsyncMock(return_value="openrouter vision answer")):
            result = await ai_router.generate_answer(
                [{"role": "user", "content": "what's in this image?"}], "sys", image_bytes=b"fake"
            )
            self.assertEqual(result, "openrouter vision answer")
            groq.assert_not_called()


if __name__ == "__main__":
    unittest.main()
