"""respond 앞 분류: 수신자(결정적 규칙)와 kind 등(LLM 구조화 출력, 실패하면 규칙).

저장되는 결과 {recipient, kind, instruction?, related_card?, reply_to_doc?}는 messages.meta.
classification이 되고 observe·지표 계산과 api의 보고 감지(kind=report)가 읽는다(docs/agent/
design.md respond 행). 그 밖의 필드(decision·parts·instructions·part_no·wants_revision·
judgment_request·asks_my_part)는 그래프 안에서만 쓴다.
"""

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import BaseLLM, LLMUnavailable, Trace, Usage

KINDS = (
    "question",
    "instruction",
    "redivide",
    "progress_query",
    "doc_feedback",
    "report",
    "other",
)
DECISIONS = ("decide", "ask", "other")
ASSIGNEES = ("candidate", "colleague", "both")
SAVED_KEYS = ("recipient", "kind", "instruction", "related_card", "reply_to_doc")

# team 채널에서 이름·호칭이 없을 때 팀장에게 가는 주제: 과제 범위·마감·보고·요구사항 변경
_MANAGER_TOPIC = re.compile(r"마감|기한|보고|범위|대상\s*(을|를|이|은)?\s*(바꾸|변경|바뀌)|일정")

CLASSIFY_SYSTEM = """주담당이 팀 메신저에 보낸 메시지 하나를 분류한다. JSON 객체 하나만 출력한다.
형식:
{"kind": "<kind>", "decision": "decide|ask|other", "parts": {"1": "candidate|colleague|both", ...}
또는 null,
 "instructions": [{"part_no": <1~5 또는 null>, "text": "<지시 요지 한 문장>", "keywords": ["<핵심어
 1~2개>"]}],
 "part_no": <1~5 또는 null>, "related_card": "<카드 id 또는 null>", "wants_revision": true|false,
 "judgment_request": true|false, "asks_my_part": <1~5 또는 null>}
kind:
- question: 정보·의견·사실을 묻는다
- instruction: 동료에게 작업 방향·내용을 지시·요청한다(담당은 그대로)
- redivide: 파트 담당을 나누거나 바꾼다(처음 나누는 것 포함)
- progress_query: 동료 파트의 진행 상황을 묻는다
- doc_feedback: 동료가 보낸 문서에 대한 의견(문서 답글 포함)
- report: 팀장에게 팀 결과(누가 무엇을 했고 어디까지 됐는지)를 보고한다
- other: 그 밖(인사, 잡담, 확인 응답 등)
decision: 분업을 정했으면 decide(parts에 말한 담당을 적는다. candidate=주담당, colleague=동료,
both=같이),
  동료에게 어떻게 나눌지 되물으면 ask, 분업과 무관하면 other.
instructions: 동료에게 하는 작업 지시를 파트별로 나눠 적는다. keywords는 동료 문서에 드러나야 할
핵심어다.
part_no: 진행 질문·문서 의견이 가리키는 파트. related_card: [카드 목록] 중 이 메시지가 답하거나 이어
가는 카드.
wants_revision: 문서 의견이 고쳐 달라는 요청이면 true. judgment_request: 팀장에게 정답·판단(뭘 쓰면
되나, 이게
맞나, 어느 쪽이 나은가)을 묻는 것이면 true. asks_my_part: 주담당 자신의 파트 문서 내용을 동료·팀장이
보고 있는지
묻는 것이면 그 파트 번호."""


def recipient(channel: str, content: str, scenario: dict[str, Any]) -> str:
    """dm → 동료, manager_dm → 팀장. team → ① 동료 이름 ② 팀장 호칭·이름
    ③ 범위·마감·보고·대상 변경이면 팀장, 그 외 동료."""
    if channel == "dm":
        return "colleague"
    if channel == "manager_dm":
        return "manager"
    company = scenario.get("company") or {}
    colleague = (company.get("colleague") or {}).get("name", "")
    manager = (company.get("manager") or {}).get("name", "")
    if colleague and (colleague in content or colleague[1:] in content):
        return "colleague"
    if "팀장" in content or (manager and (manager in content or manager[1:] in content)):
        return "manager"
    return "manager" if _MANAGER_TOPIC.search(content) else "colleague"


