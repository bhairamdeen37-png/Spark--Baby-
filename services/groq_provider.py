"""
Groq provider — text only. No vision support on the configured model, so
ai_router.py must never route image requests here (that would silently
convert an image question into a text-only guess, which is explicitly
disallowed by the project brief).
"""
import aiohttp

from config import GROQ_API_KEY, GROQ_MODEL

TIMEOUT = aiohttp.ClientTimeout(total=25)
SUPPORTS_IMAGES = False


class ProviderError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


async def generate(messages: list, system_prompt: str, max_tokens: int = 600) -> str:
    if not GROQ_API_KEY:
        raise ProviderError("no_api_key", retryable=False)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    msgs = [{"role": "system", "content": system_prompt}]
    msgs.extend({"role": m["role"], "content": m["content"]} for m in messages)
    payload = {"model": GROQ_MODEL, "messages": msgs, "max_tokens": max_tokens, "temperature": 0.7}

    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 401 or resp.status == 403:
                    raise ProviderError(f"auth_error:{resp.status}", retryable=False)
                if resp.status == 404:
                    # usually means the model ID is wrong/deprecated — not a transient issue
                    raise ProviderError(f"model_not_found:{str(data)[:200]}", retryable=False)
                if resp.status == 429:
                    raise ProviderError("rate_limited", retryable=True)
                if resp.status >= 500:
                    raise ProviderError(f"server_error:{resp.status}", retryable=True)
                if resp.status != 200:
                    raise ProviderError(f"http_{resp.status}:{str(data)[:200]}", retryable=False)

                choices = data.get("choices") or []
                if not choices:
                    raise ProviderError("empty_choices", retryable=True)
                text = (choices[0].get("message", {}) or {}).get("content", "").strip()
                if not text:
                    raise ProviderError("empty_text", retryable=True)
                return text
    except ProviderError:
        raise
    except Exception as e:
        raise ProviderError(f"network_error:{e}", retryable=True)
