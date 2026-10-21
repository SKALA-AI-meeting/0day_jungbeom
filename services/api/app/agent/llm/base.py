"""LLM 호출 공통부: 재시도(역할별, 기본 2회 1·3초) → LLMUnavailable, usage·비용 집계, LangSmith
태그.

docs/common/harness.md Recovery·Observability 행. 모델은 역할별(roles.py)이고 대체 모델은 없다.
재시도까지 실패하면 LLMUnavailable을 올리고, 호출한 노드가 규칙 폴백(고정 문장)으로 간다.
비용은 이 파일의 단가 표 한 곳에서 계산한다(contracts.md "세션 메일박스" 비용, R5-11).
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

log = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"
TIMEOUT_SECONDS = 30.0
RETRY_DELAYS = (1.0, 3.0)
DEFAULT_TEMPERATURE = 0.7

# 1M 토큰당 달러(입력, 출력). 표에 없는 모델은 gpt-4o-mini 단가로 근사한다(관측용).
PRICES_PER_M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "fake": (0.0, 0.0),
}


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICES_PER_M.get(model, PRICES_PER_M[MODEL])
    return tokens_in * price_in / 1e6 + tokens_out * price_out / 1e6


class LLMUnavailable(Exception):
    """최초 포함 모든 시도가 실패. 규칙 폴백 신호."""


def parse_fault(value: str | None) -> dict[str, int]:
    """`LLM_FAULT=<role>:timeout:<N>` → {role: N}. 형식이 다르면 무시한다(e2e 장애 주입 전용)."""
    parts = (value or "").strip().split(":")
    if len(parts) == 3 and parts[1] == "timeout" and parts[2].isdigit():
        return {parts[0]: int(parts[2])}
    return {}


# 프로세스 시작 때 한 번 읽는다. 남은 횟수는 프로세스 메모리에서 줄어든다.
FAULTS = parse_fault(os.environ.get("LLM_FAULT"))


def take_fault(role: str | None) -> bool:
    if role is None or FAULTS.get(role, 0) <= 0:
        return False
    FAULTS[role] -= 1
    return True


@dataclass
class Usage:
    """agent_runs.usage 한 벌. 실행(run) 하나 동안 노드들이 함께 더한다."""

    llm_calls: int = 0
    retries: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    tool_calls: int = 0

    def record(self, message: AIMessage, latency_ms: int, model: str = MODEL) -> None:
        self.llm_calls += 1
        self.latency_ms += latency_ms
        meta = message.usage_metadata or {}
        tokens_in = meta.get("input_tokens", 0)
        tokens_out = meta.get("output_tokens", 0)
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.cost_usd += cost_usd(model, tokens_in, tokens_out)

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    def as_dict(self) -> dict[str, Any]:
        body = asdict(self)
        body["cost_usd"] = round(self.cost_usd, 6)
        return body


@dataclass(frozen=True)
class Trace:
    """LangSmith trace에 붙일 run_id·session_id·노드 이름.

    메타데이터 키는 `agent_run_id`다(`run_id`를 쓰면 LangGraph가 같은 run_id 재호출을 끝난 실행으로
    본다, docs/agent/design.md "재실행 멱등").
    """

    run_id: str
    session_id: str
    node: str

    def config(self) -> dict[str, Any]:
        meta = {"agent_run_id": self.run_id, "session_id": self.session_id, "node": self.node}
        return {"run_name": self.node, "tags": [f"agent_run_id:{self.run_id}"], "metadata": meta}


@dataclass
class CallRecord:
    """JSON 호출 한 번의 관측 값(message_intents의 latency_ms·model, 비용 누계용)."""

    role: str
    model: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    ok: bool
    error: str | None = None


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
    temperature: float = DEFAULT_TEMPERATURE
    role: str | None = None  # make_llm이 넣는다(LLM_FAULT 대상 판정)

    @property
    def records(self) -> list[CallRecord]:
        """complete_json 호출 기록(오래된 것부터). 인스턴스마다 따로 둔다."""
        return self.__dict__.setdefault("_records", [])

    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
        *,
        usage: Usage,
        trace: Trace,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        temperature: float | None = None,
        schema: dict[str, Any] | None = None,
    ) -> AIMessage:
        """temperature를 주지 않으면 역할 표(roles.py ROLE_CONFIG) 값(make_llm이 넣음)을 쓴다."""
        temp = self.temperature if temperature is None else temperature
        last: Exception | None = None
        for attempt in range(len(self.retry_delays) + 1):
            if attempt:
                usage.retries += 1
                await asyncio.sleep(self.retry_delays[attempt - 1])
            started = time.monotonic()
            try:
                # 장애 주입: 시도 1회를 실제 호출 없이 타임아웃으로(재시도·폴백 경로는 그대로)
                if take_fault(self.role):
                    raise TimeoutError("LLM_FAULT")
                message = await self._call(
                    list(messages),
                    tools=tools,
                    json_mode=json_mode or schema is not None,
                    temperature=temp,
                    config=trace.config(),
                    schema=schema,
                )
            except Exception as exc:  # 타임아웃·HTTP 오류·응답 파싱 실패 모두 재시도 대상
                last = exc
                log.warning("llm call failed (%s, attempt %d): %r", trace.node, attempt + 1, exc)
                continue
            usage.record(message, int((time.monotonic() - started) * 1000), self.model)
            return message
        raise LLMUnavailable(f"{type(last).__name__}: {last}")

    async def complete_json(
        self,
        role: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        timeout: float = TIMEOUT_SECONDS,
        temperature: float | None = None,
        usage: Usage | None = None,
        trace: Trace | None = None,
    ) -> dict[str, Any]:
        """JsonLLM 구현. 응답이 JSON 객체가 아니면 ValueError(호출자가 폴백).

        타임아웃은 래퍼 생성 때 역할 표 값으로 정해진다(timeout 인자는 Protocol 호환용).
        """
        local = Usage()
        started = time.monotonic()
        try:
            message = await self.ainvoke(
                [SystemMessage(system), HumanMessage(user)],
                usage=local,
                trace=trace or Trace("-", "-", role),
                temperature=temperature,
                schema=schema,
            )
        except LLMUnavailable as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            self.records.append(CallRecord(role, self.model, elapsed, 0, 0, 0.0, False, str(exc)))
            if usage is not None:
                usage.retries += local.retries
            raise
        self.records.append(
            CallRecord(
                role,
                self.model,
                local.latency_ms,
                local.tokens_in,
                local.tokens_out,
                local.cost_usd,
                True,
            )
        )
        if usage is not None:
            for name in ("llm_calls", "retries", "tokens_in", "tokens_out", "latency_ms"):
                setattr(usage, name, getattr(usage, name) + getattr(local, name))
            usage.cost_usd += local.cost_usd
        return parse_json_object(str(message.content))

    async def _call(
        self,
        messages: list[BaseMessage],
        *,
        tools: list[dict[str, Any]] | None,
        json_mode: bool,
        temperature: float,
        config: dict[str, Any],
        schema: dict[str, Any] | None = None,
    ) -> AIMessage:
        raise NotImplementedError


def parse_json_object(text: str) -> dict[str, Any]:
    """모델 출력에서 JSON 객체 하나를 읽는다(코드 펜스·앞뒤 글 허용). 아니면 ValueError."""
    body = text.strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no json object")
    value = json.loads(body[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("json is not an object")
    return value
