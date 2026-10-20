"""완료 기준(api-admin): 관리자 엔드포인트가 계약 픽스처와 같은 형태, 기업 간 격리,
elements·mission_id 검증, 재초대는 failed(session)·만료·cancelled에만, regenerate는 리포트 실패
세션만, 시작 후 cancel, 목록 세 수·시각·이메일·활동·묶음, 검토
규칙(memo_required·already_reviewed·duplicate_item·reviewer_name), 검토 후 notes에 값 불변,
record 타임라인의 ref가 리포트 근거 record_ref 형태와 같음, candidate_count는 사람 수.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import Invite
from app.queue import APPROVE, GENERATE
from sqlalchemy import update

from tests.contract import CANDIDATE_OPTIONAL, assert_contract, assert_shape, load_contract
from tests.routers.support import bearer, to_report_ready


async def test_auth_catalog_and_positions_follow_contract(api, admin, invite):
    res = await api.post(
        "/admin/auth/signup", json={"email": "x@example.com", "password": "pw", "company_name": "X"}
    )
    assert_contract(res.json(), "admin_auth_token")
    dup = await api.post(
        "/admin/auth/signup", json={"email": "x@example.com", "password": "pw", "company_name": "X"}
    )
    assert (dup.status_code, dup.json()["error"]["code"]) == (409, "conflict")
    bad = await api.post("/admin/auth/login", json={"email": "x@example.com", "password": "no"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "unauthorized"

    catalog = (await api.get("/admin/catalog", headers=admin)).json()
    assert catalog == load_contract("admin_catalog")  # 생산자 응답이 공용 픽스처와 값까지 같다

    created = await api.post(
        "/admin/positions",
        json={
            "name": "PM 인턴",
            "elements": ["responsibility", "planning", "adaptability", "collaboration", "honesty"],
        },
        headers=admin,
    )
    assert_contract(created.json(), "admin_position_created")
    position = created.json()
    assert position["mission_id"] == "planning" and len(position["catalog_version"]) == 16
    cards = [(c["card_id"], c["at_min"]) for c in position["scenario"]["cards"]]
    expected = [
        (c["card_id"], c["at_min"])
        for c in load_contract("admin_position_created")["scenario"]["cards"]
    ]
    assert cards == expected

    # 지원자 수는 사람 수: 실패 뒤 재응시(같은 별칭)는 한 사람
    first = await invite(position["id"], "지원자A")
    await invite(position["id"], "지원자B")
    listed = (await api.get("/admin/positions", headers=admin)).json()
    assert_contract(listed, "admin_positions")
    assert listed[0]["candidate_count"] == 2
    del first


async def test_position_input_is_validated(api, admin):
    for elements in ([], ["planning", "planning"], ["unknown"], ["responsibility"] * 6):
        res = await api.post(
            "/admin/positions", json={"name": "x", "elements": elements}, headers=admin
        )
        assert (res.status_code, res.json()["error"]["code"]) == (422, "invalid_elements"), elements
    res = await api.post(
        "/admin/positions",
        json={"name": "x", "elements": ["planning"], "mission_id": "dev"},
        headers=admin,
    )
    assert (res.status_code, res.json()["error"]["code"]) == (422, "invalid_mission")


async def test_invite_candidates_cancel_and_reinvite(api, admin, new_position, invite, db, service):
    position = await new_position()
    row = await invite(position["id"], "지원자A")
    assert_contract(row, "admin_invite")
    assert "지원자A" in row["notice_text"] and row["invite_url"] in row["notice_text"]
    dup = await api.post(
        f"/admin/positions/{position['id']}/invites",
        json={"alias": "지원자A", "email": "a@x.com"},
        headers=admin,
    )
    assert (dup.status_code, dup.json()["error"]["code"]) == (409, "conflict")

    # 재초대: 진행 중 세션은 422, 시작 후 취소(중도 포기) 뒤에는 retry로 이어진다
    sid = uuid.UUID(row["session_id"])
    await service.consent(sid)
    await service.start(sid)
    early = await api.post(
        f"/admin/positions/{position['id']}/invites",
        json={"alias": "지원자A", "email": "a@x.com", "previous_session_id": str(sid)},
        headers=admin,
    )
    assert (early.status_code, early.json()["error"]["code"]) == (422, "invalid_previous_session")
    cancelled = await api.post(f"/admin/sessions/{sid}/cancel", headers=admin)
    assert_contract(cancelled.json(), "admin_cancel")
    retry = await api.post(
        f"/admin/positions/{position['id']}/invites",
        json={"alias": "지원자A", "email": "a@x.com", "previous_session_id": str(sid)},
        headers=admin,
    )
    assert retry.status_code == 200

    # 만료 초대의 재발행은 reissue
    stale = await invite(position["id"], "지원자C")
    await db.execute(
        update(Invite)
        .where(Invite.alias == "지원자C")
        .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db.commit()
    await api.post(
        f"/admin/positions/{position['id']}/invites",
        json={"alias": "지원자C", "email": "c@x.com", "previous_session_id": stale["session_id"]},
        headers=admin,
    )
    rows = (await api.get(f"/admin/positions/{position['id']}/candidates", headers=admin)).json()
    assert_contract(rows, "admin_candidates", CANDIDATE_OPTIONAL)
    by_status = [
        (r["alias"], r["display_status"], r["display_group"], r.get("previous_relation"))
        for r in rows
    ]
    assert by_status == [
        ("지원자A", "cancelled", "problem", None),
        ("지원자A", "invited", "waiting", "retry"),
        ("지원자C", "expired", "waiting", None),
        ("지원자C", "invited", "waiting", "reissue"),
    ]
    assert rows[0]["started_at"] and rows[0]["email"] == "cand@example.com"
    assert all(r["met"] is None and r["by_element"] is None for r in rows)


async def test_other_company_gets_404_everywhere(
    api, internal, db, service, other_admin, new_position, invite
):
    position = await new_position()
    row = await invite(position["id"])
    sid = row["session_id"]
    paths = [
        ("GET", f"/admin/positions/{position['id']}/candidates"),
        ("POST", f"/admin/positions/{position['id']}/invites"),
        ("POST", f"/admin/sessions/{sid}/cancel"),
        ("GET", f"/admin/sessions/{sid}/report"),
        ("GET", f"/admin/sessions/{sid}/record"),
        ("POST", f"/admin/sessions/{sid}/report/regenerate"),
        ("POST", f"/admin/sessions/{sid}/report/notes"),
        ("POST", f"/admin/sessions/{sid}/review"),
    ]
    for method, path in paths:
        body = {"alias": "x", "email": "x@x.com", "text": "t", "reviewer_name": "r"}
        res = await api.request(method, path, json=body, headers=other_admin)
        assert res.status_code == 404, path
    assert (await api.get("/admin/positions", headers=other_admin)).json() == []
    assert (await api.get("/admin/catalog")).status_code == 401
    assert (await api.get("/admin/catalog", headers=bearer("garbage"))).status_code == 401


async def test_report_review_notes_and_record(
    api, internal, admin, db, service, new_position, invite, publisher
):
    position = await new_position()
    row = await invite(position["id"])
    sid, content = await to_report_ready(api, internal, db, service, position, row)

    report = (await api.get(f"/admin/sessions/{sid}/report", headers=admin)).json()
    fixture = load_contract("report")
    assert set(report) == set(fixture)
    for key in ("position", "rubric", "notes", "connection_gaps"):
        assert_shape(report[key], fixture[key], f"report.{key}")
    assert_shape(
        report["deliverable"]["final"], fixture["deliverable"]["final"], "deliverable.final"
    )
    assert report["rubric"]["review"] is None and report["notes"] == []

    rows = (await api.get(f"/admin/positions/{position['id']}/candidates", headers=admin)).json()
    assert (rows[0]["score_source"], rows[0]["display_group"]) == ("auto", "needs_review")
    totals = content["rubric"]["auto_total"]
    assert (rows[0]["met"], rows[0]["unmet"], rows[0]["no_record"]) == (
        totals["met"],
        totals["unmet"],
        totals["no_record"],
    )

    items = [i for e in content["rubric"]["elements"] for c in e["cards"] for i in c["items"]]
    target = next(i for i in items if i["auto"] == 0)
    review = f"/admin/sessions/{sid}/review"
    no_memo = await api.post(
        review,
        json={"adjustments": [{"item_id": target["id"], "value": 1}], "reviewer_name": "김담당"},
        headers=admin,
    )
    assert (no_memo.status_code, no_memo.json()["error"]["code"]) == (400, "memo_required")
    twice = {"item_id": target["id"], "value": 1, "memo": "근거 확인"}
    dup = await api.post(
        review, json={"adjustments": [twice, twice], "reviewer_name": "김담당"}, headers=admin
    )
    assert dup.json()["error"]["code"] == "duplicate_item"
    unknown = await api.post(
        review,
        json={"adjustments": [{**twice, "item_id": "nope"}], "reviewer_name": "김담당"},
        headers=admin,
    )
    assert unknown.json()["error"]["code"] == "invalid_item"
    nameless = await api.post(
        review, json={"adjustments": [twice], "reviewer_name": ""}, headers=admin
    )
    assert nameless.status_code == 422

    early_note = await api.post(
        f"/admin/sessions/{sid}/report/notes",
        json={"text": "t", "reviewer_name": "김담당"},
        headers=admin,
    )
    assert early_note.status_code == 409  # 검토 완료 전
    body = {"adjustments": [twice], "memo": "자동 서술과 일치", "reviewer_name": "김담당"}
    done = await api.post(review, json=body, headers=admin)
    assert_contract(done.json(), "admin_review_response")
    assert (
        await api.post(review, json=body, headers=admin)
    ).json() == done.json()  # 같은 본문 멱등
    changed = await api.post(review, json={**body, "memo": "다름"}, headers=admin)
    assert (changed.status_code, changed.json()["error"]["code"]) == (409, "already_reviewed")
    assert publisher.published[-1] == (APPROVE, {"session_id": str(sid), "attempt": 1})

    merged = (await api.get(f"/admin/sessions/{sid}/report", headers=admin)).json()
    adjusted = next(
        i
        for e in merged["rubric"]["elements"]
        for c in e["cards"]
        for i in c["items"]
        if i["id"] == target["id"]
    )
    assert (adjusted["reviewer"], adjusted["memo"], adjusted["adjusted"]) == (1, "근거 확인", True)
    assert merged["rubric"]["reviewer_total"]["met"] == totals["met"] + 1
    assert merged["rubric"]["review"]["reviewer_name"] == "김담당"

    note = await api.post(
        f"/admin/sessions/{sid}/report/notes",
        json={"text": "면접에서 확인", "reviewer_name": "김담당"},
        headers=admin,
    )
    assert_contract(note.json(), "admin_report_notes")
    after = (await api.get(f"/admin/sessions/{sid}/report", headers=admin)).json()
    assert (
        after["rubric"] == merged["rubric"] and len(after["notes"]) == 1
    )  # 메모는 값을 바꾸지 않는다
    rows = (await api.get(f"/admin/positions/{position['id']}/candidates", headers=admin)).json()
    assert rows[0]["score_source"] == "reviewer" and rows[0]["met"] == totals["met"] + 1
    assert (rows[0]["status"], rows[0]["display_group"]) == ("approving", "done")  # 확정 중=완료

    record = (await api.get(f"/admin/sessions/{sid}/record", headers=admin)).json()
    assert_contract(record, "admin_record")
    assert record and all(
        e["ref"]["type"]
        in ("message", "share", "open", "task_event", "assistant_call", "connection_gap")
        for e in record
    )
    assert record == sorted(record, key=lambda e: e["t_min"])


async def test_regenerate_only_after_report_failure(
    api, internal, admin, db, service, new_position, invite, publisher
):
    position = await new_position(["planning"])
    row = await invite(position["id"])
    sid, _ = await to_report_ready(api, internal, db, service, position, row)
    not_failed = await api.post(f"/admin/sessions/{sid}/report/regenerate", headers=admin)
    assert not_failed.status_code == 409
    await internal.post(f"/internal/sessions/{sid}/report_failed", json={"error": "dlq"})
    rows = (await api.get(f"/admin/positions/{position['id']}/candidates", headers=admin)).json()
    assert rows[0]["next_action"] == "리포트를 다시 생성하세요"
    publisher.published.clear()
    regenerated = await api.post(f"/admin/sessions/{sid}/report/regenerate", headers=admin)
    assert_contract(regenerated.json(), "admin_report_regenerate")
    assert publisher.published == [(GENERATE, {"session_id": str(sid), "attempt": 1})]
    assert (await api.get(f"/admin/sessions/{sid}/report", headers=admin)).status_code == 404
