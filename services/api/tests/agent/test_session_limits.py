"""완료 기준(Codex 수정 라운드 R6·R7·R8): 세션 토큰 예산(모든 LLM 호출 반영, 소진 뒤 카드는 규칙
문장), 일반 응답 LLM 실패 연속 3회 → 세션 failed(정상 응답이면 0), 확정 뒤 재분업 한도(적응성 카드
전 1회·뒤 1회)를 보드와 채팅이 공유.

검증 방식: FakeLLM(Brain) + 격리 DB + 실제 MCP 하위 프로세스.
"""

import pytest
from app import scheduler
from app.agent.runner import Stimulus
from app.agent.session import common
from app.agent.session import state as session_state
from app.agent.session.graph import thread_id
from app.agent.session.nodes import FALLBACK_TEXT
from app.models import Message, Session
from langchain_core.messages import HumanMessage

from tests.agent.brain import Brain, cls
from tests.agent.script_driver import start
from tests.agent.test_session_recovery import BOARD, event
from tests.agent.test_session_scripts import rows


async def test_budget_counts_every_call_and_cards_use_rule_text(
    stack, service, make_position, db, monkeypatch
):
    """R6: 킥오프 실행의 LLM 사용량(카드 문장)이 예산에서 빠지고, 소진 뒤 분업 카드는 LLM 없이
    규칙 문장으로 나간다."""
    monkeypatch.setattr(session_state, "TOKEN_BUDGET", 1)
    monkeypatch.setattr(common, "OBSERVE_RESERVE", 0)
    brain = Brain()
    stack.llm.default = brain
    driver = await start(stack, service, make_position, ["collaboration"], 6)
    graph = await stack.runner.graph()
    config = {"configurable": {"thread_id": thread_id(driver.session_id)}}
    assert (await graph.aget_state(config)).values["token_budget_left"] == 0

    before = len(stack.llm.calls)
    await driver.advance_to(0.6)  # division 카드(0.5)
    assert len(stack.llm.calls) == before  # 소진 뒤 카드는 LLM을 부르지 않는다
    division = await event(db, driver.session_id, "division")
    [card] = await rows(db, Message, Message.event_id == division.id)
    assert division.status == "done" and card.content.startswith("기획안 파트를 어떻게 나눌지")


class FlakyReply:
    """respond(페르소나 답) 호출만 실패시킨다. fail이 참인 동안 매 응답이 LLM 실패 폴백이 된다."""

    def __init__(self, brain):
        self.brain, self.fail = brain, True

    def __call__(self, messages):
        if self.fail and "보낸 마지막 메시지에" in str(messages[-1].content):
            raise RuntimeError("forced reply failure")
        return self.brain(messages)


async def test_three_consecutive_reply_failures_fail_session(stack, service, make_position, db):
    """R7: 카드는 정상인 세션에서 일반 응답만 연속 3회 LLM 실패 → 세션 failed. 중간에 정상 응답이
    있으면 0으로 돌아간다."""
    flaky = FlakyReply(Brain())
    stack.llm.default = flaky
    driver = await start(stack, service, make_position, ["collaboration"], 6)
    sid = driver.session_id
    async with driver.client() as http:
        await driver.say({"channel": "dm", "content": "도현님 하나"}, "a", http)
        assert (await db.get(Session, sid, populate_existing=True)).llm_failures == 1
        flaky.fail = False
        await driver.say({"channel": "dm", "content": "도현님 둘"}, "b", http)
        assert (await db.get(Session, sid, populate_existing=True)).llm_failures == 0
        flaky.fail = True
        for index in range(3):
            await driver.say({"channel": "dm", "content": f"도현님 {index}"}, f"c{index}", http)
    session = await db.get(Session, sid, populate_existing=True)
    assert (session.status, session.failed_reason, session.llm_failures) == (
        "failed",
        "llm_failures",
        3,
    )
    fallbacks = [
        m for m in await rows(db, Message, Message.session_id == sid) if m.content == FALLBACK_TEXT
    ]
    assert len(fallbacks) == 4 and all(m.seq == 9 for m in fallbacks)
    kickoff = await event(db, sid, "kickoff")
    assert kickoff.status == "done"  # 카드 실패가 아니라 응답 실패로 끝났다


REDIVIDE = "도현님, 4·5번 다시 도현님이 다 해 주세요."


