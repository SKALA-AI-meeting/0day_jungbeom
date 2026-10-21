"""C10 검토: 차원 단위 조정·reviewer_name, 검증 422, 상태 409 우선, final 해시 = draft."""

from app.queue import APPROVE
from kit import bearer, draft_content, finish


async def _ready(api, sess):
    await api.say(sess, "물이 좋겠어요")
    messages = (await api.internal.get(f"/internal/sessions/{sess.id}/messages")).json()
    mine = next(m for m in messages if m["sender"] == "candidate")
    await finish(api, sess)
    content = await draft_content(api, sess, [f"msg:{mine['id']}"])
    r = await api.internal.post(
        f"/internal/sessions/{sess.id}/report/draft", json={"content": content}
    )
    assert r.status_code == 200 and r.json() == {"status": "report_ready"}
    return content


async def test_review_adjusts_one_dimension_and_final_keeps_draft_hash(api, ctx):
    sess = await api.new_session()
    content = await _ready(api, sess)
    dim = content["dimensions"][0]
    url = f"/admin/sessions/{sess.id}/review"
    adjustment = {"dimension_id": dim["dimension_id"], "level": 5, "memo": "압박에 근거로 답함"}

    for bad, code in [
        ({"adjustments": [{**adjustment, "memo": ""}], "reviewer_name": "박담당"}, "memo_required"),
        (
            {"adjustments": [{**adjustment, "dimension_id": "nope"}], "reviewer_name": "박담당"},
            "invalid_dimension",
        ),
        (
            {"adjustments": [adjustment, adjustment], "reviewer_name": "박담당"},
            "duplicate_dimension",
        ),
        ({"adjustments": [adjustment], "reviewer_name": ""}, "invalid_input"),
        ({"adjustments": ["nope"], "reviewer_name": "박담당"}, "invalid_input"),
    ]:
        r = await api.public.post(url, json=bad, headers=bearer(sess.admin))
        assert (r.status_code, r.json()["error"]["code"]) == (422, code)

    body = {"adjustments": [adjustment], "reviewer_name": "박담당"}
    r = await api.public.post(url, json=body, headers=bearer(sess.admin))
    assert r.status_code == 200 and r.json() == {"status": "approving"}
    assert ctx.publisher.published[-1] == (
        APPROVE,
        {"session_id": str(sess.id), "attempt": 1, "eval_round": 1},
    )
    assert (await api.public.post(url, json=body, headers=bearer(sess.admin))).status_code == 200
    other = await api.public.post(url, json={**body, "adjustments": []}, headers=bearer(sess.admin))
    assert (other.status_code, other.json()["error"]["code"]) == (409, "already_reviewed")

    changed = {**content, "facts": {"x": 1}}
    mismatch = await api.internal.post(
        f"/internal/sessions/{sess.id}/report/final", json={"content": changed}
    )
    assert mismatch.status_code == 409 and mismatch.json()["error"]["code"] == "draft_mismatch"
    final = await api.internal.post(
        f"/internal/sessions/{sess.id}/report/final", json={"content": content}
    )
    assert final.status_code == 200 and final.json()["status"] == "reviewed"

    report = (
        await api.public.get(f"/admin/sessions/{sess.id}/report", headers=bearer(sess.admin))
    ).json()
    merged = next(d for d in report["dimensions"] if d["dimension_id"] == dim["dimension_id"])
    assert (merged["adjusted_level"], merged["adjust_memo"]) == (5, "압박에 근거로 답함")
    element = next(e for e in report["elements"] if e["element"] == dim["element"])
    others = sum(1 for d in content["dimensions"] if d["element"] == dim["element"]) - 1
    expected = int((5 + 3 * others) / (others + 1) + 0.5)
    assert element["adjusted_level"] == expected and element["level"] == 3
    assert report["review"]["reviewer_name"] == "박담당" and report["review"]["reviewed_at"]
    assert "total" not in str(sorted(report)) and "score" not in report


async def test_candidate_list_chips_merge_adjustments_without_total(api):
    sess = await api.new_session()
    content = await _ready(api, sess)
    dim = content["dimensions"][0]
    await api.public.post(
        f"/admin/sessions/{sess.id}/review",
        json={
            "adjustments": [{"dimension_id": dim["dimension_id"], "level": 5, "memo": "근거 확인"}],
            "reviewer_name": "박담당",
        },
        headers=bearer(sess.admin),
    )
    rows = (
        await api.public.get(
            f"/admin/positions/{sess.position_id}/candidates", headers=bearer(sess.admin)
        )
    ).json()
    row = rows[0]
    chip = next(c for c in row["elements"] if c["element"] == dim["element"])
    assert chip["adjusted"] is True and chip["level"] >= 3 and row["level_source"] == "reviewer"
    assert row["display_group"] == "done" and not any("total" in k or "score" in k for k in row)
