"""C10 검토: 차원 단위 조정·reviewer_name, 검증 422, 상태 409 우선, final 해시 = draft.
리포트 조회의 세션 없음·생성 중·생성 실패 구분과 두 실패 지점(초안 전·확정)의 재생성."""

import uuid

from app.queue import APPROVE, GENERATE
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


async def _get_report(api, sess, sid=None):
    url = f"/admin/sessions/{sid or sess.id}/report"
    return await api.public.get(url, headers=bearer(sess.admin))


async def _fail_report(api, sess):
    r = await api.internal.post(
        f"/internal/sessions/{sess.id}/report_failed", json={"error": "dlq"}
    )
    assert r.json() == {"status": "failed"}


async def test_report_get_separates_missing_generating_and_failed(api, ctx):
    sess = await api.new_session()
    r = await _get_report(api, sess, uuid.uuid4())
    assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")
    await finish(api, sess)
    r = await _get_report(api, sess)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "report_not_ready")

    await _fail_report(api, sess)
    r = await _get_report(api, sess)
    assert r.status_code == 409
    assert r.json()["error"] == {
        "code": "report_failed",
        "message": "report generation failed",
        "failed_stage": "report",
        "failed_step": "draft",
    }

    regen = await api.public.post(
        f"/admin/sessions/{sess.id}/report/regenerate", headers=bearer(sess.admin)
    )
    assert regen.json() == {"status": "completed"}
    assert ctx.publisher.published[-1][0] == GENERATE
    assert (await _get_report(api, sess)).json()["error"]["code"] == "report_not_ready"
    content = await draft_content(api, sess, [])
    await api.internal.post(f"/internal/sessions/{sess.id}/report/draft", json={"content": content})
    assert (await _get_report(api, sess)).status_code == 200


async def test_finalize_failure_regenerates_by_resuming_same_round_approve(api, ctx):
    sess = await api.new_session()
    content = await _ready(api, sess)
    body = {"adjustments": [], "reviewer_name": "박담당"}
    await api.public.post(
        f"/admin/sessions/{sess.id}/review", json=body, headers=bearer(sess.admin)
    )
    await _fail_report(api, sess)
    r = await _get_report(api, sess)
    assert r.status_code == 409
    assert (r.json()["error"]["code"], r.json()["error"]["failed_step"]) == (
        "report_failed",
        "finalize",
    )

    regen = await api.public.post(
        f"/admin/sessions/{sess.id}/report/regenerate", headers=bearer(sess.admin)
    )
    assert regen.json() == {"status": "approving"}
    assert ctx.publisher.published[-1] == (
        APPROVE,
        {"session_id": str(sess.id), "attempt": 1, "eval_round": 1},
    )
    final = await api.internal.post(
        f"/internal/sessions/{sess.id}/report/final", json={"content": content}
    )
    assert final.json()["status"] == "reviewed"
    report = (await _get_report(api, sess)).json()
    assert report["stage"] == "final" and report["review"]["reviewer_name"] == "박담당"


async def test_regenerate_hides_previous_draft_until_new_draft(api, ctx):
    """초안 저장 뒤(승인 전) 실패를 재생성하면 새 draft가 올 때까지 옛 draft를 내보내지 않는다."""
    sess = await api.new_session()
    content = await _ready(api, sess)
    await _fail_report(api, sess)
    regen = await api.public.post(
        f"/admin/sessions/{sess.id}/report/regenerate", headers=bearer(sess.admin)
    )
    assert regen.json() == {"status": "completed"}
    r = await _get_report(api, sess)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "report_not_ready")
    rows = (
        await api.public.get(
            f"/admin/positions/{sess.position_id}/candidates", headers=bearer(sess.admin)
        )
    ).json()
    assert rows[0]["elements"] is None

    fresh = {**content, "evaluation": {**content["evaluation"], "run_id": str(uuid.uuid4())}}
    await api.internal.post(f"/internal/sessions/{sess.id}/report/draft", json={"content": fresh})
    report = (await _get_report(api, sess)).json()
    assert report["evaluation"]["run_id"] == fresh["evaluation"]["run_id"]


async def test_regenerate_refused_when_report_failed_for_missing_scenario_copy(api, ctx):
    from app.services.session import REGENERATE_OUTDATED

    sess = await api.new_session()
    await finish(api, sess)
    error = "report.generate attempt 1: PinnedCopyMissing: position p scenario copy lacks prompts"
    await api.internal.post(f"/internal/sessions/{sess.id}/report_failed", json={"error": error})

    regen = await api.public.post(
        f"/admin/sessions/{sess.id}/report/regenerate", headers=bearer(sess.admin)
    )

    assert regen.status_code == 409
    assert regen.json()["error"] == {"code": "position_outdated", "message": REGENERATE_OUTDATED}
    assert (await _get_report(api, sess)).json()["error"]["code"] == "report_failed"
