"""
Sequential fallback across the three providers.

Rule (per project brief): a successful answer from an earlier provider
means later providers are NEVER called. A provider is only skipped forward
from on a *retryable* failure (timeout, 429, 5xx, empty response) — an
auth error or missing key is also treated as "move on", but is logged
differently since it means the deployment is misconfigured, not that the
provider is temporarily down.

Image requests only go to providers that actually support vision
(SUPPORTS_IMAGES = True) — an image is never silently downgraded to a
text-only request on a text-only provider.
"""
import asyncio
import logging

from services import gemini_provider, groq_provider, openrouter_provider

log = logging.getLogger("spark_baby.ai_router")

MAX_RETRIES_PER_PROVIDER = 2
RETRY_DELAY_SECONDS = 1


class AllProvidersFailedError(Exception):
    def __init__(self, details: dict):
        self.details = details
        super().__init__(f"All providers failed: {details}")


async def _try_provider(name: str, call_coro_factory):
    """Runs a provider with bounded retries. Returns text or raises the last error."""
    last_err = None
    for attempt in range(MAX_RETRIES_PER_PROVIDER):
        try:
            return await call_coro_factory()
        except Exception as e:
            last_err = e
            retryable = getattr(e, "retryable", True)
            log.warning(f"[AI] {name} attempt {attempt + 1} failed: {e} (retryable={retryable})")
            if not retryable:
                break
            await asyncio.sleep(RETRY_DELAY_SECONDS)
    raise last_err


async def generate_answer(messages: list, system_prompt: str, image_bytes: bytes = None,
                           image_mime: str = "image/jpeg") -> str:
    """
    Returns the answer text from the first provider that succeeds.
    Raises AllProvidersFailedError if every eligible provider fails.
    """
    errors = {}

    providers = [
        ("gemini", gemini_provider),
        ("groq", groq_provider),
        ("openrouter", openrouter_provider),
    ]

    for name, mod in providers:
        if image_bytes is not None and not getattr(mod, "SUPPORTS_IMAGES", False):
            errors[name] = "skipped_no_vision_support"
            continue

        async def _call():
            if image_bytes is not None:
                return await mod.generate(messages, system_prompt, image_bytes=image_bytes,
                                           image_mime=image_mime)
            return await mod.generate(messages, system_prompt)

        try:
            answer = await _try_provider(name, _call)
            return answer
        except Exception as e:
            errors[name] = str(e)
            continue

    log.error(f"[AI] All providers failed/skipped: {errors}")
    raise AllProvidersFailedError(errors)
