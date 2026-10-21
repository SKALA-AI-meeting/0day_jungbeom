"""OpenAILLM이 langchain-openai 모델 객체에 넘기는 요청 형태(네트워크 없음).

FakeLLM은 _call을 갈아 끼워 이 경로를 타지 않으므로, 실제 ChatOpenAI의 bind·bind_tools를 거쳐
만들어지는 요청 본문을 _agenerate 직전에서 잡아 검사한다.
"""

import pytest
from app.agent import intent
from app.agent.llm import OpenAILLM, Trace, Usage
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_materials",
            "description": "자료 검색",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    }
]


@pytest.fixture
def payloads(monkeypatch):
    seen: list[dict] = []

    async def agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        body = self._get_request_payload(messages, stop=stop, **kwargs)
        seen.append({k: v for k, v in body.items() if k != "messages"})
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="{}"))])

    monkeypatch.setattr(ChatOpenAI, "_agenerate", agenerate)
    return seen


async def test_request_shapes_per_role(payloads):
    llm = OpenAILLM("test-key", temperature=0.7)
    call = {"usage": Usage(), "trace": Trace("r", "s", "n")}
    messages = [HumanMessage("JSON으로 답한다")]
    await llm.ainvoke(messages, tools=TOOLS, json_mode=True, **call)  # 페르소나
    await llm.ainvoke(messages, json_mode=True, **call)  # 턴
    await llm.ainvoke(messages, schema=intent.SCHEMA, temperature=0.0, **call)  # 의도 분류
    await llm.ainvoke(messages, tools=TOOLS, **call)  # 어시스턴트

    persona, turn, classify, assistant = payloads
    assert persona["tools"][0]["function"]["name"] == "search_materials"
    assert persona["extra_body"] == {"response_format": {"type": "json_object"}}
    assert "response_format" not in persona  # 있으면 parse 경로(strict 도구 전용)로 간다
    assert persona["temperature"] == 0.7
    assert turn["response_format"] == {"type": "json_object"} and "tools" not in turn
    assert classify["response_format"]["type"] == "json_schema"
    assert classify["response_format"]["json_schema"]["schema"] == intent.SCHEMA
    assert classify["temperature"] == 0.0
    assert assistant["tools"] and "response_format" not in assistant
