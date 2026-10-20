"""완료 기준(관문 3 리뷰 B3·A5): 실제 api 세션 → 워커 collect(내부 API) → build_draft → draft 저장 →
관리자 GET report·GET record. 리포트 근거의 record_ref(message·share·open·task_event)와 AI 활용
이벤트(assistant_call)가 전체 기록의 ref와 같은 값이다. 한 호출이 여러 파트에 반영됐으면
applied_part는 반영 비율이 가장 큰 파트다.

워커 패키지는 경로로 import한다(api venv에 워커의 런타임 의존성 httpx만 있으면 된다). LLM 없음.
"""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

from app.models import AssistantCall, AssistantReuse, SessionEvent
from sqlalchemy import select

from tests.routers.test_candidate import DEFAULT, assign, enter

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "report-worker"))
from report_worker.api import InternalApi  # noqa: E402
from report_worker.report import build_draft  # noqa: E402

LLM = SimpleNamespace(model="gpt-4o-mini")


def metric(value, *ids):
    return {"value": value, "evidence_ids": [str(i) for i in ids]}


async def run_worker(ctx, internal, sid, save=True):
    """워커가 쓰는 내부 REST 클라이언트를 같은 ASGI 앱에 붙여 collect → build_draft(→ 저장)."""
    worker = InternalApi(
        "http://api-internal", ctx.settings.internal_token, transport=internal._transport
    )
    try:
        draft, usage = await build_draft(await worker.collect(str(sid)), LLM)
        if save:
            await worker.save_draft(str(sid), draft, usage)
        return draft
    finally:
        await worker.close()


async def test_report_refs_match_record(
    api, internal, db, ctx, service, admin, new_position, invite
):
    _, sid, _, auth = await enter(api, new_position, invite, ["planning", "adaptability"])
    base, ibase = f"/sessions/{sid}", f"/internal/sessions/{sid}"
    assert (await assign(api, sid, auth, DEFAULT)).status_code == 200
    await api.put(f"{base}/tasks/1", json={"due_min": 40}, headers=auth)
    await api.put(f"{base}/my-documents/1", json={"content": "초안"}, headers=auth)
    shared = await api.post(
        f"{base}/my-documents/1/share",
        json={"channel": "team", "note": "의견 주세요"},
        headers=auth,
    )
    sent = await internal.post(
        f"{ibase}/docs/send",
        json={
            "part_no": 4,
            "content": "동료 초안",
            "channel": "team",
            "run_id": str(uuid.uuid4()),
            "seq": 40,
        },
    )
    opened = await api.post(
        f"{base}/documents/{sent.json()['doc_id']}/open", json={"version": 1}, headers=auth
    )
    assert opened.status_code == 200, opened.text

    message_id = uuid.UUID(shared.json()["message_id"])
    call = AssistantCall(session_id=sid, request_message_id=message_id, cited_doc_ids=[])
    db.add(call)
    for event in (
        await db.execute(select(SessionEvent).where(SessionEvent.session_id == sid))
    ).scalars():
        if event.card_id in ("planning_division", "planning_checkin", "adaptability_change"):
            event.status, event.fired_at = "done", event.due_at
    await db.commit()

    task_events = (await internal.get(f"{ibase}/task_events")).json()
    docs = (await internal.get(f"{ibase}/docs")).json()["documents"]
    open_id = next(o["id"] for d in docs for o in d["opens"])
    share_id = next(s["id"] for d in docs if d["owner"] == "candidate" for s in d["shares"])
    for card, element, label, metrics, evidence in [
        (
            "planning_division",
            "planning",
            "assign_with_schedule",
            {
                "division_by_candidate": metric(True, task_events[0]["id"]),
                "stated_schedule": metric(True, task_events[-1]["id"]),
            },
            [{"type": "task_event", "id": task_events[0]["id"]}],
        ),
        (
            "planning_checkin",
            "planning",
            "feedback",
            {"draft_delivered": metric(True), "draft_opened": metric(True, open_id)},
            [{"type": "message", "id": str(message_id)}],
        ),
        (
            "adaptability_change",
            "adaptability",
            "apply_silently",
            {
                "document_changed_after": metric(True, share_id),
                "target_applied": metric(True, share_id),
            },
            [{"type": "share", "id": share_id}],
        ),
    ]:
        res = await internal.post(
            f"{ibase}/observations",
            json={
                "card_id": card,
                "element": element,
                "window_start": 0,
                "window_end": 120,
                "label": label,
                "metrics": metrics,
                "evidence": evidence,
                "run_id": str(uuid.uuid4()),
            },
        )
        assert res.status_code == 200, res.text
    await service.submit(sid)
    await service.complete(sid)

    await run_worker(ctx, internal, sid)
    report = (await api.get(f"/admin/sessions/{sid}/report", headers=admin)).json()
    record = (await api.get(f"/admin/sessions/{sid}/record", headers=admin)).json()
    refs = [r["ref"] for r in record]
    evidence = [e for s in report["sections"] for c in s["cards"] for e in c["evidence"]]
    linked = [e["record_ref"] for e in evidence if e["record_ref"] is not None]
    assert {"message", "share", "open", "task_event"} <= {r["type"] for r in linked}
    assert all(r in refs for r in linked), (linked, refs)

    events = report["ai_usage"]["events"]
    assert len(events) == 1
    assert [
        {"type": "assistant_call", "id": e["call_id"], "t_min": e["t_min"]} for e in events
    ] == [r for r in refs if r["type"] == "assistant_call"]


async def test_applied_part_is_highest_ratio(api, internal, db, ctx, new_position, invite):
    _, sid, _, auth = await enter(api, new_position, invite, ["planning"])
    shared = await api.post(
        f"/sessions/{sid}/my-documents/1/share", json={"channel": "team"}, headers=auth
    )
    docs = (await internal.get(f"/internal/sessions/{sid}/docs")).json()["documents"]
    mine = {d["part_no"]: d for d in docs if d["owner"] == "candidate" and not d["final"]}
    call = AssistantCall(
        session_id=sid, request_message_id=uuid.UUID(shared.json()["message_id"]), cited_doc_ids=[]
    )
    db.add(call)
    await db.flush()
    for part_no, ratio in [(1, 0.4), (2, 0.9)]:
        db.add(
            AssistantReuse(
                call_id=call.id,
                doc_id=uuid.UUID(mine[part_no]["doc_id"]),
                part_no=part_no,
                ratio=ratio,
                applied=True,
            )
        )
    await db.commit()
    draft = await run_worker(ctx, internal, sid, save=False)
    assert draft["ai_usage"]["events"][0]["applied_part"] == 2
