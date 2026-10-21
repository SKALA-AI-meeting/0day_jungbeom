"""OpenAI 호환 Chat Completions(langchain-openai). SDK 자체 재시도는 끄고 BaseLLM 재시도만 쓴다.

LangSmith 트레이싱은 환경변수(LANGCHAIN_TRACING_V2·LANGCHAIN_API_KEY·LANGCHAIN_PROJECT)로 켜고,
호출마다 Trace.config()의 agent_run_id 태그·메타데이터가 붙는다. schema를 주면 json_schema(strict)
구조화 출력, json_mode만 주면 json_object를 쓴다.
"""

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

from app.agent.llm.base import DEFAULT_TEMPERATURE, MODEL, RETRY_DELAYS, TIMEOUT_SECONDS, BaseLLM


class OpenAILLM(BaseLLM):
    def __init__(
        self,
        api_key: str,
        model: str = MODEL,
        timeout: float = TIMEOUT_SECONDS,
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
        base_url: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> None:
        self.model = model
        self.retry_delays = retry_delays
        self.temperature = temperature
        # base_url은 OpenAI 호환 엔드포인트(gemini-*)일 때만 준다(llm/roles.py)
        self._chat = ChatOpenAI(
            model=model, api_key=api_key, timeout=timeout, max_retries=0, base_url=base_url
        )

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
        kwargs: dict[str, Any] = {"temperature": temperature}
        if schema is not None and not tools:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema, "strict": True},
            }
        elif json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        runnable = self._chat.bind_tools(tools, **kwargs) if tools else self._chat.bind(**kwargs)
        return await runnable.ainvoke(messages, config=config)
