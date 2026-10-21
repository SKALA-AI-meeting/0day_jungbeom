"""C1 지원자 확정과 단계·칸 규칙(design.md "단계·칸")."""

import asyncio
import uuid
from datetime import datetime, timedelta

from app.models import Session
from kit import bearer, finish, high, to_phase, types


async def test_keyword_confirm_frames_support_and_cumulative_deadline(api, ctx, classifier):
    sess = await api.new_session(minutes=60)
    classifier.rules["물이 좋겠어요"] = high("propose", "water")
    await api.say(sess, "물이 좋겠어요")
    before = await api.state(sess)
    assert [s["outcome"] for s in before["slots"]] == [None, None, None]
    mark = api.mark(sess)

    r = await api.confirm(sess, "keyword", value="물", option_key="water")

    assert r.status_code == 200, r.text
    assert r.json()["phase"] == "problem"
    frames = api.frames_since(sess, mark)
    assert types(frames)[:4] == ["slot.confirmed", "phase.changed", "timer", "materials.opened"]
    seqs = [f["seq"] for f in frames]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))
    slot = frames[0]["payload"]
    assert (slot["resolution"], slot["filled_by"], slot["value"]) == (
        "consensus",
        "candidate",
        "물",
    )
    assert frames[1]["payload"]["reason"] == "confirmed"
    assert frames[3]["payload"]["keyword"] == "물"
    # 지지자가 지원자 혼자면 표시용 outcome은 지원자 결정
    assert slot["outcome"] == "candidate_decision"
    assert r.json()["slot"]["outcome"] == "candidate_decision"
    assert "support" not in slot and "support" not in r.json()["slot"]

    slots = (await api.internal.get(f"/internal/sessions/{sess.id}/slots")).json()
    assert slots[0]["support"][0]["supporters"] == ["candidate"]
    assert slots[0]["outcome"] == "candidate_decision"
    state = await api.state(sess)
    assert state["slots"][0]["outcome"] == "candidate_decision"
    assert "support" not in state["slots"][0]
    record = (
        await api.public.get(f"/admin/sessions/{sess.id}/record", headers=bearer(sess.admin))
    ).json()
    assert [i["summary"] for i in record if i["type"] == "slot"] == [
        "keyword: 물 (candidate_decision)"
    ]
    started = state["session"]["started_at"]
    session = (await api.internal.get(f"/internal/sessions/{sess.id}")).json()
    assert session["phase_deadline_at"] != state["session"]["phase_started_at"]
    deadline = datetime.fromisoformat(session["phase_deadline_at"])
    assert deadline - datetime.fromisoformat(started) == timedelta(minutes=28)


async def test_confirm_rejects_unknown_keyword_and_other_phase(api):
    sess = await api.new_session()
    bad = await api.confirm(sess, "keyword", value="흙", option_key="soil")
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_keyword"
    other = await api.confirm(sess, "problem", value="아무거나")
    assert other.status_code == 409 and other.json()["error"]["code"] == "phase_not_open"
    ok = await api.confirm(sess, "keyword", value="불", option_key="fire")
    assert ok.status_code == 200
    again = await api.confirm(sess, "keyword", value="불", option_key="fire")
    assert again.status_code == 200
    different = await api.confirm(sess, "keyword", value="물", option_key="water")
    assert different.status_code == 409 and different.json()["error"]["code"] == "slot_confirmed"


async def test_problem_confirm_links_by_key_or_label_else_null_without_llm(api, classifier):
    sess = await api.new_session()
    await to_phase(api, sess, "problem")
    await api.ai_support(sess, "p1", "problem", "water_p2", "도심 폭우·침수 피해 증가")
    calls = len(classifier.calls)
    r = await api.confirm(sess, "problem", value="침수 문제", option_key="water_p2")
    assert r.status_code == 200
    r = await api.confirm(sess, "solution", value="우리 동네 물 지도 만들기")
    assert r.status_code == 200
    slots = (await api.internal.get(f"/internal/sessions/{sess.id}/slots")).json()
    assert slots[1]["option_id"] is not None and slots[1]["value"] == "침수 문제"
    assert slots[2]["option_id"] is None
    assert len(classifier.calls) == calls


