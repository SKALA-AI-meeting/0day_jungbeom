"""노드들이 함께 쓰는 실행 의존성(RunDeps)과 작은 도구: 메시지 저장, 재실행 확인, 문장 생성.

RunDeps는 LangGraph Runtime context라 체크포인트되지 않는다. route가 이번 실행의 세션 조회 결과
(deps.session)를 채우고, 노드는 그것으로 이벤트 시각·분업·제출 여부를 본다.
"""

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.guard import guard_for
from app.agent.llm import BaseLLM, LLMUnavailable, Trace, Usage
from app.agent.mcp_client import SESSION_CODE_TOOLS, McpClient, ToolScope, error_code
from app.agent.session import prompts
from app.agent.session.state import TOKEN_BUDGET, SessionState
from app.agent.session.store import AgentStore

log = logging.getLogger(__name__)

Progress = Callable[[str, str, str, str | None], Awaitable[None]]
COLLEAGUE_PARTS = ("colleague", "both")
# 세션 예산 중 관찰 분류에 남겨 두는 몫. 페르소나 쪽이 먼저 멈춰도 남은 창의 관찰은 300k 안에서 돈다
OBSERVE_RESERVE = 30_000
SPEAKER_PREFIX = re.compile(r"^(\[[^\]\n]{1,20}\]\s*)?[^:\n\[]{1,20}\(나\)\s*:\s*")


@dataclass
class Outcome:
    ok: bool = True
    fallback_used: bool = False
    error: str | None = None
    reply_fallback: bool = False  # 응답 메시지가 LLM 실패 폴백(seq 9)

    def fail(self, error: str) -> None:
        self.ok = False
        self.error = self.error or error


@dataclass
class RunDeps:
    llm: BaseLLM
    mcp: McpClient
    store: AgentStore
    usage: Usage
    progress: Progress
    outcome: Outcome = field(default_factory=Outcome)
    session: dict[str, Any] = field(default_factory=dict)  # 이번 실행의 get_session 결과
    # 역할별 LLM(llm/roles.make_llm). 없는 역할은 llm을 쓴다(테스트의 FakeLLM 하나)
    roles: dict[str, BaseLLM] = field(default_factory=dict)

    def budget_left(self, state: SessionState) -> int:
        """세션 토큰 예산(입력+출력, 재시도 포함) 잔량. 이번 실행의 모든 호출(usage)을 뺀 값."""
        return state.get("token_budget_left", TOKEN_BUDGET) - self.usage.tokens

    def exhausted(self, state: SessionState) -> bool:
        """페르소나·카드·문서·분류 호출을 멈출 때. 관찰 분류 몫(OBSERVE_RESERVE)은 남겨 둔다."""
        return self.budget_left(state) <= OBSERVE_RESERVE

    def observe_exhausted(self, state: SessionState) -> bool:
        """관찰 분류까지 멈출 때(세션 300k 한도 자체). 그 뒤 관찰은 레이블 null(분류 실패)."""
        return self.budget_left(state) <= 0

    def llm_for(self, role: str) -> BaseLLM:
        """colleague·manager·observe. 메시지 분류는 observe(고정 레이블 분류와 같은 역할)."""
        return self.roles.get(role) or self.llm

    def trace(self, state: SessionState, node: str) -> Trace:
        return Trace(state["run_id"], state["session_id"], node)

    @property
    def code(self) -> ToolScope:
        """결정적 노드가 코드로 부르는 도구."""
        return self.mcp.scope(SESSION_CODE_TOOLS)

    def minutes(self, iso: str | None, *, exact: bool = False) -> float | None:
        """ISO 시각 → 세션 분. 기본은 0.01분 반올림(관찰 키 window_start가 재실행에도 같은 값),
        exact는 창 끝처럼 그 시각의 기록까지 포함해야 할 때."""
        started = self.session.get("started_at")
        if iso is None or started is None:
            return None
        delta = (datetime.fromisoformat(iso) - datetime.fromisoformat(started)).total_seconds() / 60
        return delta if exact else round(delta, 2)

    def events(self) -> list[dict[str, Any]]:
        return self.session.get("events") or []

    def event(self, event_id: str) -> dict[str, Any] | None:
        return next((e for e in self.events() if e["id"] == event_id), None)

    def card_fired(self, card_id: str) -> bool:
        return any(
            e["card_id"] == card_id and e["status"] in ("fired", "done") for e in self.events()
        )


