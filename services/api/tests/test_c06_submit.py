"""C6 제출과 자동 제출: 같은 요청 안에서 completed, 큐 report.generate{eval_round: 1}."""

from datetime import datetime

from app.queue import GENERATE
from app.scheduler import tick
from kit import to_phase, types


async def test_submit_completes_and_blocks_later_writes(api, ctx):
    sess = await api.new_session()
    early = await api.public.post(
        f"/sessions/{sess.id}/proposal/submit", headers=sess.auth, json={}
    )
    assert early.status_code == 409 and early.json()["error"]["code"] == "phase_not_open"
    await to_phase(api, sess, "proposal")
    proposal = (await api.public.get(f"/sessions/{sess.id}/proposal", headers=sess.auth)).json()
    assert proposal["sections"]["keyword"] == "물"  # proposal 진입 때 확정 칸 값으로 채움
    mark = api.mark(sess)

    r = await api.public.post(f"/sessions/{sess.id}/proposal/submit", headers=sess.auth, json={})

    assert r.status_code == 200 and r.json()["status"] == "completed"
    session = (await api.internal.get(f"/internal/sessions/{sess.id}")).json()
    assert session["status"] == "completed" and session["ended_at"]
    ended = [f for f in api.frames_since(sess, mark) if f["type"] == "session.ended"]
    assert ended[0]["payload"] == {"reason": "submitted"}
    assert ctx.publisher.published == [
        (GENERATE, {"session_id": str(sess.id), "attempt": 1, "eval_round": 1})
    ]
    again = await api.public.post(
        f"/sessions/{sess.id}/proposal/submit", headers=sess.auth, json={}
    )
    assert again.status_code == 200
    mark = api.mark(sess)
    await api.say(sess, "제출 뒤 메시지")
    assert api.frames_since(sess, mark)[0]["payload"]["code"] == "session_ending"


async def test_auto_submit_at_ends_at(api, ctx, clock):
    sess = await api.new_session(minutes=15)
    put = await api.public.put(
        f"/sessions/{sess.id}/proposal",
        headers=sess.auth,
        json={
            "sections": {
                "keyword": "물",
                "problem": "",
                "solution": "",
                "rationale": "근거",
                "expected_effect": "",
                "idea_credit": "",
            },
            "revision": 0,
        },
    )
    assert put.status_code == 200, put.text
    state = await api.state(sess)
    clock.set(datetime.fromisoformat(state["session"]["ends_at"]))
    mark = api.mark(sess)

    await tick(ctx)

    proposal = (await api.internal.get(f"/internal/sessions/{sess.id}/proposal")).json()
    assert proposal["auto_submitted"] is True and proposal["sections"]["rationale"] == "근거"
    assert "session.ended" in types(api.frames_since(sess, mark))
    assert [f for f in api.frames_since(sess, mark) if f["type"] == "session.ended"][0][
        "payload"
    ] == {"reason": "timeout"}
    assert ctx.publisher.published[0][1]["eval_round"] == 1