async def test_concurrent_confirms_only_one_wins(api):
    sess = await api.new_session()
    first, second = await asyncio.gather(
        api.confirm(sess, "keyword", option_key="water"),
        api.confirm(sess, "keyword", option_key="fire"),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]


async def test_confirm_with_three_supporters_is_consensus(api):
    sess = await api.new_session()
    await to_phase(api, sess, "problem")
    for seat in ("p1", "p2", "p3"):
        await api.ai_support(sess, seat, "problem", "water_p2", "도심 폭우·침수 피해 증가")

    r = await api.confirm(sess, "problem", value="도심 폭우·침수 피해 증가", option_key="water_p2")

    assert r.status_code == 200, r.text
    assert r.json()["slot"]["outcome"] == "consensus"


async def test_outcome_is_candidate_decision_below_three_supporters_of_confirmed(api):
    """확정 안 지지자 2명, 다른 안에만 3명, 안 연결 없음은 모두 지원자 결정."""
    two = await api.new_session()
    await to_phase(api, two, "problem")
    for seat in ("p1", "p2"):
        await api.ai_support(two, seat, "problem", "water_p2", "도심 폭우·침수 피해 증가")
    r = await api.confirm(two, "problem", value="도심 폭우·침수 피해 증가", option_key="water_p2")
    assert r.json()["slot"]["outcome"] == "candidate_decision"

    other = await api.new_session()
    await to_phase(api, other, "problem")
    await api.ai_support(other, "p1", "problem", "water_p1", "가뭄으로 생활용수 제한이 잦아짐")
    for seat in ("p1", "p2", "p3"):  # p1은 다른 안으로 지지를 옮긴다
        await api.ai_support(other, seat, "problem", "water_p2", "도심 폭우·침수 피해 증가")
    r = await api.confirm(
        other, "problem", value="가뭄으로 생활용수 제한이 잦아짐", option_key="water_p1"
    )
    assert r.json()["slot"]["outcome"] == "candidate_decision"

    unlinked = await api.new_session()
    await to_phase(api, unlinked, "solution")
    r = await api.confirm(unlinked, "solution", value="우리 동네 물 지도 만들기")
    slots = (await api.internal.get(f"/internal/sessions/{unlinked.id}/slots")).json()
    assert slots[2]["option_id"] is None
    assert r.json()["slot"]["outcome"] == "candidate_decision"


def gate_after_commit(ctx):
    """다음으로 닫히는 DB 세션 하나를 커밋·close 뒤(프레임 emit 전) 멈춰 둔다. (멈춤 신호, 풀기)."""
    real = ctx.session_factory
    stopped, release = asyncio.Event(), asyncio.Event()
    armed = [True]

    class Gated:
        def __init__(self):
            self.inner = real()

        async def __aenter__(self):
            return await self.inner.__aenter__()

        async def __aexit__(self, *exc):
            out = await self.inner.__aexit__(*exc)
            if armed[0]:
                armed[0] = False
                stopped.set()
                await release.wait()
            return out

    ctx.session_factory = Gated
    return stopped, release


async def _race(ctx, first, second):
    """first가 커밋 뒤 멈춘 사이 second를 시작하고, 잠시 뒤 first를 푼다."""
    stopped, release = gate_after_commit(ctx)
    a = asyncio.create_task(first())
    await stopped.wait()
    b = asyncio.create_task(second())
    await asyncio.sleep(0.3)  # second가 먼저 emit할 기회를 준다
    release.set()
    return await asyncio.gather(a, b)


