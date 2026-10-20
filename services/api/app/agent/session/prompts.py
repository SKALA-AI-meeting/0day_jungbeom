"""프롬프트 조립과 페르소나별 컨텍스트 블록(scenarios/prompts/README.md "조립 방식").

system = common_rules.md + 페르소나 파일. 실행 맥락은 이름 붙은 블록으로 사람 메시지에 넣는다.
컨텍스트 허용 목록(harness.md Context): 동료 = 팀·DM 최근 30개 + 요약 + 보드·문서 상태 + 작업 기억 +
문서 검색 결과, 팀장 = 팀 채널·팀장 DM + 보드·문서 상태 + 문서 검색 결과. notice·assistant 채널,
미래 카드, 관찰 레이블·지표, 미공개 문서, 지원자가 보내지 않은 문서는 어느 페르소나에도 넣지 않는다.
"""

import json
from typing import Any

from app.masking import mask

PERSONA_FILE = {"colleague": "colleague.md", "manager": "manager.md"}
VISIBLE_CHANNELS = {"colleague": ("team", "dm"), "manager": ("team", "manager_dm")}
CONTEXT_MESSAGES = 30
CHANNEL_NAME = {"team": "팀 채널", "dm": "DM", "manager_dm": "팀장 DM"}


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
    persona: str = "colleague",
) -> str:
    """보드(태스크)와 파트별로 보낸 문서(get_shared_documents). 조회에 실패한 쪽은 '확인 불가'로
    둔다.

    지원자 문서는 보낸 버전만 보인다(보내지 않은 문서 내용은 어느 페르소나에도 넣지 않는다).
    """
    colleague = "나(동료)" if persona == "colleague" else names(scenario)["colleague"]
    who = {"candidate": "주담당", "colleague": colleague, "both": "같이"}
    owner = {"candidate": "주담당", "colleague": "나" if persona == "colleague" else colleague}
    tasks = {str(t["part_no"]): t for t in (board or {}).get("tasks", [])}
    sent: dict[str, list[str]] = {}
    for doc in (shared or {}).get("documents", []):
        latest = doc["versions"][-1]
        preview = mask((latest.get("content") or "").strip()[:120])  # 전화번호·이메일 가림
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


NOTE_KEYS = (
    "parts",
    "instructions",
    "agreements",
    "progress",
    "sent",
    "feedback",
    "disagree_target",
)


def work_notes_block(work_notes: dict[str, Any]) -> str:
    """동료 작업 기억(설계의 7필드만. 되돌림 대안·재분업 횟수 같은 진행 기록은 넣지 않는다)."""
    notes = {k: work_notes.get(k) for k in NOTE_KEYS}
    return "[작업 기억]\n" + json.dumps(notes, ensure_ascii=False)


def search_block(result: dict[str, Any] | None, unreleased: list[str] | None = None) -> str:
    """rag search_documents 결과. 실패는 사실대로 적고 내용을 지어내지 않게 한다.

    unreleased는 질문이 가리킨 미공개 문서 제목이다(내용은 넣지 않고 공개 전이라는 사실만).
    """
    if result is None:
        body = "(검색하지 않음)"
    elif not result.get("ok"):
        code = (result.get("error") or {}).get("code", "internal")
        body = f"(문서 검색을 지금 쓸 수 없음: {code}. 문서 내용을 짐작하지 말 것)"
    elif not result["data"]:
        body = "(관련 공개 문서 없음)"
    else:
        body = "\n".join(f"- [{r['title']}] {r['chunk'].strip()}" for r in result["data"])
    if unreleased:
        body += "\n" + "\n".join(
            f"- 미공개: {t} (아직 공유되지 않은 자료, 내용 모름)" for t in unreleased
        )
    return "[문서 검색 결과] (공개된 문서만)\n" + body


def card_block(card: dict[str, Any], brief: str, extra: list[str] | None = None) -> str:
    """카드 brief(치환 뒤)·brief_note·채널. extra는 코드가 정한 사실(보낸 문서, 확정 분업 등)."""
    lines = [
        f"brief: {brief}",
        f"채널: {CHANNEL_NAME.get(card.get('channel'), card.get('channel'))}",
    ]
    if card.get("brief_note"):
        lines.insert(1, f"brief_note: {card['brief_note']}")
    lines += extra or []
    return "[실행할 카드]\n" + "\n".join(lines)


def say_block(instruction: str) -> str:
    """카드가 아닌 결정적 노드의 말(분업 수락·되돌림 등). 무엇을 말할지만 정하고 문장은
    페르소나가."""
    return "[실행할 카드]\nbrief: " + instruction + "\n채널: 지금 대화한 채널"


def rules_block(scenario: dict[str, Any], current_card: str | None) -> str:
    """지금 열린 창의 선점 금지(persona.must_not_preempt)와 창 안에서 해도 되는 것.

    창 이름(카드 id)만 쓰고 카드 내용·관찰 방식은 넣지 않는다.
    """
    persona = (scenario.get("persona") or {}).get("colleague") or {}
    rules = [
        r["rule"]
        for r in persona.get("must_not_preempt") or []
        if r.get("window") in (current_card, "any")
    ]
    lines = [f"- 하지 않음: {r}" for r in rules]
    lines += [f"- 해도 됨: {h}" for h in persona.get("in_window_help") or []]
    return "[지금 지킬 것]\n" + "\n".join(lines)


def part_block(
    part_no: int,
    title: str,
    version: int,
    *,
    skeleton: bool,
    instructions: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
    previous: str | None,
    missing: list[str] | None = None,
) -> str:
    """동료가 자기 파트 문서를 쓸 때의 입력. 반영할 지시의 핵심어는 본문에 드러나야 한다."""
    kind = "골격(같이 맡은 파트, 주담당이 이어 씀)" if skeleton else "본문"
    lines = [
        f"{part_no}번 {title} v{version} {kind}. 문서 본문만 300~600자로 쓴다. 인사·설명 문장 없이."
    ]
    if instructions:
        lines.append("반영할 지시(파트별 최신):")
        for i in instructions:
            keys = ", ".join(i.get("keywords") or [])
            lines.append(f"- {i['text']}" + (f" [핵심어: {keys}]" if keys else ""))
    if feedback:
        lines.append("주담당 답글:")
        lines += [f"- v{f['version']}: {f['text']}" for f in feedback]
    if previous:
        lines.append(f"이전 버전:\n{previous}")
    if missing:
        lines.append(f"앞 초안에 빠진 핵심어: {', '.join(missing)}. 반드시 본문에 넣는다.")
    return "[쓸 파트]\n" + "\n".join(lines)


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
