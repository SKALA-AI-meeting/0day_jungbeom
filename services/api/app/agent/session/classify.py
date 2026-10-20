"""respond 앞 분류: 수신자(결정적 규칙)와 kind(LLM 구조화 출력, 실패하면 규칙).

결과 {recipient, kind, instruction?, related_card?}는 messages.meta.classification으로 저장되고
observe·지표 계산이 읽는다(docs/agent/design.md respond 행).
"""

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import BaseLLM, LLMUnavailable, Trace, Usage

KINDS = ("question", "instruction", "redivide", "progress_query", "fix_request", "other")

# team 채널에서 이름·호칭이 없을 때 팀장에게 가는 주제: 과제 범위·마감·보고·대상 변경
_MANAGER_TOPIC = re.compile(r"마감|기한|보고|범위|대상\s*(을|를|이|은)?\s*(바꾸|변경|바뀌)|일정")

CLASSIFY_SYSTEM = """주담당이 팀 채팅에 보낸 메시지 하나를 분류한다. JSON 객체 하나만 출력한다.
형식: {"kind": "<kind>", "instruction": "<지시 요지 또는 null>", "part_no": <1~5 또는 null>}
kind:
- question: 정보·의견·사실을 묻는다
- instruction: 동료에게 작업 방향이나 내용을 지시·요청한다(담당은 그대로)
- redivide: 파트 담당을 새로 나누거나 바꾼다
- progress_query: 동료 파트의 진행 상황을 묻는다
- fix_request: 동료 파트의 문제(정책 위반 등)를 지적하며 고쳐 달라고 한다
- other: 그 밖(인사, 잡담, 확인 응답 등)
instruction은 kind가 instruction·redivide일 때만 한 문장으로 채운다.
part_no는 지시가 가리키는 파트."""


def recipient(channel: str, content: str, scenario: dict[str, Any]) -> str:
    """dm → 동료. team → ① 동료 이름 ② 팀장 호칭·이름
    ③ 범위·마감·보고·대상 변경이면 팀장, 그 외 동료."""
    if channel != "team":
        return "colleague"
    company = scenario.get("company") or {}
    colleague = (company.get("colleague") or {}).get("name", "")
    manager = (company.get("manager") or {}).get("name", "")
    if colleague and (colleague in content or colleague[1:] in content):
        return "colleague"
    if "팀장" in content or (manager and (manager in content or manager[1:] in content)):
        return "manager"
    return "manager" if _MANAGER_TOPIC.search(content) else "colleague"


def rule_kind(content: str) -> str:
    """LLM이 실패했을 때의 kind."""
    if re.search(r"진행|어디까지|얼마나\s*(됐|되)", content):
        return "progress_query"
    if re.search(r"(나누|분담|맡아|맡기|담당)", content):
        return "redivide"
    if re.search(r"(고쳐|수정해|위반|빼\s*주)", content):
        return "fix_request"
    if re.search(r"(해\s*주세요|해줘|해 줘|로\s*가요|바꿔)", content):
        return "instruction"
    if "?" in content or re.search(r"(나요|까요|어요\?|인가요|있어요)$", content.strip()):
        return "question"
    return "other"


async def classify(
    llm: BaseLLM,
    content: str,
    channel: str,
    scenario: dict[str, Any],
    *,
    usage: Usage,
    trace: Trace,
    current_card: str | None,
) -> tuple[dict[str, Any], bool]:
    """(classification, fallback_used)."""
    result: dict[str, Any] = {
        "recipient": recipient(channel, content, scenario),
        "kind": "other",
        "instruction": None,
        "related_card": current_card,
    }
    try:
        message = await llm.ainvoke(
            [SystemMessage(CLASSIFY_SYSTEM), HumanMessage(content)],
            usage=usage,
            trace=trace,
            json_mode=True,
            temperature=0,
        )
        parsed = json.loads(str(message.content))
        kind = parsed.get("kind")
        result["kind"] = kind if kind in KINDS else "other"
        if result["kind"] in ("instruction", "redivide") and parsed.get("instruction"):
            result["instruction"] = str(parsed["instruction"])
            result["part_no"] = parsed.get("part_no")
        return result, False
    except (LLMUnavailable, ValueError, AttributeError):
        result["kind"] = rule_kind(content)
        if result["kind"] in ("instruction", "redivide"):
            result["instruction"] = content
        return result, True
