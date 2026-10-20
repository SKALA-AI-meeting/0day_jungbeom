"""완료 기준: /admin 응답 형식, 기업 간 격리, elements 검증, 권한 밖 403, 리뷰 규칙."""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import Invite, Report, RubricAdjustment
from app.queue import APPROVE
from sqlalchemy import select, update

from tests.routers.support import bearer, to_report_ready


async def test_signup_login_catalog_and_positions_follow_contract(api, new_position, invite):
    res = await api.post(
        "/admin/auth/signup", json={"email": "x@example.com", "password": "pw", "company_name": "X"}
    )
    assert set(res.json()) == {"token"}
    login = await api.post("/admin/auth/login", json={"email": "x@example.com", "password": "pw"})
    assert login.status_code == 200 and login.json()["token"]
    bad = await api.post("/admin/auth/login", json={"email": "x@example.com", "password": "no"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "unauthorized"
    missing = await api.post("/admin/auth/login", json={"email": "x@example.com"})
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "invalid_input"

    headers = bearer(login.json()["token"])
    catalog = (await api.get("/admin/catalog", headers=headers)).json()
    assert catalog["session_minutes"] == 120
    assert [e["id"] for e in catalog["elements"]] == [
        "cooperation",
        "responsibility",
        "flexibility",
        "respect",
    ]
    coop = catalog["elements"][0]
    assert coop["name"] == "협력 태도" and coop["situation_public"]
    assert {
        "id": "coop_replied_within_5m",
        "text": "요청 후 5분 안에 답함",
        "pilot_value": True,
    } in (coop["rubric"])
    assert [f["card_id"] for f in catalog["timeline"]["flow"]] == [
        "kickoff",
        "division",
        "review",
        "report_request",
    ]
    assert catalog["timeline"]["element_fraction_rule"] and catalog["candidate_notice_template"]

    position = (
        await api.post(
            "/admin/positions",
            json={"name": "기획", "elements": ["cooperation", "respect"]},
            headers=headers,
        )
    ).json()
    assert set(position) == {"id", "name", "elements", "scenario", "catalog_version"}
    assert position["elements"] == ["cooperation", "respect"]
    assert position["scenario"]["session_minutes"] == 120 and position["catalog_version"]

    await invite(position["id"], headers=headers)
    listing = (await api.get("/admin/positions", headers=headers)).json()
    assert [(p["name"], p["candidate_count"]) for p in listing] == [("기획", 1)]
    assert set(listing[0]) == {"id", "name", "elements", "candidate_count", "created_at"}


async def test_position_elements_are_validated(api, admin):
    for elements in ([], ["cooperation", "cooperation"], ["nope"], ["cooperation"] * 5):
        res = await api.post(
            "/admin/positions", json={"name": "기획", "elements": elements}, headers=admin
        )
        assert res.status_code == 400, elements
        assert res.json()["error"]["code"] == "invalid_elements"


async def test_invite_candidates_and_cancel(api, admin, new_position, invite, db, service):
    position = await new_position()
    created = await invite(position["id"], "지원자A")
    assert set(created) == {"session_id", "invite_url", "expires_at", "notice_text"}
    assert "/s/" in created["invite_url"]
    token = created["invite_url"].rsplit("/s/", 1)[1]
    assert token not in str((await db.execute(select(Invite.token_hash))).scalars().all())
    assert "2시간" in created["notice_text"] and created["invite_url"] in created["notice_text"]

    rows = (await api.get(f"/admin/positions/{position['id']}/candidates", headers=admin)).json()
    assert rows[0]["alias"] == "지원자A"
    assert (rows[0]["status"], rows[0]["display_status"], rows[0]["score"]) == (
        "invited",
        "invited",
        None,
    )

    # 시작 전 만료는 표시값 expired로 보인다
    await db.execute(update(Invite).values(expires_at=datetime.now(UTC) - timedelta(hours=1)))
    await db.commit()
    rows = (await api.get(f"/admin/positions/{position['id']}/candidates", headers=admin)).json()
    assert (rows[0]["status"], rows[0]["display_status"]) == ("invited", "expired")

    sid = created["session_id"]
    res = await api.post(f"/admin/sessions/{sid}/cancel", headers=admin)
    assert res.json() == {"status": "cancelled"}
    rows = (await api.get(f"/admin/positions/{position['id']}/candidates", headers=admin)).json()
    assert rows[0]["display_status"] == "cancelled"

    # invited가 아니면 409
    second = await invite(position["id"], "지원자B")
    await db.execute(update(Invite).values(expires_at=datetime.now(UTC) + timedelta(hours=1)))
    await db.commit()
    started = uuid.UUID(second["session_id"])
    await service.consent(started)
    await service.start(started)
    res = await api.post(f"/admin/sessions/{started}/cancel", headers=admin)
    assert res.status_code == 409 and res.json()["error"]["code"] == "conflict"


async def test_other_company_gets_404_everywhere(
    api, internal, db, service, admin, other_admin, new_position, invite
):
    position = await new_position()
    created = await invite(position["id"])
    sid, _ = await to_report_ready(api, internal, db, service, position, created)

    calls = [
        api.get(f"/admin/positions/{position['id']}/candidates", headers=other_admin),
        api.post(
            f"/admin/positions/{position['id']}/invites",
            json={"alias": "x", "email": "x@example.com"},
            headers=other_admin,
        ),
        api.post(f"/admin/sessions/{sid}/cancel", headers=other_admin),
        api.get(f"/admin/sessions/{sid}/report", headers=other_admin),
        api.post(
            f"/admin/sessions/{sid}/review",
            json={"adjustments": [], "memo": ""},
            headers=other_admin,
        ),
    ]
    for call in calls:
        res = await call
        assert res.status_code == 404, res.text
    assert (await api.get("/admin/positions", headers=other_admin)).json() == []
    # 다른 회사 세션을 재응시 연결로 지정할 수도 없다
    other_position = await new_position(headers=other_admin)
    res = await api.post(
        f"/admin/positions/{other_position['id']}/invites",
        json={"alias": "y", "email": "y@example.com", "previous_session_id": str(sid)},
        headers=other_admin,
    )
    assert res.status_code == 404


async def test_admin_routes_reject_missing_or_non_admin_tokens(api):
    from app.auth import session_token

    assert (await api.get("/admin/positions")).status_code == 401
    token = session_token(uuid.uuid4(), 120)
    res = await api.get("/admin/positions", headers=bearer(token))
    assert res.status_code == 403 and res.json()["error"]["code"] == "forbidden"


async def test_report_merges_deliverable_and_review_adjustments(
    api, internal, db, service, admin, new_position, invite, publisher
):
    position = await new_position()
    created = await invite(position["id"], "지원자A")
    sid = uuid.UUID(created["session_id"])
    res = await api.get(f"/admin/sessions/{sid}/report", headers=admin)
    assert res.status_code == 404  # 아직 없음

    sid, content = await to_report_ready(api, internal, db, service, position, created)
    report = (await api.get(f"/admin/sessions/{sid}/report", headers=admin)).json()
    assert (report["stage"], report["alias"], report["reviewed_at"]) == ("draft", "지원자A", None)
    assert report["position"] == {
        "name": "프로덕트 기획",
        "elements": ["cooperation", "responsibility"],
    }
    parts = report["deliverable"]["parts"]
    assert [(p["part_no"], p["revisions"], p["empty"]) for p in parts] == [
        (n, 0, True) for n in range(1, 6)
    ]
    assert parts[0]["title"] == "문제 정의와 대상 사용자"
    rubric = report["rubric"]
    assert rubric["reviewer_total"] is None and rubric["review"] is None
    assert rubric["history"] == []
    assert rubric["auto_total"] == {"met": 4, "judged": 6, "no_record": 2}

    items = [i for e in rubric["elements"] for i in e["items"]]
    zero = next(i for i in items if i["auto"] == 0)
    nothing = next(i for i in items if i["auto"] is None)
    one = next(i for i in items if i["auto"] == 1)

    def review(body):
        return api.post(f"/admin/sessions/{sid}/review", json=body, headers=admin)

    # 규칙 위반은 아무것도 바꾸지 않는다
    res = await review({"adjustments": [{"item_id": zero["id"], "value": 1, "memo": " "}]})
    assert (res.status_code, res.json()["error"]["code"]) == (400, "memo_required")
    res = await review({"adjustments": [{"item_id": "nope", "value": 1, "memo": "x"}]})
    assert (res.status_code, res.json()["error"]["code"]) == (400, "invalid_item")
    dup = {"item_id": zero["id"], "value": 1, "memo": "x"}
    res = await review({"adjustments": [dup, dup]})
    assert (res.status_code, res.json()["error"]["code"]) == (400, "duplicate_item")
    assert (await db.execute(select(RubricAdjustment))).scalars().all() == []
    assert publisher.published[-1][0] != APPROVE

    # 자동 값과 같은 항목은 조정이 아니라 메모 없이도 통과한다
    body = {
        "adjustments": [
            {"item_id": zero["id"], "value": 1, "memo": "대화에서 확인됨"},
            {"item_id": nothing["id"], "value": 0, "memo": "기록은 없으나 미충족으로 봄"},
            {"item_id": one["id"], "value": 1, "memo": ""},
        ],
        "memo": "전체적으로 무난함",
    }
    res = await review(body)
    assert (res.status_code, res.json()) == (200, {"status": "approving"})
    assert [k for k, _ in publisher.published].count(APPROVE) == 1

    rows = (await db.execute(select(RubricAdjustment))).scalars().all()
    assert {(r.item_id, r.auto_value, r.reviewer_value) for r in rows} == {
        (zero["id"], 0, 1),
        (nothing["id"], None, 0),
    }
    stored = (await db.execute(select(Report))).scalar_one()
    assert (stored.reviewer_met, stored.reviewer_judged, stored.review_memo) == (
        5,
        7,
        "전체적으로 무난함",
    )
    assert stored.content == content  # 승인 전 draft 본문은 불변

    # 같은 본문 재요청은 멱등, 다른 본문은 409 already_reviewed
    again = await review(body)
    assert (again.status_code, again.json()) == (200, {"status": "approving"})
    assert [k for k, _ in publisher.published].count(APPROVE) == 1
    other = await review({"adjustments": [], "memo": "다른 의견"})
    assert (other.status_code, other.json()["error"]["code"]) == (409, "already_reviewed")
    # 이미 제출된 뒤에는 본문 검증 오류보다 already_reviewed가 먼저다
    no_memo = await review({"adjustments": [{"item_id": one["id"], "value": 0, "memo": ""}]})
    assert (no_memo.status_code, no_memo.json()["error"]["code"]) == (409, "already_reviewed")

    merged = (await api.get(f"/admin/sessions/{sid}/report", headers=admin)).json()["rubric"]
    by_id = {i["id"]: i for e in merged["elements"] for i in e["items"]}
    assert (by_id[zero["id"]]["auto"], by_id[zero["id"]]["reviewer"]) == (0, 1)
    assert by_id[zero["id"]]["memo"] == "대화에서 확인됨"
    assert by_id[nothing["id"]]["reviewer"] == 0
    assert by_id[one["id"]]["reviewer"] is None and by_id[one["id"]]["memo"] is None
    assert merged["auto_total"] == {"met": 4, "judged": 6, "no_record": 2}
    assert merged["reviewer_total"] == {"met": 5, "judged": 7, "no_record": 1}
    assert merged["review"]["memo"] == "전체적으로 무난함"
    assert {h["item_id"] for h in merged["history"]} == {zero["id"], nothing["id"]}
    coop = next(e for e in merged["elements"] if e["element"] == "cooperation")
    assert coop["reviewer"] == {"met": 3, "judged": 4, "no_record": 0}


async def test_candidate_list_shows_totals_and_source(
    api, internal, db, service, admin, new_position, invite
):
    position = await new_position()
    created = await invite(position["id"])
    sid, content = await to_report_ready(api, internal, db, service, position, created)

    url = f"/admin/positions/{position['id']}/candidates"
    row = (await api.get(url, headers=admin)).json()[0]
    assert (row["status"], row["display_status"]) == ("report_ready", "report_ready")
    assert row["report_ready_at"]
    assert row["score"]["source"] == "auto"
    assert {k: row["score"][k] for k in ("met", "judged", "no_record")} == {
        "met": 4,
        "judged": 6,
        "no_record": 2,
    }
    assert [e["element"] for e in row["score"]["by_element"]] == ["cooperation", "responsibility"]
    assert row["score"]["by_element"][0] == {"element": "cooperation", "met": 2, "judged": 3}

    zero = next(
        i["id"] for e in content["rubric"]["elements"] for i in e["items"] if i["auto"] == 0
    )
    res = await api.post(
        f"/admin/sessions/{sid}/review",
        json={"adjustments": [{"item_id": zero, "value": 1, "memo": "정정"}]},
        headers=admin,
    )
    assert res.status_code == 200
    row = (await api.get(url, headers=admin)).json()[0]
    assert (row["display_status"], row["score"]["source"]) == ("approving", "reviewer")
    assert (row["score"]["met"], row["score"]["judged"]) == (5, 6)


async def test_review_requires_a_ready_report(api, admin, new_position, invite):
    position = await new_position()
    created = await invite(position["id"])
    res = await api.post(
        f"/admin/sessions/{created['session_id']}/review", json={"adjustments": []}, headers=admin
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "conflict"
