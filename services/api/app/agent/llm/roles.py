"""역할별 모델·키 선택과 호출 설정(docs/agent/design.md "역할별 모델"). G-F 동결.

규칙은 여기 한 곳이다.

- 역할 5개는 env `MODEL_INTENT`·`MODEL_TURN`·`MODEL_PERSONA`·`MODEL_ASSISTANT`·`MODEL_EVALUATOR`를
  읽고 비어 있으면 `OPENAI_MODEL`(기본 gpt-4o-mini)을 쓴다. 옛 `MODEL_COLLEAGUE`·`MODEL_MANAGER`·
  `MODEL_OBSERVE`·`MODEL_REPORT`는 읽지 않는다.
- 키는 모델 id로 고른다: gpt-4o-mini → OPENAI_API_KEY(제한 키), 그 외 gpt-* →
  OPENAI_API_KEY_PERSONAL, gemini-* → GEMINI_API_KEY(OpenAI 호환 엔드포인트). 대체 모델 없음.
- 재시도는 역할 표의 횟수(기본 2회, 의도 분류는 0회) 뒤 LLMUnavailable → 호출한 노드의 규칙 폴백.
  report-worker는 같은 규칙의 사본을 쓴다(평가 역할 `evaluator`).
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from app.agent.llm.base import MODEL, RETRY_DELAYS, BaseLLM
from app.agent.llm.openai import OpenAILLM
from app.config import get_settings

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


@dataclass(frozen=True)
class RoleConfig:
    env: str
    timeout: float  # 초. 호출 한 번의 상한
    retries: int  # 최초 호출 뒤 재시도 횟수
    temperature: float


ROLE_CONFIG: dict[str, RoleConfig] = {
    "intent": RoleConfig("MODEL_INTENT", timeout=10.0, retries=0, temperature=0.0),
    "turn": RoleConfig("MODEL_TURN", timeout=15.0, retries=2, temperature=0.0),
    "persona": RoleConfig("MODEL_PERSONA", timeout=20.0, retries=2, temperature=0.7),
    "assistant": RoleConfig("MODEL_ASSISTANT", timeout=30.0, retries=2, temperature=0.3),
    "evaluator": RoleConfig("MODEL_EVALUATOR", timeout=60.0, retries=2, temperature=0.1),
}
ROLES = tuple(ROLE_CONFIG)


def role_config(role: str) -> RoleConfig:
    if role not in ROLE_CONFIG:
        raise ValueError(f"unknown llm role: {role}")
    return ROLE_CONFIG[role]


def model_for(role: str, env: Mapping[str, str] | None = None) -> str:
    config = role_config(role)
    env = _env(env)
    return env.get(config.env) or env.get("OPENAI_MODEL") or MODEL


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
    """그 역할의 LLM 래퍼(역할 표의 타임아웃·재시도).

    env를 주지 않으면 infra/.env를 읽은 프로세스 환경을 쓴다.
    """
    config = role_config(role)
    model = model_for(role, env)
    key, base_url = key_for(model, env)
    delays = tuple(RETRY_DELAYS[: config.retries])
    return OpenAILLM(key, model, timeout=config.timeout, retry_delays=delays, base_url=base_url)


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    if env is not None:
        return env
    get_settings()  # .env.local → .env를 프로세스 환경에 읽어 둔다
    return os.environ