async def test_ai_message_committed_before_confirm_is_sent_before_confirm_frames(api, ctx):
    """A2: AI 발언 게시 커밋 뒤 전송 전에 지원자가 확정해도 프레임 순서 = 커밋 순서.

    확정 프레임(slot.confirmed·phase.changed) 뒤에 이전 단계 발언이 뜨지 않아야 한다.
    """
    sess = await api.new_session()
    await to_phase(api, sess, "solution")
    mark = api.mark(sess)
    message, r = await _race(
        ctx,
        lambda: api.post_ai(sess, "p3", "그 방향은 반대예요"),
        lambda: api.confirm(sess, "solution", value="센서·데이터 기반 물 관리·경보"),
    )
    assert r.status_code == 200, r.text

    frames = api.frames_since(sess, mark)
    order = [
        "ai" if f["type"] == "message.new" and f["payload"]["id"] == message["id"] else f["type"]
        for f in frames
        if f["type"] in ("message.new", "slot.confirmed", "phase.changed")
    ]
    assert order.index("ai") < order.index("slot.confirmed") < order.index("phase.changed")


async def test_start_committed_before_confirm_keeps_frame_and_generation_order(api, ctx):
    """시작 커밋 뒤 emit 전에 키워드 확정이 끼어도 keyword → problem 순, generation 역행 없음."""
    sess = await api.new_session(start=False)
    start, r = await _race(
        ctx,
        lambda: api.public.post(f"/s/{sess.token}/start", headers=sess.auth),
        lambda: api.confirm(sess, "keyword", value="물", option_key="water"),
    )
    assert start.status_code == 200 and r.status_code == 200, r.text
    phases = [f["payload"]["phase"] for f in api.frames(sess) if f["type"] == "phase.changed"]
    assert phases[:2] == ["keyword", "problem"]
    async with ctx.session_factory() as db:
        assert ctx.generations[sess.id] == (await db.get(Session, sess.id)).generation


class _StuckSocket:
    def __init__(self):
        self.never = asyncio.Event()

    async def send_json(self, data):
        await self.never.wait()

    async def close(self, code=1000):
        pass


async def test_slow_socket_does_not_block_writes_or_other_sessions(api, ctx):
    """전송이 멈춘 연결이 있어도 같은 세션 다음 쓰기·다른 세션 쓰기·리포트 발행이 막히지 않는다."""
    slow, other = await api.new_session(), await api.new_session()
    await ctx.hub.connect(slow.id, _StuckSocket())
    for text in ("첫 발언", "둘째 발언"):
        await asyncio.wait_for(api.post_ai(slow, "p1", text), 2)
    await asyncio.wait_for(api.post_ai(other, "p1", "다른 세션"), 2)
    assert [f["payload"]["content"] for f in api.frames(slow) if f["type"] == "message.new"][
        -2:
    ] == ["첫 발언", "둘째 발언"]

    locked = []
    publish = ctx.publisher.publish

    async def watch(routing_key, body):
        locked.append(ctx.ordered(uuid.UUID(body["session_id"])).locked())
        await publish(routing_key, body)

    ctx.publisher.publish = watch
    await asyncio.wait_for(finish(api, slow), 5)
    assert locked == [False]  # 브로커 발행은 순서 잠금 밖


async def test_hub_drop_on_send_timeout_records_connection_gap(api, ctx):
    """hub가 전송 타임아웃으로 먼저 끊어도 connection_gaps에 끊김이 한 번 기록된다."""
    from app.models import ConnectionGap
    from sqlalchemy import select

    sess = await api.new_session()
    ctx.hub.send_timeout = 0.05
    stuck = _StuckSocket()
    await ctx.hub.connect(sess.id, stuck)
    ctx.hub.enqueue(sess.id, "timer", {})
    await asyncio.sleep(0.3)
    assert not ctx.hub.is_connected(sess.id)
    assert not ctx.hub.disconnect(sess.id, stuck)  # 라우터 종료 처리는 다시 기록하지 않는다
    async with ctx.session_factory() as db:
        gaps = (
            await db.scalars(select(ConnectionGap).where(ConnectionGap.session_id == sess.id))
        ).all()
    assert len(gaps) == 1 and gaps[0].reconnected_at is None
