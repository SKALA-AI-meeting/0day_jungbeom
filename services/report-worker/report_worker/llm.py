"""AI 활용 요약에 쓰는 LLM. gpt-4o-mini, temperature 0.

harness.md Recovery: 타임아웃 30초, 재시도 2회(1·3초) 뒤 고정 문장(FallbackText).
호출마다 사용량을 모아 reports.usage로 남긴다. 테스트는 같은 Protocol의 FakeLLM을 쓴다.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger("report_worker.llm")

TIMEOUT_SECONDS = 30
RETRY_DELAYS = (1, 3)
FALLBACK_SUMMARY = "요약을 만들지 못했습니다. 아래 호출 기록을 확인해 주세요."


@dataclass
class Completion:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


class LLM(Protocol):
    model: str

    async def complete(self, system: str, user: str) -> Completion: ...


def empty_usage(model: str) -> dict:
    return {
        "model": model,
        "llm_calls": 0,
        "retries": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "latency_ms": 0,
        "fallback_used": False,
    }


async def complete_with_retry(llm: LLM, system: str, user: str, usage: dict) -> str:
    """최초 포함 3회. 모두 실패하면 FALLBACK_SUMMARY. usage를 제자리에서 갱신한다."""
    for attempt in range(len(RETRY_DELAYS) + 1):
        if attempt:
            usage["retries"] += 1
            await asyncio.sleep(RETRY_DELAYS[attempt - 1])
        started = time.monotonic()
        usage["llm_calls"] += 1
        try:
            result = await llm.complete(system, user)
        except Exception:
            log.warning("llm call failed (attempt %d)", attempt + 1, exc_info=True)
            continue
        finally:
            usage["latency_ms"] += int((time.monotonic() - started) * 1000)
        usage["tokens_in"] += result.tokens_in
        usage["tokens_out"] += result.tokens_out
        return result.text
    usage["fallback_used"] = True
    return FALLBACK_SUMMARY


class OpenAILLM:
    def __init__(self, model: str) -> None:
        from langchain_openai import ChatOpenAI

        self.model = model
        # 재시도는 complete_with_retry가 센다(SDK 자체 재시도는 끈다)
        self._chat = ChatOpenAI(model=model, temperature=0, timeout=TIMEOUT_SECONDS, max_retries=0)

    async def complete(self, system: str, user: str) -> Completion:
        reply = await self._chat.ainvoke([("system", system), ("user", user)])
        meta = reply.usage_metadata or {}
        return Completion(
            text=str(reply.content).strip(),
            tokens_in=meta.get("input_tokens", 0),
            tokens_out=meta.get("output_tokens", 0),
        )