async def test_redivide_limit_shared_by_board_and_chat(stack, service, make_position, db):
    """R8: 확정 뒤 재분업은 적응성 카드 전 1회·뒤 1회. 보드로 한 번 바꾸면(1분 안 연속 변경은 같은
    재분업) 같은 단계의 다음 보드 변경은 422이고 채팅 재분업도 한도 안내로 답한다. 카드 뒤에는 다시
    한 번 된다."""
    parts = {"1": "candidate", "2": "candidate", "3": "both", "4": "candidate", "5": "colleague"}
    stack.llm.default = Brain(
        {REDIVIDE: cls("redivide", decision="decide", parts={"4": "colleague", "5": "colleague"})}
    )
    driver = await start(stack, service, make_position, ["adaptability"], 6)
    sid = driver.session_id
    await driver.advance_to(0.2)
    await driver.do({"board": BOARD}, 0)
    async with driver.client() as http:
        r = await http.put(f"/sessions/{sid}/tasks/4", json={"assignee": "candidate"})
        assert r.status_code == 200  # 카드 전 재분업 1회
        await driver.shift(1.2)  # 1분 넘게 지난 다음 변경은 새 재분업
        r = await http.put(f"/sessions/{sid}/tasks/4", json={"assignee": "colleague"})
        assert r.status_code == 422 and "더 바꾸긴 어렵" in r.json()["error"]["message"]
        await driver.say({"channel": "dm", "content": REDIVIDE}, "x", http)
    session = await db.get(Session, sid, populate_existing=True)
    assert session.division["parts"] == parts
    replies = await rows(db, Message, Message.session_id == sid, order=Message.created_at)
    assert "더 바꾸긴 어렵" in replies[-1].content

    await driver.advance_to(1.6)  # 적응성 카드(1.5) 뒤에는 한 번 더
    async with driver.client() as http:
        r = await http.put(f"/sessions/{sid}/tasks/4", json={"assignee": "colleague"})
    assert r.status_code == 200
    await scheduler.drain()  # 보드 재배정이 띄운 동료 division 자극까지 끝낸다
    session = await db.get(Session, sid, populate_existing=True)
    assert [row["stage"] for row in session.redivisions] == ["before_change", "after_change"]


class _Scope:
    async def specs(self):
        return []

    async def call(self, name, args):
        return {"ok": True, "data": {"tasks": []}}


class _Mcp:
    def scope(self, allowed):
        return _Scope()


async def _noop(*args):
    return None


async def test_tool_loop_checks_budget_before_every_call():
    """RC4: 도구를 고른 첫 호출로 예산이 바닥나면 다음 LLM 호출 없이 끝낸다(예산 안내 경로)."""
    from app.agent.llm import FakeLLM, Usage, tool_call
    from app.agent.session.common import OBSERVE_RESERVE, RunDeps
    from app.agent.session.nodes import _tool_loop

    llm = FakeLLM([tool_call("get_board"), "답"])
    deps = RunDeps(llm=llm, mcp=_Mcp(), store=None, usage=Usage(), progress=_noop)
    state = {"token_budget_left": OBSERVE_RESERVE + 10, "run_id": "r", "session_id": "s"}
    loop = await _tool_loop(deps, state, "colleague", [HumanMessage("질문 " * 100)])
    assert (loop.text, loop.budget_hit, len(llm.calls)) == ("", True, 1)


async def test_observe_classification_stays_inside_session_budget(monkeypatch):
    """RC4: 관찰 분류는 페르소나가 멈춘 뒤에도 남긴 몫(OBSERVE_RESERVE)으로 돌지만 세션 300k 자체를
    넘기면 부르지 않는다(label null → 분류 실패)."""
    from app.agent import observe
    from app.agent.llm import FakeLLM, Trace, Usage
    from app.agent.session.common import OBSERVE_RESERVE, RunDeps

    deps = RunDeps(llm=FakeLLM(), mcp=None, store=None, usage=Usage(), progress=_noop)
    assert deps.exhausted({"token_budget_left": OBSERVE_RESERVE})
    assert not deps.observe_exhausted({"token_budget_left": OBSERVE_RESERVE})
    assert deps.observe_exhausted({"token_budget_left": 0})
    card = {"card_id": "collab_help", "labels": ["help_now"], "aux": [], "metrics": []}
    win = observe.Window(card=card, start=0, end=10, due=0, card_t_min=0)
    meta = {"classification": {"related_card": "collab_help"}}
    message = {
        "id": "m",
        "t_min": 1,
        "content": "네",
        "channel": "dm",
        "sender": "candidate",
        "meta": meta,
    }
    result = await observe.classify(
        win, observe.Inputs(messages=[message]), None, "", usage=Usage(), trace=Trace("r", "s", "o")
    )
    assert (result.label, result.llm_called) == (None, False)


