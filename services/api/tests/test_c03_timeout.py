"""C3 시간 초과: 스케줄러가 그래프 없이 api에서 결정적으로 채운다."""

from datetime import datetime, timedelta

from app.scheduler import tick
from kit import high, to_phase, types


async def test_timeout_fills_most_supported_option_without_graph(
    api, ctx, clock, runner, classifier
):
    sess = await api.new_session(minutes=60)
    await to_phase(api, sess, "problem")
    await api.ai_support(sess, "p1", "problem", "water_p2", "도심 폭우·침수 피해 증가")
    await api.ai_support(sess, "p3", "problem", "water_p2", "도심 폭우·침수 피해 증가")
    classifier.rules["가뭄 문제가 커요"] = high("propose", "water_p1")
    await api.say(sess, "가뭄 문제가 커요")
    session = (await api.internal.get(f"/internal/sessions/{sess.id}")).json()
    deadline = datetime.fromisoformat(session["phase_deadline_at"])

    clock.set(deadline - timedelta(seconds=10))
    mark = api.mark(sess)
    await tick(ctx)
    await ctx.mailboxes.drain()
    assert "slot.confirmed" not in types(api.frames_since(sess, mark))

    clock.set(deadline)
    calls = len(runner.calls)
    mark = api.mark(sess)
    await tick(ctx)
    await ctx.mailboxes.drain()

    frames = api.frames_since(sess, mark)
    assert types(frames)[:3] == ["message.new", "slot.confirmed", "phase.changed"]
    notice, slot = frames[0]["payload"], frames[1]["payload"]
    assert notice["sender"] == "p3" and notice["content"].startswith("시간이 다 돼서")
    assert "도심 폭우·침수 피해 증가" in notice["content"]
    assert (slot["resolution"], slot["filled_by"]) == ("timeout", "p3")
    assert frames[2]["payload"]["reason"] == "timeout"
    assert [s.type for _, s, _ in runner.calls[calls:]] == ["phase_started"]


async def test_timeout_without_options_uses_default_keyword(api, ctx, clock):
    sess = await api.new_session(minutes=15)
    session = (await api.internal.get(f"/internal/sessions/{sess.id}")).json()
    clock.set(datetime.fromisoformat(session["phase_deadline_at"]))
    await tick(ctx)
    slots = (await api.internal.get(f"/internal/sessions/{sess.id}/slots")).json()
    assert (slots[0]["value"], slots[0]["resolution"], slots[0]["filled_by"]) == (
        "물",
        "timeout",
        "p3",
    )