_SENTENCE = re.compile(r"[^.!?。\n]+[.!?。]*")
# 물음표가 없어도(끝에 마침표를 찍어도) 묻는 말로 보는 끝맺음과 의문사
_ASK_END = re.compile(
    r"(나요|까요|인가요|건가요|는가요|던가요|습니까|ㄹ까|을까|는지요|되죠|맞죠|되나|하나)$"
)
# 사실 확인 요청("4번 완료했는지 알려 주세요"): 결과 단어가 있어도 보고가 아니다
_ASK_REQUEST = re.compile(
    r"(는지|은지|인지|건지|했는지|됐는지|었는지)\s*.{0,8}(알려|말해|확인해|봐)\s*주"
)
_ASK_WORD = re.compile(r"어디까지|언제|얼마나|무엇|뭐가|뭘|어떻게|왜|어느")
_PROGRESS = re.compile(r"진행|어디까지|얼마나\s*(됐|되)")
_RESULT = re.compile(r"썼|했|완료|비어|됐|맡았|남았|못\s*했|아직|넣었|합쳤")


def sentences(content: str) -> list[str]:
    return [m.group(0).strip() for m in _SENTENCE.finditer(content) if m.group(0).strip()]


def is_question_sentence(sentence: str) -> bool:
    if sentence.rstrip().endswith("?"):
        return True
    body = sentence.rstrip(" .!。~")
    return bool(_ASK_END.search(body) or _ASK_WORD.search(body) or _ASK_REQUEST.search(body))


def is_question(content: str) -> bool:
    """문장마다 보고, 묻는 문장만 있는 메시지(결과를 진술한 문장이 없음)."""
    parts = sentences(content)
    return bool(parts) and all(is_question_sentence(p) for p in parts)


def states_result(content: str) -> bool:
    """묻지 않는 문장 중 결과(누가 썼다·완료·비어 있다)를 진술한 문장이 있는가. 보고와 질문이
    섞인 메시지("1~3번은 제가 썼어요. 이대로 제출해도 될까요?")도 보고로 남는다."""
    return any(_RESULT.search(p) for p in sentences(content) if not is_question_sentence(p))


def is_progress_query(content: str) -> bool:
    """진행을 묻는 문장이 있고 결과 진술은 없음("진행했고"처럼 단어만 든 보고는 조회가 아니다)."""
    asks = [p for p in sentences(content) if is_question_sentence(p) and _PROGRESS.search(p)]
    return bool(asks) and not states_result(content)


def rule_kind(content: str, *, report_requested: bool = False, channel: str = "team") -> str:
    """LLM이 실패했을 때의 kind. 보고(종료 신호)는 결과를 진술한 메시지만 인정한다."""
    if report_requested and channel in ("team", "manager_dm") and states_result(content):
        return "report"
    if is_progress_query(content):
        return "progress_query"
    if re.search(r"(나누|분담|맡아|맡기|담당)", content):
        return "redivide"
    if is_question(content):  # 확인 요청("…했는지 확인해 주세요")은 지시보다 질문으로
        return "question"
    if re.search(r"(해\s*주세요|해줘|해 줘|로\s*가요|바꿔)", content):
        return "instruction"
    return "other"


def _cards_block(cards: list[dict[str, Any]], current_card: str | None) -> str:
    lines = [f"- {c['card_id']}: {c.get('name') or c.get('situation') or ''}" for c in cards]
    head = f"열린 카드: {current_card or '없음'}"
    return "[카드 목록] (지금까지 나온 카드)\n" + head + ("\n" + "\n".join(lines) if lines else "")


def _parts(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    parts = {str(k): v for k, v in raw.items() if v in ASSIGNEES}
    return parts or None


def _instructions(raw: Any) -> list[dict[str, Any]]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        part = item.get("part_no")
        out.append(
            {
                "part_no": int(part)
                if isinstance(part, int | str) and str(part).isdigit()
                else None,
                "text": str(item["text"]),
                "keywords": [str(k) for k in item.get("keywords") or [] if str(k).strip()],
            }
        )
    return out


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | str) and str(value).isdigit() else None


