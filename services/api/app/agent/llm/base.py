"""LLM 호출 공통부: 재시도(2회, 1·3초) → LLMUnavailable, usage 집계, LangSmith 태그.

docs/common/harness.md Recovery·Observability 행. 모델은 역할별(roles.py)이고 대체 모델은 없다.
재시도까지 실패하면 LLMUnavailable을 올리고, 호출한 노드가 규칙 폴백(고정 문장)으로 간다.
"""

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage

log = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"
TIMEOUT_SECONDS = 30.0
RETRY_DELAYS = (1.0, 3.0)


class LLMUnavailable(Exception):
    """최초 포함 3회 모두 실패. 규칙 폴백 신호."""


@dataclass
class Usage:
    """agent_runs.usage 한 벌. 실행(run) 하나 동안 노드들이 함께 더한다."""

    llm_calls: int = 0
    retries: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    tool_calls: int = 0

    def record(self, message: AIMessage, latency_ms: int) -> None:
        self.llm_calls += 1
        self.latency_ms += latency_ms
        meta = message.usage_metadata or {}
        self.tokens_in += meta.get("input_tokens", 0)
        self.tokens_out += meta.get("output_tokens", 0)

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class Trace:
    """LangSmith trace에 붙일 run_id·session_id·노드 이름."""

    run_id: str
    session_id: str
    node: str

    def config(self) -> dict[str, Any]:
        meta = {"run_id": self.run_id, "session_id": self.session_id, "node": self.node}
        return {"run_name": self.node, "tags": [f"run_id:{self.run_id}"], "metadata": meta}


class JsonLLM(Protocol):
    """JSON 스키마 구조화 출력 호출(agent-spike 7절). 의도 분류 등 결정적 판정 역할이 쓴다.

    구현은 호출마다 {role, model, latency_ms, tokens_in, tokens_out, cost_usd}를 기록한다.
    """

    async def complete_json(
        self,
        role: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        timeout: float,
        temperature: float,
    ) -> dict[str, Any]: ...


class BaseLLM:
    """재시도와 usage 집계. 실제 호출(_call)만 구현체가 정한다."""

    model: str = MODEL
    retry_delays: Sequence[float] = RETRY_DELAYS

    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
        *,
        usage: Usage,
        trace: Trace,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        temperature: float = 0.7,
    ) -> AIMessage:
        last: Exception | None = None
        for attempt in range(len(self.retry_delays) + 1):
            if attempt:
                usage.retries += 1
                await asyncio.sleep(self.retry_delays[attempt - 1])
            started = time.monotonic()
            try:
                message = await self._call(
                    list(messages),
                    tools=tools,
                    json_mode=json_mode,
                    temperature=temperature,
                    config=trace.config(),
                )
            except Exception as exc:  # 타임아웃·HTTP 오류·응답 파싱 실패 모두 재시도 대상
                last = exc
                log.warning("llm call failed (%s, attempt %d): %r", trace.node, attempt + 1, exc)
                continue
            usage.record(message, int((time.monotonic() - started) * 1000))
            return message
        raise LLMUnavailable(f"{type(last).__name__}: {last}")

    async def _call(
        self,
        messages: list[BaseMessage],
        *,
        tools: list[dict[str, Any]] | None,
        json_mode: bool,
        temperature: float,
        config: dict[str, Any],
    ) -> AIMessage:
        raise NotImplementedError
