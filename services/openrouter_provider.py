"""
OpenRouter provider — OpenAI-compatible chat completions. Default model
is "openrouter/free", OpenRouter's own router across free models, which
accepts both text and images and survives individual free models rotating
out (see AI_SETUP.md).
"""
import base64
import aiohttp

from config import OPENROUTER_API_KEY, OPENROUTER_MODEL

TIMEOUT = aiohttp.ClientTimeout(total=30)
SUPPORTS_IMAGES = True


class ProviderError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


async def generate(messages: list, system_prompt: str, image_bytes: bytes = None,
                    image_mime: str = "image/jpeg", max_tokens: int = 600) -> str:
    if not OPENROUTER_API_KEY:
        raise ProviderError("no_api_key", retryable=False)

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    msgs = [{"role": "system", "content": system_prompt}]
    for m in messages[:-1] if messages else []:
        msgs.append({"role": m["role"], "content": m["content"]})

    last_content = messages[-1]["content"] if messages else ""
    if image_bytes is not None:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_uri = f"data:{image_mime};base64,{b64}"
        msgs.append({
            "role": "user",
            "content": [
                {"type": "text", "text": last_content},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        })
    elif messages:
        msgs.append({"role": messages[-1]["role"], "content": last_content})

    payload = {"model": OPENROUTER_MODEL, "messages": msgs, "max_tokens": max_tokens, "temperature": 0.7}

    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 401 or resp.status == 403:
                    raise ProviderError(f"auth_error:{resp.status}", retryable=False)
                if resp.status == 404:
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
