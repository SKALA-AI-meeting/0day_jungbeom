"""프롬프트 조립과 페르소나별 컨텍스트 블록(scenarios/prompts/README.md "조립 방식").

system = common_rules.md + 페르소나 파일. 실행 맥락은 이름 붙은 블록으로 사람 메시지에 넣는다.
컨텍스트 허용 목록(harness.md Context): 동료 = 팀·DM 최근 30개 + 요약 + 보드·문서 상태 + 작업 기억 +
문서 검색 결과, 팀장 = 팀 채널 + 보드·문서 상태. notice·assistant 채널, 미래 카드, 관찰 레이블,
미공개 문서는 어느 페르소나에도 넣지 않는다.
"""

import json
from typing import Any

PERSONA_FILE = {"colleague": "colleague.md", "manager": "manager.md"}
VISIBLE_CHANNELS = {"colleague": ("team", "dm"), "manager": ("team",)}
CONTEXT_MESSAGES = 30
CHANNEL_NAME = {"team": "팀 채널", "dm": "DM"}


def system_prompt(scenario: dict[str, Any], persona: str) -> str:
    prompts = scenario["prompts"]
    return f"{prompts['common_rules.md'].strip()}\n\n{prompts[PERSONA_FILE[persona]].strip()}"


def names(scenario: dict[str, Any]) -> dict[str, str]:
    company = scenario.get("company") or {}
    colleague = (company.get("colleague") or {}).get("name", "동료")
    manager = (company.get("manager") or {}).get("name", "팀장")
    return {
        "candidate": "주담당",
        "colleague": colleague,
        "manager": f"{manager} 팀장",
        "system": "시스템",
    }


def visible(messages: list[dict[str, Any]], persona: str) -> list[dict[str, Any]]:
    channels = VISIBLE_CHANNELS[persona]
    return [m for m in messages if m["channel"] in channels][-CONTEXT_MESSAGES:]


def _clock(t_min: float | None) -> str:
    if t_min is None:
        return "--:--"
    total = int(t_min)
    return f"{total // 60:02d}:{total % 60:02d}"


def recent_block(
    messages: list[dict[str, Any]], scenario: dict[str, Any], persona: str, summary: str
) -> str:
    label = names(scenario)
    lines = [f"(이전 대화 요약) {summary}"] if summary else []
    for m in visible(messages, persona):
        speaker = label.get(m["sender"], m["sender"])
        if m["sender"] == persona:
            speaker += "(나)"
        channel = CHANNEL_NAME.get(m["channel"], m["channel"])
        lines.append(f"[{_clock(m.get('t_min'))} {channel}] {speaker}: {m['content']}")
    return "[최근 대화]\n" + ("\n".join(lines) if lines else "(아직 대화 없음)")


def board_block(
    scenario: dict[str, Any],
    division: dict[str, str] | None,
    board: dict[str, Any] | None,
    shared: dict[str, Any] | None,
) -> str:
    """보드(태스크)와 파트별로 보낸 문서(get_shared_documents). 조회에 실패한 쪽은 '확인 불가'로
    둔다.

    지원자 문서는 보낸 버전만 보인다(보내지 않은 문서 내용은 어느 페르소나에도 넣지 않는다).
    """
    who = {"candidate": "주담당", "colleague": "나(동료)", "both": "같이"}
    owner = {"candidate": "주담당", "colleague": "나"}
    tasks = {str(t["part_no"]): t for t in (board or {}).get("tasks", [])}
    sent: dict[str, list[str]] = {}
    for doc in (shared or {}).get("documents", []):
        latest = doc["versions"][-1]
        preview = (latest.get("content") or "").strip()[:120]
        sent.setdefault(str(doc["part_no"]), []).append(
            f"{owner.get(doc['owner'], doc['owner'])} v{latest['version']}: {preview}"
        )
    lines = []
    if division is None:
        lines.append("분업: 아직 정하지 않음")
    for part_no, part in sorted((scenario.get("parts") or {}).items(), key=lambda p: int(p[0])):
        key = str(part_no)
        title = part["title"] if isinstance(part, dict) else part
        assignee = who.get((division or {}).get(key, ""), "미정")
        status = tasks.get(key, {}).get("status", "-") if board is not None else "확인 불가"
        if shared is None:
            written = "확인 불가"
        else:
            written = " / ".join(sent.get(key, [])) or "보낸 문서 없음"
        lines.append(f"{key}번 {title} | 담당 {assignee} | 보드 {status} | 문서 {written}")
    return "[보드·문서 상태]\n" + "\n".join(lines)


def work_notes_block(work_notes: dict[str, Any]) -> str:
    return "[작업 기억]\n" + json.dumps(work_notes, ensure_ascii=False)


def search_block(result: dict[str, Any] | None) -> str:
    """rag search_documents 결과. 실패는 사실대로 적고 내용을 지어내지 않게 한다."""
    if result is None:
        body = "(검색하지 않음)"
    elif not result.get("ok"):
        code = (result.get("error") or {}).get("code", "internal")
        body = f"(문서 검색을 지금 쓸 수 없음: {code}. 문서 내용을 짐작하지 말 것)"
    elif not result["data"]:
        body = "(관련 공개 문서 없음)"
    else:
        body = "\n".join(f"- [{r['title']}] {r['chunk'].strip()}" for r in result["data"])
    return "[문서 검색 결과] (공개된 문서만)\n" + body


def card_block(card: dict[str, Any], brief: str) -> str:
    lines = [
        f"brief: {brief}",
        f"채널: {CHANNEL_NAME.get(card.get('channel'), card.get('channel'))}",
    ]
    if card.get("brief_note"):
        lines.insert(1, f"brief_note: {card['brief_note']}")
    return "[실행할 카드]\n" + "\n".join(lines)


def fill_brief(text: str, scenario: dict[str, Any], division: dict[str, str] | None) -> str:
    """brief 치환 변수({interview_expected_time}, {colleague_first_part}).

    모르는 변수는 그대로 둔다.
    """
    parts = division or {str(k): v for k, v in (scenario.get("default_division") or {}).items()}
    mine = sorted(int(no) for no, who in parts.items() if who == "colleague")
    values = _Keep(scenario.get("vars") or {})
    if mine:
        values["colleague_first_part"] = f"{mine[0]}번"
    return text.format_map(values)


class _Keep(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
