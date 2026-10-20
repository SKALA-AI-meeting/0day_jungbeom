"""동료 파트 문서 쓰기·보내기(초안 v1, 완성본 v2, 피드백 반영 v3).

입력은 작업 기억(parts·instructions·agreements·feedback)과 회사 문서 검색 결과다. 파트별 최신 지시의
핵심어가 본문에 없으면 생성 실패로 보고 1회 다시 쓴다(지시 반영 검사, 규칙 함수). 보내기는 같은
run_id로 1회 재시도하고, 그래도 실패하면 호출한 카드가 document_missing으로 실패시킨다.
"""

from typing import Any

from app.agent.llm import LLMUnavailable
from app.agent.mcp_client import error_code
from app.agent.session import prompts, seq
from app.agent.session.common import RunDeps, compose
from app.agent.session.state import SessionState

SEARCH_TOP_K = 3


def latest_instructions(work_notes: dict[str, Any], part_no: int) -> list[dict[str, Any]]:
    """그 파트에 적용할 지시: 파트를 가리킨 최신 지시 1개 + 파트를 정하지 않은 최신 지시 1개.

    같은 파트의 새 지시가 이전 지시를 대체한다(이전 지시는 work_notes에 이력으로 남는다).
    """
    rows = work_notes.get("instructions") or []
    chosen = []
    for target in (part_no, None):
        found = [i for i in rows if i.get("part_no") == target]
        if found:
            chosen.append(found[-1])
    return chosen


def missing_keywords(content: str, instructions: list[dict[str, Any]]) -> list[str]:
    """지시 반영 검사: 각 지시의 핵심어가 본문에 있는가(띄어쓰기 무시)."""
    compact = "".join(content.split())
    return [
        k
        for i in instructions
        for k in i.get("keywords") or []
        if "".join(k.split()) not in compact
    ]


def part_title(state: SessionState, part_no: int) -> str:
    part = (state["scenario"].get("parts") or {}).get(str(part_no)) or {}
    return part.get("title", f"{part_no}번") if isinstance(part, dict) else str(part)


def previous_version(shared: dict[str, Any] | None, part_no: int) -> str | None:
    for doc in (shared or {}).get("documents", []):
        if doc["owner"] == "colleague" and doc["part_no"] == part_no and doc["versions"]:
            return doc["versions"][-1]["content"]
    return None


async def write_part(
    deps: RunDeps,
    state: SessionState,
    part_no: int,
    version: int,
    *,
    shared: dict[str, Any] | None,
    skeleton: bool = False,
) -> str | None:
    """파트 본문. 지시 반영 검사를 두 번 통과하지 못하거나 LLM이 실패하면 None."""
    notes = state["work_notes"]
    instructions = latest_instructions(notes, part_no)
    feedback = [f for f in notes.get("feedback") or [] if f.get("part_no") == part_no]
    title = part_title(state, part_no)
    if deps.exhausted(state):
        return rule_part(part_no, title, instructions, previous_version(shared, part_no))
    query = " ".join([title, *(i["text"] for i in instructions)])
    search = await deps.code.call("search_documents", {"query": query, "top_k": SEARCH_TOP_K})
    base = [
        prompts.work_notes_block(notes),
        prompts.search_block(search),
    ]
    missing: list[str] | None = None
    for _ in range(2):
        block = prompts.part_block(
            part_no,
            title,
            version,
            skeleton=skeleton,
            instructions=instructions,
            feedback=feedback,
            previous=previous_version(shared, part_no),
            missing=missing,
        )
        try:
            content = await compose(deps, state, "colleague", [*base, block], node="draft")
        except LLMUnavailable:
            return None
        missing = missing_keywords(content, instructions)
        if not missing:
            return content
    return None


def rule_part(
    part_no: int, title: str, instructions: list[dict[str, Any]], previous: str | None
) -> str:
    """예산 소진 때의 규칙 문서: 이전 버전에 파트별 최신 지시(핵심어 포함)를 덧붙인다."""
    lines = [previous.strip()] if previous else [f"{part_no}번 {title}"]
    for i in instructions:
        keys = ", ".join(i.get("keywords") or [])
        lines.append(f"- 반영: {i['text']}" + (f" ({keys})" if keys else ""))
    return "\n".join(lines)


async def send_part(
    deps: RunDeps, state: SessionState, part_no: int, content: str, event_id: str | None
) -> tuple[bool, int | None]:
    """send_document(team, seq=파트 번호×10). 실패하면 같은 run_id로 1회 재시도. (ok, version)."""
    args = {
        "part_no": part_no,
        "content": content,
        "channel": "team",
        "run_id": state["run_id"],
        "seq": seq.doc_seq(part_no),
    }
    if event_id:
        args["event_id"] = event_id
    for _ in range(2):
        result = await deps.code.call("send_document", args)
        if result.get("ok"):
            return True, result["data"]["version"]
        if error_code(result) == "forbidden":  # 동료 담당이 아님. 다시 해도 같다
            break
    return False, None
