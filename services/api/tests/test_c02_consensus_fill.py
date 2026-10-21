"""C2 AI 합의 채우기(내부 POST /slots/fill): 칸 확정과 공지가 한 트랜잭션, 합의 전 409."""

import uuid

from app.agent.runner import Stimulus
from app.models import AgentRun, Message
from kit import high, to_phase, types
from sqlalchemy import func, select

P2 = ("water_p2", "도심 폭우·침수 피해 증가")


async def _fill(api, sess, option_id, run_id, seat="p3"):
    return await api.internal.post(
        f"/internal/sessions/{sess.id}/slots/fill",
        json={
            "option_id": option_id,
            "seat": seat,
            "content": "그럼 도심 폭우·침수 피해 증가로 정리할게요.",
            "run_id": str(run_id),
        },
    )


async def test_fill_in_same_run_after_candidate_agrees(api, ctx, runner, classifier):
    sess = await api.new_session()
    await to_phase(api, sess, "problem")
    option_id = await api.ai_support(sess, "p1", "problem", *P2)
    await api.ai_support(sess, "p3", "problem", *P2)
    classifier.rules["저도 침수 문제가 맞다고 봐요"] = high("agree", P2[0])
    results = []

    async def hook(ctx_, session_id, stimulus, run_id):
        if stimulus.type == "message":
            results.append((run_id, await _fill(api, sess, option_id, run_id)))

    runner.hook = hook
    mark = api.mark(sess)
    await api.say(sess, "저도 침수 문제가 맞다고 봐요")

    run_id, r = results[0]
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["phase"] == "solution"
    assert (body["slot"]["filled_by"], body["slot"]["resolution"]) == ("p3", "consensus")
    assert body["slot"]["outcome"] == "consensus"
    frames = [f for f in api.frames_since(sess, mark) if f["type"] != "typing"]
    filled = types(frames)
    start = filled.index("message.new", filled.index("message.ack") + 2)
    assert filled[start : start + 4] == ["message.new", "slot.confirmed", "phase.changed", "timer"]
    assert frames[start]["payload"]["sender"] == "p3"
    async with ctx.session_factory() as db:
        notice = await db.scalar(select(Message).where(Message.run_id == run_id, Message.seq == 5))
        assert notice.meta["kind"] == "consensus_fill"

    again = await _fill(api, sess, option_id, run_id)
    assert again.status_code == 200 and again.json()["message"]["id"] == str(notice.id)
    # fill 커밋 뒤 같은 run_id를 다시 실행하면 낡은 자극이라 skipped, 공지는 1건 그대로
    async with ctx.session_factory() as db:
        run = await db.get(AgentRun, run_id)
        run.status = "queued"
        message_id = uuid.UUID(run.ref_id)
        await db.commit()
    runner.hook = None
    ctx.mailboxes.put(sess.id, Stimulus("message", "problem", run.generation, message_id), run_id)
    await ctx.mailboxes.drain()
    async with ctx.session_factory() as db:
        assert (await db.get(AgentRun, run_id)).status == "skipped"
        count = await db.scalar(
            select(func.count()).where(Message.session_id == sess.id, Message.seq == 5)
        )
        assert count == 1


async def test_fill_after_ai_stance_in_same_run(api, classifier):
    sess = await api.new_session()
    await to_phase(api, sess, "problem")
    option_id = await api.ai_support(sess, "p1", "problem", *P2)
    classifier.rules["침수 피해가 더 급해요"] = high("agree", P2[0])
    await api.say(sess, "침수 피해가 더 급해요")
    run_id = uuid.uuid4()
    assert (await _fill(api, sess, option_id, run_id)).json()["error"]["code"] == "no_consensus"

    await api.ai_support(sess, "p3", "problem", *P2)  # 이번 run의 AI 발언이 지지를 더함
    r = await _fill(api, sess, option_id, run_id)
    assert r.status_code == 200, r.text


async def test_withdrawn_support_is_no_consensus_and_saves_nothing(api, ctx, classifier):
    sess = await api.new_session()
    await to_phase(api, sess, "problem")
    option_id = await api.ai_support(sess, "p1", "problem", *P2)
    await api.ai_support(sess, "p3", "problem", *P2)
    classifier.rules["침수가 좋아요"] = high("agree", P2[0])
    classifier.rules["다시 생각해 보니 침수는 아니에요"] = high("oppose", P2[0])
    await api.say(sess, "침수가 좋아요")
    await api.say(sess, "다시 생각해 보니 침수는 아니에요")

    r = await _fill(api, sess, option_id, uuid.uuid4())

    assert r.status_code == 409 and r.json()["error"]["code"] == "no_consensus"
    state = await api.state(sess)
    assert state["session"]["phase"] == "problem"
    assert state["slots"][1]["status"] == "empty"
    async with ctx.session_factory() as db:
        notices = await db.scalar(
            select(func.count()).where(Message.session_id == sess.id, Message.seq == 5)
        )
    assert notices == 0


async def test_fill_checks_phase_then_slot_then_consensus(api):
    sess = await api.new_session()
    keyword_option = await api.ai_support(sess, "p1", "keyword", "fire", "불")
    await to_phase(api, sess, "problem")
    r = await _fill(api, sess, keyword_option, uuid.uuid4(), seat="p1")
    assert r.json()["error"]["code"] == "phase_not_open"
