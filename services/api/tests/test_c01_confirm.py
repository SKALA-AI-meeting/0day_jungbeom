"""C1 지원자 확정과 단계·칸 규칙(design.md "단계·칸")."""

import asyncio
from datetime import datetime, timedelta

from kit import high, to_phase, types


async def test_keyword_confirm_frames_support_and_cumulative_deadline(api, ctx, classifier):
    sess = await api.new_session(minutes=60)
    classifier.rules["물이 좋겠어요"] = high("propose", "water")
    await api.say(sess, "물이 좋겠어요")
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

    slots = (await api.internal.get(f"/internal/sessions/{sess.id}/slots")).json()
    assert slots[0]["support"][0]["supporters"] == ["candidate"]
    state = await api.state(sess)
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
