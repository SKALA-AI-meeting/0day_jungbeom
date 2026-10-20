"""완료 기준(api-admin 내부 쪽): 내부 엔드포인트가 계약 픽스처와 같은 형태, 권한 밖 변경 403, 분업
422, send의 event_id·seq 멱등(같은 run에서 파트 2개 → 메시지 2건·재호출에 버전 불변), 보내지 않은
지원자 문서 차단, honesty_facts 필드 전부, 관찰 PATCH 멱등(최소 테스트 ③ api 쪽), 무관한 편집의
revision 보존(④ api 쪽), 승인 전 final 409.
"""

import importlib.util
import uuid
from dataclasses import replace

from app.auth import session_token
from app.config import REPO_ROOT

from tests.contract import assert_contract, load_contract
from tests.routers.support import bearer, make_report_content

DEFAULT = {"1": "candidate", "2": "candidate", "3": "both", "4": "colleague", "5": "colleague"}


def mission_version(mission_id: str = "planning") -> str:
    spec = importlib.util.spec_from_file_location("v", REPO_ROOT / "scenarios" / "version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.catalog_version(mission_id)


async def running(api, new_position, invite, start_invited, elements=None):
    position = await new_position(elements) if elements else await new_position()
    row = await invite(position["id"])
    return position, await start_invited(row["session_id"]), row


def run() -> str:
    return str(uuid.uuid4())


async def test_session_board_and_documents_follow_contract(
    api, internal, db, ctx, new_position, invite, start_invited
):
    position, sid, _ = await running(api, new_position, invite, start_invited)
    base = f"/internal/sessions/{sid}"

    session = (await internal.get(base)).json()
    assert_contract(session, "internal_session")
    # catalog_version은 예시 값이 아니라 공용 함수로 계산한 실제 미션 해시와 같아야 한다
    assert (
        session["position"]["catalog_version"] == mission_version() == position["catalog_version"]
    )
    assert session["current_card"] is None and len(session["events"]) == 9

    posted = await internal.post(
        f"{base}/messages", json={**load_contract("internal_message_post"), "run_id": run()}
    )
    assert_contract([posted.json()], "internal_messages")
    message = posted.json()
    classified = await internal.put(
        f"{base}/messages/{message['id']}/classification",
        json=load_contract("internal_classification"),
    )
    assert classified.json()["meta"]["classification"]["kind"] == "report"
    assert_contract((await internal.get(f"{base}/messages")).json(), "internal_messages")

    # 분업: 위반 422, 확정은 보드를 채우고 task_events(by=colleague), 같은 내용 재요청은 저장값
    wrong = {**DEFAULT, "3": "candidate"}
    bad = await internal.put(
        f"{base}/division", json={"parts": wrong, "decided_by": "candidate", "run_id": run()}
    )
    assert (bad.status_code, bad.json()["error"]["code"]) == (422, "invalid_division")
    request = {**load_contract("internal_division_put"), "run_id": run()}
    division = (await internal.put(f"{base}/division", json=request)).json()
    assert_contract(division, "internal_division")
    assert (await internal.put(f"{base}/division", json=request)).json() == division
    board = (await internal.get(f"{base}/board")).json()
    assert_contract(board, "internal_board")
    assert [t["assignee"] for t in board["tasks"]] == list(DEFAULT.values())

    status_run = run()
    forbidden = await internal.put(
        f"{base}/tasks/1", json={"status": "doing", "run_id": status_run}
    )
    assert (forbidden.status_code, forbidden.json()["error"]["code"]) == (403, "forbidden")
    done = await internal.put(f"{base}/tasks/4", json={"status": "doing", "run_id": status_run})
    again = await internal.put(f"{base}/tasks/4", json={"status": "doing", "run_id": status_run})
    assert done.json() == again.json() and done.json()["status"] == "doing"
    events = (await internal.get(f"{base}/task_events")).json()
    assert_contract(events, "internal_task_events")
    assert [(e["part_no"], e["by"], e["field"]) for e in events if e["field"] == "status"] == [
        (4, "colleague", "status")
    ]

    # 동료 문서 보내기: 같은 run에서 파트 2개 → 메시지 2건(seq 파트×10), 재호출은 버전 불변, 지원자
    # 파트 403
    send_run = run()
    event_id = session["events"][3]["id"]  # planning_checkin
    first = await internal.post(
        f"{base}/docs/send",
        json={
            "part_no": 4,
            "content": "사례",
            "channel": "team",
            "run_id": send_run,
            "event_id": event_id,
            "seq": 40,
        },
    )
    second = await internal.post(
        f"{base}/docs/send",
        json={
            "part_no": 5,
            "content": "지표",
            "channel": "team",
            "run_id": send_run,
            "event_id": event_id,
            "seq": 50,
        },
    )
    replay = await internal.post(
        f"{base}/docs/send",
        json={
            "part_no": 4,
            "content": "사례",
            "channel": "team",
            "run_id": send_run,
            "event_id": event_id,
            "seq": 40,
        },
    )
    assert_contract(first.json(), "internal_docs_send")
    assert (
        replay.json() == first.json() and first.json()["message_id"] != second.json()["message_id"]
    )
    cards = [
        m
        for m in (await internal.get(f"{base}/messages")).json()
        if m["shared_doc"] and m["event_id"] == event_id
    ]
    assert len(cards) == 2
    candidate_part = await internal.post(
        f"{base}/docs/send",
        json={"part_no": 1, "content": "x", "channel": "team", "run_id": run(), "seq": 10},
    )
    assert (candidate_part.status_code, candidate_part.json()["error"]["code"]) == (
        403,
        "forbidden",
    )

    # 지원자 문서는 보낸 버전만 페르소나에게 보인다
    from app.services import documents as doc_service

    sess = await ctx.session_service(db).get(sid)
    await doc_service.save_part(db, sid, 1, "보내지 않은 초안")
    await db.commit()
    shared = (await internal.get(f"{base}/docs/shared")).json()
    assert_contract(shared, "internal_docs_shared")
    assert {d["owner"] for d in shared["documents"]} == {"colleague"}
    await doc_service.share_part(db, ctx.hub, sess, 1, "dm")
    shared = (await internal.get(f"{base}/docs/shared")).json()
    assert [d["part_no"] for d in shared["documents"] if d["owner"] == "candidate"] == [1]

    assert_contract((await internal.get(f"{base}/docs")).json(), "internal_docs")
    assert_contract(
        (await internal.get(f"{base}/document_revisions")).json(), "internal_document_revisions"
    )
    docs = (await internal.get(f"{base}/documents")).json()
    assert_contract(docs, "internal_documents")
    assert docs["catalog_version"] == mission_version()
    released = await internal.post(f"{base}/releases/interview_summary")
    assert_contract(released.json(), "internal_release")
    assert (await internal.post(f"{base}/releases/interview_summary")).json() == released.json()
    notices = [m for m in (await internal.get(f"{base}/messages?channel=notice")).json()]
    assert [m["content"] for m in notices] == ["「사용자 인터뷰 요약」이 공개됐어요"]
    facts = (await internal.get(f"{base}/honesty_facts")).json()
    assert_contract(facts, "internal_honesty_facts")
    assert facts["changed_after_adaptability"] is False and facts["empty_sections"] == [
        1,
        2,
        3,
        4,
        5,
    ]
    assert_contract((await internal.get(f"{base}/doc_views")).json(), "internal_doc_views")

    auth = bearer(session_token(sid, 120))
    await api.post(f"/sessions/{sid}/assistant", json={"prompt": "요약해줘"}, headers=auth)
    assert_contract(
        (await internal.get(f"{base}/assistant_calls")).json(), "internal_assistant_calls"
    )

    # 제출 뒤 문서 쓰기는 409, 이미 저장된 run_id 재전달은 기존 결과
    await ctx.session_service(db).submit(sid)
    late = await internal.post(
        f"{base}/docs/send",
        json={"part_no": 4, "content": "v2", "channel": "team", "run_id": run(), "seq": 40},
    )
    assert late.status_code == 409
    assert (
        await internal.post(
            f"{base}/docs/send",
            json={
                "part_no": 4,
                "content": "사례",
                "channel": "team",
                "run_id": send_run,
                "event_id": event_id,
                "seq": 40,
            },
        )
    ).json() == first.json()
    completed = (await internal.post(f"{base}/complete")).json()
    assert_contract(completed, "internal_complete")
    from app.scheduler import drain

    await drain()
    assert (await internal.get(base)).json()["status"] == "completed"
    assert_contract(
        (await internal.get(f"{base}/assistant_reuse")).json(), "internal_assistant_reuse"
    )


async def test_observations_patch_is_idempotent(
    api, internal, db, new_position, invite, start_invited
):
    """최소 테스트 ③ 창 밖 약속 이행(api 쪽): collab_help 관찰을 promise_kept=null로 저장 →
    finalize의 PATCH가 그 지표만 바꾸고(창 밖 50분 메시지 근거), 같은 run_id 재요청은 멱등."""
    _, sid, _ = await running(api, new_position, invite, start_invited)
    base = f"/internal/sessions/{sid}"
    later = await internal.post(
        f"{base}/messages",
        json={
            "channel": "team",
            "sender": "colleague",
            "content": "약속 시각",
            "run_id": run(),
            "seq": 1,
        },
    )
    body = load_contract("observation_collab_help")
    created = await internal.post(f"{base}/observations", json={**body, "run_id": run()})
    assert_contract(created.json(), "observation_created")
    assert (
        await internal.post(f"{base}/observations", json={**body, "run_id": run()})
    ).json() == created.json()

    foreign = {
        **body,
        "card_id": "planning_checkin",
        "evidence": [{"type": "message", "id": str(uuid.uuid4())}],
    }
    rejected = await internal.post(f"{base}/observations", json={**foreign, "run_id": run()})
    assert (rejected.status_code, rejected.json()["error"]["code"]) == (422, "invalid_evidence")

    finalize = run()
    patch = {
        "card_id": "collab_help",
        "window_start": body["window_start"],
        "metrics_patch": {"promise_kept": {"value": True, "evidence_ids": [later.json()["id"]]}},
        "run_id": finalize,
    }
    updated = (await internal.patch(f"{base}/observations", json=patch)).json()
    assert updated["metrics"]["promise_kept"]["value"] is True
    assert (
        updated["metrics"]["response_minutes"] == body["metrics"]["response_minutes"]
    )  # 다른 지표 그대로
    replay = {**patch, "metrics_patch": {"promise_kept": {"value": False, "evidence_ids": []}}}
    assert (await internal.patch(f"{base}/observations", json=replay)).json()["metrics"] == updated[
        "metrics"
    ]
    missing = await internal.patch(
        f"{base}/observations", json={**patch, "card_id": "honesty_report"}
    )
    assert missing.status_code == 404
    listed = (await internal.get(f"{base}/observations")).json()
    assert_contract(listed, "internal_observations")
    assert listed[0]["window_start"] == body["window_start"]


async def test_unrelated_edit_keeps_revisions(
    api, internal, db, ctx, new_position, invite, start_invited
):
    """최소 테스트 ④ 무관한 편집(api 쪽): 방향 변경 뒤 오탈자만 고친 저장도 revision으로 남고(본문
    스냅샷), target_applied=false 관찰을 document 근거와 함께 저장할 수 있다. 항목 0은 워커가
    정한다(관문 3)."""
    _, sid, _ = await running(api, new_position, invite, start_invited)
    from app.services import documents as doc_service

    await doc_service.save_part(db, sid, 1, "대상: 첫 모임 참여자")
    await doc_service.save_part(db, sid, 1, "대상: 첫 모임 참여자들")  # 오탈자만
    await db.commit()
    base = f"/internal/sessions/{sid}"
    revisions = (await internal.get(f"{base}/document_revisions")).json()
    assert [(r["revision"], r["content"]) for r in revisions] == [
        (1, "대상: 첫 모임 참여자"),
        (2, "대상: 첫 모임 참여자들"),
    ]
    observation = {
        "card_id": "adaptability_change",
        "element": "adaptability",
        "window_start": 75.0,
        "window_end": 90.0,
        "metrics": {
            "document_changed_after": {"value": True, "evidence_ids": [revisions[1]["id"]]},
            "target_applied": {"value": False, "evidence_ids": []},
        },
        "label": "refuse_or_ignore",
        "aux": {"target_applied": False, "mentions_scope": False, "related_message_ids": []},
        "evidence": [{"type": "document", "id": revisions[1]["id"]}],
        "run_id": run(),
    }
    assert (await internal.post(f"{base}/observations", json=observation)).status_code == 200
    stored = (await internal.get(f"{base}/observations")).json()[0]
    assert stored["metrics"]["target_applied"]["value"] is False
    assert stored["evidence"] == [{"type": "document", "id": revisions[1]["id"]}]


async def test_report_draft_final_follow_approval(
    api, internal, db, ctx, new_position, invite, start_invited
):
    position, sid, _ = await running(api, new_position, invite, start_invited, ["planning"])
    base = f"/internal/sessions/{sid}"
    content = make_report_content(position["scenario"], [1, 0, None, 1])
    early = await internal.post(f"{base}/report/draft", json={"content": content})
    assert early.status_code == 409  # 보고 종료 전
    await ctx.session_service(db).submit(sid)
    await ctx.session_service(db).complete(sid)
    usage = load_contract("internal_report_usage")
    draft = await internal.post(f"{base}/report/draft", json={"content": content, "usage": usage})
    assert_contract(draft.json(), "internal_report_draft")
    blocked = await internal.post(f"{base}/report/final", json={"content": content})
    assert blocked.status_code == 409  # 승인 전 final
    await ctx.session_service(db).approve(sid)
    mismatch = await internal.post(f"{base}/report/final", json={"content": {**content, "x": 1}})
    assert (mismatch.status_code, mismatch.json()["error"]["code"]) == (409, "draft_mismatch")
    final = await internal.post(f"{base}/report/final", json={"content": content})
    assert_contract(final.json(), "internal_report_final")
    assert (
        await internal.post(f"{base}/report/final", json={"content": content})
    ).json() == final.json()


async def test_report_failed_and_test_session_gate(
    api, internal, db, ctx, new_position, invite, start_invited
):
    _, sid, _ = await running(api, new_position, invite, start_invited, ["planning"])
    await ctx.session_service(db).submit(sid)
    await ctx.session_service(db).complete(sid)
    failed = await internal.post(f"/internal/sessions/{sid}/report_failed", json={"error": "dlq"})
    assert_contract(failed.json(), "internal_report_failed")
    body = {"elements": ["planning"], "session_minutes": 6}
    ctx.settings = replace(ctx.settings, enable_test_api=False)
    assert (await internal.post("/internal/test/sessions", json=body)).status_code == 404
    ctx.settings = replace(ctx.settings, enable_test_api=True)
    created = await internal.post("/internal/test/sessions", json=body)
    assert_contract(created.json(), "internal_test_session")
    unknown = await internal.post("/internal/test/sessions", json={**body, "mission_id": "dev"})
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (422, "invalid_mission")


async def test_send_is_atomic_and_retry_safe(
    api, internal, db, ctx, new_position, invite, start_invited, monkeypatch
):
    """G2-A1: 동료 보내기는 revision·version·문서 카드 메시지·share를 한 트랜잭션으로 저장한다.
    커밋 전에 끊기면 아무것도 남지 않고, 커밋 뒤(알림 중) 끊기면 같은 요청이 기존 결과를
    돌려준다.
    """
    from app.models import DocumentShare, DocumentVersion, Message
    from app.services import documents as doc_service
    from sqlalchemy import func, select

    _, sid, _ = await running(api, new_position, invite, start_invited)
    base = f"/internal/sessions/{sid}"
    await internal.put(
        f"{base}/division", json={"parts": DEFAULT, "decided_by": "candidate", "run_id": run()}
    )
    body = {"part_no": 4, "content": "사례", "channel": "team", "run_id": run(), "seq": 40}

    async def counts():
        rows = []
        for table in (DocumentVersion, DocumentShare):
            rows.append(await db.scalar(select(func.count()).select_from(table)))
        rows.append(
            await db.scalar(
                select(func.count()).select_from(Message).where(Message.run_id == body["run_id"])
            )
        )
        return rows

    class Boom(Exception):
        pass

    original = doc_service.DocumentShare

    def broken_share(**kwargs):
        raise Boom

    monkeypatch.setattr(doc_service, "DocumentShare", broken_share)
    try:
        await internal.post(f"{base}/docs/send", json=body)
    except Boom:
        pass
    assert await counts() == [0, 0, 0]  # 커밋 전 중단: 아무것도 남지 않음
    monkeypatch.setattr(doc_service, "DocumentShare", original)

    calls = {"n": 0}
    real = ctx.hub.broadcast

    async def flaky(session_id, kind, payload):
        if kind == "document.shared" and calls["n"] == 0:
            calls["n"] += 1
            raise Boom
        await real(session_id, kind, payload)

    monkeypatch.setattr(ctx.hub, "broadcast", flaky)
    try:
        await internal.post(f"{base}/docs/send", json=body)
    except Boom:
        pass
    retried = await internal.post(f"{base}/docs/send", json=body)
    assert retried.status_code == 200 and retried.json()["version"] == 1
    assert await counts() == [1, 1, 1]  # 커밋 뒤 중단: 재시도는 기존 결과, 각 1건
