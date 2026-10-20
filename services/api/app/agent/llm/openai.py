"""gpt-4o-mini(langchain-openai). SDK 자체 재시도는 끄고 BaseLLM의 재시도 규칙(2회)만 쓴다.

LangSmith 트레이싱은 환경변수(LANGCHAIN_TRACING_V2·LANGCHAIN_API_KEY·LANGCHAIN_PROJECT)로 켜고,
호출마다 Trace.config()의 run_id 태그·메타데이터가 붙는다.
"""

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

from app.agent.llm.base import MODEL, RETRY_DELAYS, TIMEOUT_SECONDS, BaseLLM


class OpenAILLM(BaseLLM):
    def __init__(
        self,
        api_key: str,
        model: str = MODEL,
        timeout: float = TIMEOUT_SECONDS,
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
    ) -> None:
        self.model = model
        self.retry_delays = retry_delays
        self._chat = ChatOpenAI(model=model, api_key=api_key, timeout=timeout, max_retries=0)

    async def _call(
        self,
        messages: list[BaseMessage],
        *,
        tools: list[dict[str, Any]] | None,
        json_mode: bool,
        temperature: float,
        config: dict[str, Any],
    ) -> AIMessage:
        kwargs: dict[str, Any] = {"temperature": temperature}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        runnable = self._chat.bind_tools(tools, **kwargs) if tools else self._chat.bind(**kwargs)
        return await runnable.ainvoke(messages, config=config)
