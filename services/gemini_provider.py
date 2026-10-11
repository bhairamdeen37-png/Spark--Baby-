"""
Google Gemini provider. Supports text and image (vision) input.
Raises on failure — ai_router.py decides what to do next.
"""
import base64
import aiohttp

from config import GEMINI_API_KEY, GEMINI_MODELS

TIMEOUT = aiohttp.ClientTimeout(total=25)
SUPPORTS_IMAGES = True


class ProviderError(Exception):
    """Raised for any Gemini failure — includes whether it's retryable."""
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


_working_model = None  # remembered once a model ID answers successfully


async def generate(messages: list, system_prompt: str, image_bytes: bytes = None,
                    image_mime: str = "image/jpeg", max_tokens: int = 600) -> str:
    """Tries the configured model list in order; a retired/unknown model ID (HTTP 404)
    just moves on to the next candidate instead of killing Gemini entirely."""
    global _working_model
    if not GEMINI_API_KEY:
        raise ProviderError("no_api_key", retryable=False)
    candidates = ([_working_model] if _working_model else []) + [m for m in GEMINI_MODELS if m != _working_model]
    last = None
    for model in candidates:
        try:
            out = await _generate_with(model, messages, system_prompt, image_bytes, image_mime, max_tokens)
            _working_model = model
            return out
        except ProviderError as e:
            last = e
            if str(e).startswith("http_404") or "not found" in str(e).lower():
                continue  # model ID retired/unknown -> try next one
            raise
    raise last or ProviderError("no_model", retryable=False)


async def _generate_with(model, messages, system_prompt, image_bytes, image_mime, max_tokens):
    if not GEMINI_API_KEY:
        raise ProviderError("no_api_key", retryable=False)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GEMINI_API_KEY}"
    )

    contents = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    if image_bytes is not None:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        if contents and contents[-1]["role"] == "user":
            contents[-1]["parts"].append(
                {"inline_data": {"mime_type": image_mime, "data": b64}}
            )
        else:
            contents.append({
                "role": "user",
                "parts": [{"inline_data": {"mime_type": image_mime, "data": b64}}],
            })

    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
    }

    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 401 or resp.status == 403:
                    raise ProviderError(f"auth_error:{resp.status}", retryable=False)
                if resp.status == 429:
                    raise ProviderError("rate_limited", retryable=True)
                if resp.status >= 500:
                    raise ProviderError(f"server_error:{resp.status}", retryable=True)
                if resp.status != 200:
                    raise ProviderError(f"http_{resp.status}:{str(data)[:200]}", retryable=False)

                candidates = data.get("candidates") or []
                if not candidates:
                    raise ProviderError("empty_candidates", retryable=True)
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                if not text:
                    raise ProviderError("empty_text", retryable=True)
                return text
    except ProviderError:
        raise
    except Exception as e:
        raise ProviderError(f"network_error:{e}", retryable=True)
