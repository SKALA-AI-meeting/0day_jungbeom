"""C6 제출과 자동 제출: 같은 요청 안에서 completed, 큐 report.generate{eval_round: 1}."""

from datetime import datetime

from app.models import Proposal
from app.queue import GENERATE
from app.scheduler import tick
from kit import bearer, to_phase, types


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
    row = await _proposal_row(ctx, sess)
    assert row.submit_blank_sections == ["problem", "solution", "expected_effect", "idea_credit"]
    assert row.blank_warning_shown is None
    assert await _submit_summary(api, sess) == "자동 제출 · 빈 칸 4개"
    assert "session.ended" in types(api.frames_since(sess, mark))
    assert [f for f in api.frames_since(sess, mark) if f["type"] == "session.ended"][0][
        "payload"
    ] == {"reason": "timeout"}
    assert ctx.publisher.published[0][1]["eval_round"] == 1


async def _submit_summary(api, sess) -> str:
    record = (
        await api.public.get(f"/admin/sessions/{sess.id}/record", headers=bearer(sess.admin))
    ).json()
    return next(i["summary"] for i in record if i["type"] == "proposal_submit")


async def _proposal_row(ctx, sess) -> Proposal:
    async with ctx.session_factory() as db:
        return await db.get(Proposal, sess.id)


async def _submit_with_blanks(api, sess) -> None:
    """앞 3칸은 확정 값, rationale은 공백뿐, 나머지 둘은 빈 칸으로 경고 확인 뒤 제출한다."""
    await to_phase(api, sess, "proposal")
    proposal = (await api.public.get(f"/sessions/{sess.id}/proposal", headers=sess.auth)).json()
    sections = {**proposal["sections"], "rationale": "  \n", "expected_effect": "효과"}
    put = await api.public.put(
        f"/sessions/{sess.id}/proposal",
        headers=sess.auth,
        json={"sections": sections, "revision": proposal["revision"]},
    )
    assert put.status_code == 200, put.text
    r = await api.public.post(
        f"/sessions/{sess.id}/proposal/submit",
        headers=sess.auth,
        json={"blank_warning_shown": True},
    )
    assert r.status_code == 200, r.text


async def test_submit_saves_blank_sections_and_warning(api, ctx):
    sess = await api.new_session()

    await _submit_with_blanks(api, sess)

    row = await _proposal_row(ctx, sess)
    assert row.submit_blank_sections == ["rationale", "idea_credit"]
    assert row.blank_warning_shown is True and row.auto_submitted is False


async def test_facts_expose_blank_sections(api):
    sess = await api.new_session()
    await _submit_with_blanks(api, sess)

    facts = (await api.internal.get(f"/internal/sessions/{sess.id}/facts")).json()

    assert facts["blank_sections_at_submit"] == ["rationale", "idea_credit"]
    assert facts["blank_warning_acknowledged"] is True


async def test_record_summary_counts_blank_sections(api):
    sess = await api.new_session()
    await _submit_with_blanks(api, sess)

    record = (
        await api.public.get(f"/admin/sessions/{sess.id}/record", headers=bearer(sess.admin))
    ).json()

    submit = [i for i in record if i["type"] == "proposal_submit"]
    assert [i["summary"] for i in submit] == ["제출 · 빈 칸 2개(경고 확인 후 제출)"]


async def test_manual_submit_without_flag_saves_false_and_stays_on_retry(api, ctx):
    sess = await api.new_session()
    await to_phase(api, sess, "proposal")
    row = await _proposal_row(ctx, sess)
    assert (row.submit_blank_sections, row.blank_warning_shown) == (None, None)
    full = {f: "내용" for f in ("keyword", "problem", "solution", "rationale", "expected_effect")}
    await api.public.put(
        f"/sessions/{sess.id}/proposal",
        headers=sess.auth,
        json={"sections": {**full, "idea_credit": "없음"}, "revision": 1},
    )

    await api.public.post(f"/sessions/{sess.id}/proposal/submit", headers=sess.auth, json={})
    again = await api.public.post(
        f"/sessions/{sess.id}/proposal/submit",
        headers=sess.auth,
        json={"blank_warning_shown": True},
    )

    assert again.status_code == 200
    row = await _proposal_row(ctx, sess)
    assert (row.submit_blank_sections, row.blank_warning_shown) == ([], False)
    assert await _submit_summary(api, sess) == "제출 · 빈 칸 0개(경고 없이 제출)"


async def test_auto_submit_without_blanks_keeps_values_on_manual_retry(api, ctx, clock):
    sess = await api.new_session(minutes=15)
    sections = {
        f: "내용"
        for f in ("keyword", "problem", "solution", "rationale", "expected_effect", "idea_credit")
    }
    put = await api.public.put(
        f"/sessions/{sess.id}/proposal",
        headers=sess.auth,
        json={"sections": sections, "revision": 0},
    )
    assert put.status_code == 200, put.text
    state = await api.state(sess)
    clock.set(datetime.fromisoformat(state["session"]["ends_at"]))
    await tick(ctx)

    await api.public.post(
        f"/sessions/{sess.id}/proposal/submit",
        headers=sess.auth,
        json={"blank_warning_shown": True},
    )

    row = await _proposal_row(ctx, sess)
    assert (row.submit_blank_sections, row.blank_warning_shown) == ([], None)
    assert await _submit_summary(api, sess) == "자동 제출 · 빈 칸 0개"
