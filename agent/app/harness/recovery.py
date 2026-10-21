"""Recovery: 429 / 5xx from the model API are retried twice, then the fallback model, then the task fails."""
from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable, TypeVar

from . import runtime

T = TypeVar("T")
RETRYABLE = {429, 500, 502, 503, 504}


class RecoveryExhausted(RuntimeError):
    pass


def models() -> list[str]:
    primary = os.getenv("LLM_MODEL", "gpt-4o-mini")
    fallback = os.getenv("LLM_FALLBACK_MODEL", "gpt-4.1-mini")
    return [primary] if fallback in ("", primary) else [primary, fallback]


def status_of(e: Exception) -> int | None:
    for obj in (e, getattr(e, "response", None)):
        code = getattr(obj, "status_code", None)
        if isinstance(code, int):
            return code
    name = type(e).__name__
    if name == "RateLimitError":
        return 429
    if name in ("APITimeoutError", "APIConnectionError", "InternalServerError"):
        return 503
    return None


async def with_recovery(make: Callable[[str], Awaitable[T]], retries: int = 2) -> T:
    ctx = runtime.current()
    last: Exception | None = None
    for mi, model in enumerate(models()):
        if mi > 0 and ctx:
            ctx.tracer.note("fallback")
        for attempt in range(retries + 1):
            try:
                return await make(model)
            except Exception as e:
                if status_of(e) not in RETRYABLE:
                    raise
                last = e
                if attempt < retries:
                    if ctx:
                        ctx.tracer.note("retry")
                    await asyncio.sleep(0.8 * (attempt + 1))
    raise RecoveryExhausted(f"model calls failed after retries and fallback: {last}")
