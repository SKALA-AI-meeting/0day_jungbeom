"""C4 침묵 초대: invite_delivered가 false인 동안 다음 틱에 idle을 다시 넣는다."""

import asyncio
import uuid

from app.agent.runner import RunResult
from app.scheduler import tick
from kit import to_phase


async def test_idle_deferred_then_reenqueued_and_invite_once(api, ctx, clock, runner):
    sess = await api.new_session(minutes=60)
    await to_phase(api, sess, "solution")
    idle_runs = []

    async def hook(ctx_, session_id, stimulus, run_id):
        if stimulus.type != "idle":
            return None
        idle_runs.append(run_id)
        if len(idle_runs) == 1:  # 첫 실행은 지원자 입력 중이라 게시하지 않음
            return RunResult(status="deferred")
        await api.post_ai(
            sess,
            "p3",
            "김지원님은 어떻게 생각하세요?",
            is_invite=True,
            expected_generation=stimulus.generation,
        )
        return None

    runner.hook = hook
    clock.advance(minutes=3, seconds=1)  # L/20
    await tick(ctx)
    await ctx.mailboxes.drain()
    assert len(idle_runs) == 1
    clock.advance(seconds=5)
    await tick(ctx)
    await ctx.mailboxes.drain()
    assert len(idle_runs) == 2 and idle_runs[0] != idle_runs[1]

    clock.advance(seconds=5)
    await tick(ctx)
    await ctx.mailboxes.drain()
    assert len(idle_runs) == 2  # 전달됐으면 더 넣지 않는다
    second = await api.internal.post(
        f"/internal/sessions/{sess.id}/messages",
        json={
            "sender": "p3",
            "content": "한 번 더?",
            "run_id": str(uuid.uuid4()),
            "seq": 1,
            "is_invite": True,
        },
    )
    assert second.status_code == 409

    await api.say(sess, "저는 데이터 쪽이 좋아요")
    await api.say(sess, "비용도 생각해야 해요")
    messages = (
        await api.internal.get(
            f"/internal/sessions/{sess.id}/messages", params={"phase": "solution"}
        )
    ).json()
    mine = [m for m in messages if m["sender"] == "candidate"]
    assert [m["origin"] for m in mine] == ["invited", "spontaneous"]
    session = (await api.internal.get(f"/internal/sessions/{sess.id}")).json()
    assert session["invite_delivered_phases"] == ["solution"]


async def test_idle_not_enqueued_while_candidate_typing_or_pending(api, ctx, clock, runner):
    sess = await api.new_session(minutes=60)
    clock.advance(minutes=3, seconds=1)
    ctx.hub.candidate_typing(sess.id, "start")
    await tick(ctx)
    await ctx.mailboxes.drain()
    assert "idle" not in runner.types()

    release = asyncio.Event()

    async def hold(ctx_, session_id, stimulus, run_id):
        if stimulus.type == "idle":
            await release.wait()

    runner.hook = hold
    clock.advance(seconds=7)  # typing 6초 만료
    started = len(runner.calls)
    await tick(ctx)
    await asyncio.sleep(0.05)
    await tick(ctx)  # 같은 단계 idle이 대기·실행 중이면 다시 넣지 않는다
    release.set()
    await ctx.mailboxes.drain()
    assert runner.types()[started:].count("idle") == 1
