"""평가 에이전트 LLM 호출(`MODEL_EVALUATOR`, temperature 0.1, JSON 출력).

전송 오류·타임아웃은 재시도 2회(1·3초) 뒤 LLMUnavailable로 올린다. 평가는 폴백 문장이 없다:
아무것도 저장하지 않고 작업을 실패시켜 큐 재시도(attempt+1)에 맡긴다(worker-infra/design.md 4단계).
호출마다 사용량을 모아 reports.usage로 남긴다. 테스트는 같은 Protocol의 FakeLLM을 쓴다.
"""

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from report_worker.config import (
    EVALUATOR_RETRY_DELAYS,
    EVALUATOR_TEMPERATURE,
    EVALUATOR_TIMEOUT,
    key_for,
)

log = logging.getLogger("report_worker.llm")


class LLMUnavailable(Exception):
    """최초 포함 3회 모두 전송 실패·타임아웃. 큐 재시도 신호."""


@dataclass
class Completion:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


class LLM(Protocol):
    model: str
    temperature: float

    async def complete(self, system: str, user: str) -> Completion: ...


def empty_usage(model: str) -> dict:
    return {
        "model": model,
        "llm_calls": 0,
        "element_retries": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "latency_ms": 0,
    }


async def complete_tracked(llm: LLM, system: str, user: str, usage: dict) -> str:
    started = time.monotonic()
    usage["llm_calls"] += 1
    try:
        result = await llm.complete(system, user)
    finally:
        usage["latency_ms"] += int((time.monotonic() - started) * 1000)
    usage["tokens_in"] += result.tokens_in
    usage["tokens_out"] += result.tokens_out
    return result.text


class OpenAILLM:
    def __init__(self, model: str, env: Mapping[str, str]) -> None:
        from langchain_openai import ChatOpenAI

        key, base_url = key_for(model, env)
        self.model = model
        self.temperature = EVALUATOR_TEMPERATURE
        # 재시도는 complete가 센다(SDK 자체 재시도는 끈다)
        self._chat = ChatOpenAI(
            model=model,
            api_key=key,
            base_url=base_url,
            temperature=self.temperature,
            timeout=EVALUATOR_TIMEOUT,
            max_retries=0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    async def complete(self, system: str, user: str) -> Completion:
        last: Exception | None = None
        for attempt in range(len(EVALUATOR_RETRY_DELAYS) + 1):
            if attempt:
                await asyncio.sleep(EVALUATOR_RETRY_DELAYS[attempt - 1])
            try:
                reply = await self._chat.ainvoke([("system", system), ("user", user)])
            except Exception as exc:
                log.warning("evaluator llm failed (attempt %d): %r", attempt + 1, exc)
                last = exc
                continue
            meta = reply.usage_metadata or {}
            return Completion(
                text=str(reply.content).strip(),
                tokens_in=meta.get("input_tokens", 0),
                tokens_out=meta.get("output_tokens", 0),
            )
        raise LLMUnavailable(f"evaluator llm failed after retries: {last!r}")