async def classify(
    llm: BaseLLM,
    content: str,
    channel: str,
    scenario: dict[str, Any],
    *,
    usage: Usage,
    trace: Trace,
    current_card: str | None,
    fired_cards: list[dict[str, Any]] | None = None,
    reply_to_doc: dict[str, Any] | None = None,
    report_requested: bool = False,
    use_llm: bool = True,
) -> tuple[dict[str, Any], bool]:
    """(classification, fallback_used). 저장 키는 SAVED_KEYS, 나머지는 그래프 안에서만 쓴다."""
    fired = fired_cards or []
    known = {c["card_id"] for c in fired}
    result: dict[str, Any] = {
        "recipient": recipient(channel, content, scenario),
        "kind": "other",
        "instruction": None,
        "related_card": current_card,
        "reply_to_doc": reply_to_doc,
        "decision": "other",
        "parts": None,
        "instructions": [],
        "part_no": None,
        "wants_revision": False,
        "judgment_request": False,
        "asks_my_part": None,
    }
    channel_name = {"team": "팀 채널", "dm": "동료 DM", "manager_dm": "팀장 DM"}.get(
        channel, channel
    )
    reply = (
        f"\n(문서 답글: {reply_to_doc.get('part_no')}번 v{reply_to_doc.get('version')})"
        if reply_to_doc
        else ""
    )
    human = f"{_cards_block(fired, current_card)}\n\n[메시지] ({channel_name}){reply}\n{content}"
    try:
        if not use_llm:  # 세션 예산 소진: 규칙 분류
            raise LLMUnavailable("token_budget_exhausted")
        message = await llm.ainvoke(
            [SystemMessage(CLASSIFY_SYSTEM), HumanMessage(human)],
            usage=usage,
            trace=trace,
            json_mode=True,
            temperature=0,
        )
        parsed = json.loads(str(message.content))
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
    except (LLMUnavailable, ValueError):
        kind = rule_kind(content, report_requested=report_requested, channel=channel)
        if reply_to_doc:
            kind = "doc_feedback"
        result["kind"] = kind
        if kind in ("instruction", "redivide"):
            result["instruction"] = content
            result["instructions"] = [{"part_no": None, "text": content, "keywords": []}]
        return result, True

    kind = parsed.get("kind")
    result["kind"] = kind if kind in KINDS else "other"
    if result["kind"] == "report" and not states_result(content):
        # 보고는 세션을 끝내는 신호라 결과 진술 없이 묻기만 한 메시지는 보고로 받지 않는다
        result["kind"] = "progress_query" if is_progress_query(content) else "question"
    if result["kind"] == "report" and channel == "team":
        result["recipient"] = "manager"  # 팀 채널 보고는 동료 이름이 들어가도 팀장에게 한 말이다
    if reply_to_doc and result["kind"] in ("other", "question", "instruction"):
        result["kind"] = "doc_feedback"
    decision = parsed.get("decision")
    result["decision"] = decision if decision in DECISIONS else "other"
    result["parts"] = _parts(parsed.get("parts"))
    result["instructions"] = _instructions(parsed.get("instructions"))
    if result["instructions"]:
        result["instruction"] = " / ".join(i["text"] for i in result["instructions"])
    result["part_no"] = _int(parsed.get("part_no"))
    # 관련 카드는 모델이 고른다(창 밖 근거 허용의 기준이라 열린 카드로 짐작하지 않는다)
    related = parsed.get("related_card")
    result["related_card"] = related if related in known else None
    result["wants_revision"] = bool(parsed.get("wants_revision"))
    result["judgment_request"] = bool(parsed.get("judgment_request"))
    result["asks_my_part"] = _int(parsed.get("asks_my_part"))
    return result, False


def saved(result: dict[str, Any]) -> dict[str, Any]:
    """messages.meta.classification에 남기는 부분."""
    return {k: result.get(k) for k in SAVED_KEYS if k != "reply_to_doc" or result.get(k)}
