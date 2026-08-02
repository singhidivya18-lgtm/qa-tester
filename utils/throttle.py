"""Rate limiting and retry for LiteLLM calls.

Spaces out LLM calls and retries transient failures (rate limits and
empty/invalid responses). The OpenRouter deepseek/deepseek-v4-flash model
allows high request rates, so spacing is kept minimal.
"""

import asyncio
import time

MIN_INTERVAL_SECONDS = 0.5
MAX_RETRIES = 3

_lock = asyncio.Lock()
_last_call = {"ts": 0.0}


async def _throttle_async():
    while True:
        async with _lock:
            now = time.monotonic()
            if now - _last_call["ts"] >= MIN_INTERVAL_SECONDS:
                _last_call["ts"] = now
                return
        await asyncio.sleep(0.3)


def _throttle_sync():
    now = time.monotonic()
    wait = MIN_INTERVAL_SECONDS - (now - _last_call["ts"])
    if wait > 0:
        time.sleep(wait)
    _last_call["ts"] = time.monotonic()


def _is_rate_limited(exc) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "rate_limit" in msg or "too many requests" in msg


def _is_retryable(exc) -> bool:
    """Retry on rate limits AND transient empty/invalid responses from the
    free OpenRouter model (HTTP 200 with an empty body -> litellm APIError
    'Unable to get json response')."""
    msg = str(exc).lower()
    if _is_rate_limited(exc):
        return True
    if "unable to get json response" in msg or "expecting value" in msg:
        return True
    if "cannot connect to host" in msg or "getaddrinfo" in msg or "connecterror" in msg:
        return True
    if "timed out" in msg or "timeout" in msg:
        return True
    return False


def install_throttle() -> None:
    """Patch litellm.completion / acompletion with throttling + retry."""
    import litellm
    import google.adk.models.lite_llm as adk_llm

    orig_async = litellm.acompletion
    orig_sync = litellm.completion

    async def patched_acompletion(*args, **kwargs):
        await _throttle_async()
        last_exc = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await orig_async(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if _is_retryable(exc):
                    await asyncio.sleep(4 * (attempt + 1))
                    continue
                raise
        raise last_exc

    def patched_completion(*args, **kwargs):
        _throttle_sync()
        last_exc = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return orig_sync(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if _is_retryable(exc):
                    time.sleep(4 * (attempt + 1))
                    continue
                raise
        raise last_exc

    litellm.acompletion = patched_acompletion
    litellm.completion = patched_completion
    if hasattr(adk_llm, "acompletion"):
        adk_llm.acompletion = patched_acompletion
    if hasattr(adk_llm, "completion"):
        adk_llm.completion = patched_completion
