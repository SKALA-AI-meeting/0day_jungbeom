"""역할별 모델·키 선택(docs/decisions.md 2026-10-20 "역할별 모델과 상향 규칙"). 규칙은 여기 한 곳.

- 역할 5개는 env `MODEL_<역할>`을 읽고 비어 있으면 `OPENAI_MODEL`(기본 gpt-4o-mini)을 쓴다.
- 키는 모델 id로 고른다: gpt-4o-mini → OPENAI_API_KEY(제한 키),
  그 외 gpt-* → OPENAI_API_KEY_PERSONAL, gemini-* → GEMINI_API_KEY(Google의 OpenAI 호환
  엔드포인트라 같은 클라이언트를 쓴다).
- 재시도 2회 후 LLMUnavailable(규칙 폴백)은 모델과 무관하게 BaseLLM이 그대로 한다. 대체 모델 없음.
"""

import os
from collections.abc import Mapping

from app.agent.llm.base import MODEL, BaseLLM
from app.agent.llm.openai import OpenAILLM
from app.config import get_settings

ROLES = ("colleague", "manager", "observe", "assistant", "report")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def model_for(role: str, env: Mapping[str, str] | None = None) -> str:
    if role not in ROLES:
        raise ValueError(f"unknown llm role: {role}")
    env = _env(env)
    return env.get(f"MODEL_{role.upper()}") or env.get("OPENAI_MODEL") or MODEL


def key_for(model: str, env: Mapping[str, str] | None = None) -> tuple[str, str | None]:
    """(api_key, base_url). 키가 비어 있으면 설정 오류로 멈춘다(다른 키로 몰래 바꾸지 않는다)."""
    env = _env(env)
    if model == MODEL:
        name, base_url = "OPENAI_API_KEY", None
    elif model.startswith("gpt-"):
        name, base_url = "OPENAI_API_KEY_PERSONAL", None
    elif model.startswith("gemini-"):
        name, base_url = "GEMINI_API_KEY", GEMINI_BASE_URL
    else:
        raise ValueError(f"no key rule for model: {model}")
    key = env.get(name, "")
    if not key:
        raise ValueError(f"{name} is required for model {model}")
    return key, base_url


def make_llm(role: str, env: Mapping[str, str] | None = None) -> BaseLLM:
    """그 역할의 LLM 래퍼. env를 주지 않으면 infra/.env.local·.env를 읽은 프로세스 환경을 쓴다."""
    model = model_for(role, env)
    key, base_url = key_for(model, env)
    return OpenAILLM(key, model, base_url=base_url)


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    if env is not None:
        return env
    get_settings()  # .env.local → .env를 프로세스 환경에 읽어 둔다
    return os.environ