def cards_by_id(state: SessionState) -> dict[str, dict[str, Any]]:
    return {c["card_id"]: c for c in state["scenario"]["cards"]}


def my_parts(division: dict[str, str] | None) -> list[int]:
    """확정 분업에서 동료 담당(혼자·같이) 파트."""
    return sorted(int(no) for no, who in (division or {}).items() if who in COLLEAGUE_PARTS)


def already(state: SessionState, slot: int) -> dict[str, Any] | None:
    """같은 run_id·슬롯 메시지가 이미 저장됐는가(변경 성공 뒤 체크포인트 전에 죽은 재실행)."""
    return next(
        (
            m
            for m in state.get("recent_messages") or []
            if m.get("run_id") == state["run_id"] and m.get("slot") == slot
        ),
        None,
    )


def sent_this_run(state: SessionState, part_no: int) -> dict[str, Any] | None:
    """이 run_id로 이미 보낸 그 파트 문서 카드 메시지."""
    return next(
        (
            m
            for m in state.get("recent_messages") or []
            if m.get("run_id") == state["run_id"]
            and m.get("shared_doc")
            and m["sender"] == "colleague"
            and str(m.get("content", "")).startswith(f"{part_no}번")
        ),
        None,
    )


async def post(
    deps: RunDeps,
    state: SessionState,
    *,
    channel: str,
    sender: str,
    content: str,
    slot: int,
    node: str,
    event_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> bool:
    body = {
        "channel": channel,
        "sender": sender,
        "content": content,
        "run_id": state["run_id"],
        "seq": slot,
        "meta": {"model": deps.llm_for(sender).model, "node": node, "slot": slot, **(meta or {})},
    }
    if event_id:
        body["event_id"] = event_id
    result = await deps.code.call("post_message", body)
    if not result.get("ok"):
        deps.outcome.fail(f"post_message:{error_code(result)}")
        return False
    return True


class BudgetExhausted(LLMUnavailable):
    """세션 토큰 예산 소진. 호출자는 실패와 같은 규칙 경로(고정·규칙 문장)로 간다."""


async def compose(
    deps: RunDeps, state: SessionState, persona: str, blocks: list[str], *, node: str
) -> str:
    """페르소나 system + 블록으로 한 메시지를 만든다(guard 적용). 실패하면 LLMUnavailable,
    예산이 소진됐으면 LLM을 부르지 않고 BudgetExhausted."""
    scenario = state["scenario"]
    if deps.exhausted(state):
        raise BudgetExhausted("token_budget_exhausted")
    reply = await deps.llm_for(persona).ainvoke(
        [
            SystemMessage(prompts.system_prompt(scenario, persona)),
            HumanMessage("\n\n".join(blocks)),
        ],
        usage=deps.usage,
        trace=deps.trace(state, node),
    )
    # 모델이 [최근 대화] 줄 형식("[팀 채널] 한서윤 팀장(나): …")을 흉내 내면 말머리를 뗀다
    text = SPEAKER_PREFIX.sub("", str(reply.content or "").strip()).strip()
    if not text:  # 지시문을 그대로 내보내지 않는다
        raise LLMUnavailable("empty text")
    return guard_for(scenario).apply(text).text


async def board_and_shared(deps: RunDeps) -> tuple[dict | None, dict | None]:
    board = await deps.code.call("get_board")
    shared = await deps.code.call("get_shared_documents")
    return (
        board["data"] if board.get("ok") else None,
        shared["data"] if shared.get("ok") else None,
    )


async def context_blocks(
    deps: RunDeps, state: SessionState, persona: str, division: dict[str, str] | None
) -> list[str]:
    """카드·결정적 노드의 기본 컨텍스트: 보드·보낸 문서, (동료) 작업 기억, 최근 대화."""
    board, shared = await board_and_shared(deps)
    scenario = state["scenario"]
    blocks = [prompts.board_block(scenario, division, board, shared, persona)]
    if persona == "colleague":
        blocks.append(prompts.work_notes_block(state["work_notes"]))
        blocks.append(prompts.rules_block(scenario, state.get("current_card")))
    blocks.append(
        prompts.recent_block(state["recent_messages"], scenario, persona, state.get("summary", ""))
    )
    return blocks


PAGE = 50  # 메시지 한 페이지
MAX_PAGES = 5
RECENT_KEEP = 80  # State에 남기는 최근 메시지(페르소나별로 다시 30개로 거른다)
PERSONA_CHANNELS = ("team", "dm", "manager_dm")  # notice·assistant는 State에도 넣지 않는다
# 시나리오에서 State에 담지 않는 큰 값(회사 문서 본문은 rag-mcp가 가진다)
SCENARIO_SKIP = ("documents",)


def _slim(message: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "channel", "sender", "content", "t_min", "created_at", "run_id", "event_id")
    slim = {k: message.get(k) for k in keys}
    slim["slot"] = (message.get("meta") or {}).get("slot")
    slim["reply_to_doc"] = message.get("reply_to_doc")
    slim["shared_doc"] = message.get("shared_doc")
    slim["fallback"] = (message.get("meta") or {}).get("fallback")
    return slim


async def refresh_messages(
    store: AgentStore, session_id: uuid.UUID, recent: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str | None]:
    """(created_at, id) 커서로 최근 메시지를 갱신한다. 상한 소진은 불완전 조회로 실패한다."""
    # 이전 체크포인트에 정확한 시각이 없으면 처음부터 읽어 새 커서를 만든다.
    after = recent[-1] if recent and recent[-1].get("created_at") else None
    merged = list(recent) if after else []
    known = {m["id"] for m in merged}
    for _ in range(MAX_PAGES):
        page = await store.messages_page(session_id, after, PAGE)
        for message in page:
            if message["id"] not in known and message["channel"] in PERSONA_CHANNELS:
                merged.append(_slim(message))
                known.add(message["id"])
        if len(page) < PAGE:
            return merged[-RECENT_KEEP:], None
        after = page[-1]
    return merged[-RECENT_KEEP:], "page_limit_exceeded"


async def prepare(deps: RunDeps, state: SessionState) -> dict[str, Any] | None:
    """이번 실행의 세션 조회(deps.session)와 State 갱신값(scenario·division·recent_messages).

    route가 부르고, 중단된 실행을 LangGraph가 route 없이 그 노드부터 이어 갈 때는 진입 노드가
    부른다(deps는 실행마다 새로 만들어지므로 비어 있다). 실패하면 outcome에 남기고 None.
    """
    session = await deps.code.call("get_session")
    if not session.get("ok"):
        deps.outcome.fail(f"get_session:{error_code(session)}")
        return None
    deps.session = session["data"]
    update: dict[str, Any] = {}
    if state.get("scenario") is None:
        scenario = session["data"]["position"]["scenario"]
        update["scenario"] = {k: v for k, v in scenario.items() if k not in SCENARIO_SKIP}
    division = session["data"].get("division")
    # 보드 확정은 division 자극이 작업 기억과 함께 반영한다(그 전에는 State를 앞지르지 않는다)
    if state["stimulus"]["type"] != "division" and division:
        update["division"] = division.get("parts")
    recent, error = await refresh_messages(
        deps.store, uuid.UUID(state["session_id"]), state.get("recent_messages") or []
    )
    update["recent_messages"] = recent
    if error:
        deps.outcome.fail(f"list_messages:{error}")
        return None
    return update


async def resumed(deps: RunDeps, state: SessionState) -> tuple[SessionState, dict[str, Any]]:
    """진입 노드 앞에서: route를 건너뛴 재개 실행이면 prepare로 채운다. (state, 반환에 더할
    갱신값)."""
    if deps.session:
        return state, {}
    update = await prepare(deps, state) or {}
    return {**state, **update}, update
