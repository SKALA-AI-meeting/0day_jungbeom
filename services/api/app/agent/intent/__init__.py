"""실시간 의도 분류 공개 함수(contracts.md "의도 분류 출력 스키마"). G-F stub, agent 트랙에 인계.

api 메일박스(`services/debate.py`)가 `message` 자극마다 그래프 전에 부른다. 입력 단계는 저장된
`messages.phase`이고 카탈로그 안 전체·그 단계의 기존 안·직전 메시지 5개·자리 이름을 받는다.
모델 `MODEL_INTENT`(역할 `intent`), temperature 0, 타임아웃 10초, 재시도 없음.

G-F stub은 LLM을 부르지 않고 폴백(other·confidence low, fallback=True)만 돌려준다. 시그니처는 동결.
"""

from typing import Any, Literal, TypedDict

from app.agent.llm.base import JsonLLM

INTENTS = ("propose", "agree", "oppose", "question", "other")
SEAT_IDS = ("p1", "p2", "p3")


class IntentResult(TypedDict):
    intent: Literal["propose", "agree", "oppose", "question", "other"]
    target_option_id: str | None
    scenario_option_key: str | None
    new_option_label: str | None
    confidence: Literal["high", "low"]
    addressed_to: list[str]


class CatalogOption(TypedDict):
    scenario_option_key: str
    label: str


class ExistingOption(TypedDict):
    option_id: str
    label: str
    scenario_option_key: str | None


# OpenAI json_schema(strict) 출력 스키마
SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": list(IntentResult.__annotations__),
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "target_option_id": {"type": ["string", "null"]},
        "scenario_option_key": {"type": ["string", "null"]},
        "new_option_label": {"type": ["string", "null"]},
        "confidence": {"type": "string", "enum": ["high", "low"]},
        "addressed_to": {"type": "array", "items": {"type": "string", "enum": list(SEAT_IDS)}},
    },
}


def fallback() -> IntentResult:
    """실패·스키마 위반 때의 결과(contracts.md). 호출마다 새 dict."""
    return {
        "intent": "other",
        "target_option_id": None,
        "scenario_option_key": None,
        "new_option_label": None,
        "confidence": "low",
        "addressed_to": [],
    }


async def classify(
    llm: JsonLLM | None,
    message: str,
    *,
    phase: str,
    catalog: list[CatalogOption],
    options: list[ExistingOption],
    recent: list[dict[str, Any]],
    seats: dict[str, str],
) -> tuple[IntentResult, bool]:
    """지원자 메시지 하나의 의도. 반환 (결과, fallback).

    seats는 {자리 id: 표시 이름}, recent는 직전 메시지 [{sender, content}] 최대 5개.
    결과의 target_option_id는 options 안의 id, scenario_option_key는 catalog 안의 키만 허용한다.
    """
    return fallback(), True