async def test_reply_fallback_restored_on_rerun(stack, service, make_position, db):
    """RC5: 세 번째 폴백 응답이 저장된 뒤 finish_run 전에 끊겼어도, 같은 run_id 복구가 저장된 응답
    (seq 9, meta.fallback)에서 실패를 복원해 한 번만 센다 → 세션 failed."""
    from app.services.messages import accept_candidate_message, save_internal_message

    flaky = FlakyReply(Brain())
    stack.llm.default = flaky
    driver = await start(stack, service, make_position, ["collaboration"], 6)
    sid = driver.session_id
    async with driver.client() as http:
        for index in range(2):
            await driver.say({"channel": "dm", "content": f"도현님 {index}"}, f"c{index}", http)
    assert (await db.get(Session, sid, populate_existing=True)).llm_failures == 2
    async with stack.ctx.session_factory() as session_db:
        message, run_id, _ = await accept_candidate_message(
            session_db, stack.hub, sid, "c3", "dm", "도현님 셋"
        )
        # 그래프가 폴백 응답까지 저장하고 agent_runs를 끝내기 전에 죽은 상태
        await save_internal_message(
            session_db,
            stack.hub,
            sid,
            "dm",
            "colleague",
            FALLBACK_TEXT,
            run_id,
            9,
            None,
            {"node": "respond", "slot": 9, "fallback": "llm_unavailable"},
        )
    flaky.fail = False  # 복구 실행에서는 LLM이 살아 있어도 이미 저장된 응답을 쓴다
    await scheduler.run_stimulus(stack.ctx, sid, Stimulus("message", message_id=message.id), run_id)
    session = await db.get(Session, sid, populate_existing=True)
    assert (session.llm_failures, session.status) == (3, "failed")
    replies = await rows(db, Message, Message.session_id == sid, Message.run_id == run_id)
    assert [m.seq for m in replies if m.sender == "colleague"] == [9]


FIRST = "도현님, 4번은 제가 맡을게요."
ASK_AGAIN = "도현님, 5번도 제가 할게요."


async def test_chat_decisions_are_each_one_redivide(stack, service, make_position, db):
    """RC6: 1분 유예는 보드 행 묶음에만. 채팅 결정은 하나가 1회라 같은 단계의 두 번째 채팅 결정과
    그 뒤 보드 PUT은 거부된다."""
    stack.llm.default = Brain(
        {
            FIRST: cls("redivide", decision="decide", parts={"4": "candidate", "5": "colleague"}),
            ASK_AGAIN: cls(
                "redivide", decision="decide", parts={"4": "colleague", "5": "candidate"}
            ),
        }
    )
    driver = await start(stack, service, make_position, ["adaptability"], 6)
    sid = driver.session_id
    await driver.advance_to(0.2)
    await driver.do({"board": BOARD}, 0)
    async with driver.client() as http:
        await driver.say({"channel": "dm", "content": FIRST}, "x1", http)  # 1회 수락
        await driver.say({"channel": "dm", "content": ASK_AGAIN}, "x2", http)  # 바로 다음 결정
        r = await http.put(f"/sessions/{sid}/tasks/4", json={"assignee": "colleague"})
    session = await db.get(Session, sid, populate_existing=True)
    assert (
        session.division["parts"]["4"] == "candidate"
        and session.division["parts"]["5"] == "colleague"
    )
    assert r.status_code == 422
    assert [(row["stage"], row["via"]) for row in session.redivisions] == [
        ("before_change", "chat")
    ]
    replies = await rows(db, Message, Message.session_id == sid, order=Message.created_at)
    assert "더 바꾸긴 어렵" in [m for m in replies if m.sender == "colleague"][-1].content


class Crash(Exception):
    """프로세스가 죽은 것처럼 실행 기록 저장을 끊는다."""


async def test_reply_fallback_counted_once_after_graph_completed(
    stack, service, make_position, db, monkeypatch
):
    """RC5: 세 번째 폴백 응답으로 그래프까지 끝난 뒤 finish_run 직전에 끊기면, 같은 run_id 복구는
    route에서 바로 끝나지만 체크포인트의 표시로 폴백을 복원해 한 번만 센다 → 3·failed."""
    from app.services import runs
    from app.services.messages import accept_candidate_message

    flaky = FlakyReply(Brain())
    stack.llm.default = flaky
    driver = await start(stack, service, make_position, ["collaboration"], 6)
    sid = driver.session_id
    async with driver.client() as http:
        for index in range(2):
            await driver.say({"channel": "dm", "content": f"도현님 {index}"}, f"c{index}", http)
    async with stack.ctx.session_factory() as session_db:
        message, run_id, _ = await accept_candidate_message(
            session_db, stack.hub, sid, "c3", "dm", "도현님 셋"
        )
    original = runs.finish_run

    async def crash_before_record(*args, **kwargs):
        raise Crash

    monkeypatch.setattr(runs, "finish_run", crash_before_record)
    stimulus = Stimulus("message", message_id=message.id)
    with pytest.raises(Crash):
        await scheduler.run_stimulus(stack.ctx, sid, stimulus, run_id)
    monkeypatch.setattr(runs, "finish_run", original)
    assert (await db.get(Session, sid, populate_existing=True)).llm_failures == 2

    flaky.fail = False
    calls = len(stack.llm.calls)
    await scheduler.run_stimulus(stack.ctx, sid, stimulus, run_id)  # 같은 run_id 복구
    assert len(stack.llm.calls) == calls  # 끝난 그래프는 다시 생성하지 않는다
    session = await db.get(Session, sid, populate_existing=True)
    assert (session.llm_failures, session.status) == (3, "failed")
    replies = await rows(db, Message, Message.run_id == run_id, Message.sender == "colleague")
    assert [m.seq for m in replies] == [9]
