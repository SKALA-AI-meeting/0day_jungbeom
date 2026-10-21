"""LLM 래퍼(역할별 모델·재시도 → LLMUnavailable), FakeLLM, usage 집계, LangSmith 태그.

G-F에서 be-foundation이 설정(roles.py)만 정하고 agent 트랙에 인계한다.
"""

from app.agent.llm.base import MODEL, BaseLLM, JsonLLM, LLMUnavailable, Trace, Usage
from app.agent.llm.fake import FakeCall, FakeLLM, tool_call
from app.agent.llm.openai import OpenAILLM
from app.agent.llm.roles import (
    ROLE_CONFIG,
    ROLES,
    RoleConfig,
    key_for,
    make_llm,
    model_for,
    role_config,
)

__all__ = [
    "MODEL",
    "BaseLLM",
    "FakeCall",
    "FakeLLM",
    "JsonLLM",
    "LLMUnavailable",
    "OpenAILLM",
    "ROLES",
    "ROLE_CONFIG",
    "RoleConfig",
    "Trace",
    "Usage",
    "key_for",
    "make_llm",
    "model_for",
    "role_config",
    "tool_call",
]
