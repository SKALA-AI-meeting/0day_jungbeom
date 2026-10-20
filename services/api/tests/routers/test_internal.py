"""완료 기준: /internal 응답 형식과 멱등 저장(run_id·seq, run_id, window_start)."""

import dataclasses
import hashlib
import json
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from app.config import get_settings
from app.main import create_internal_app
from app.models import AssistantCall, AssistantReuse, Message, Report, SessionEvent
from app.services.messages import accept_candidate_message
from sqlalchemy import select, update

from tests.conftest import FakeSocket
from tests.routers.support import make_report_content, to_report_ready


@pytest.fixture
async def running(api, new_position, invite, started_session, hub):
    """in_progress 세션과 그 WS 소켓. (session_id, position, socket)"""
    position = await new_position()
    created = await invite(position["id"])
    sid = await started_session(created["session_id"])
    ws = FakeSocket()
    await hub.connect(sid, ws)
    return sid, position, ws


def url(sid, tail=""):
    return f"/internal/sessions/{sid}{tail}"


async def test_internal_routes_require_the_internal_token(ctx):
    bare = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_internal_app(ctx)), base_url="http://x"
    )
    res = await bare.get(url(uuid.uuid4()))
    assert res.status_code == 401 and res.json()["error"]["code"] == "unauthorized"
    await bare.aclose()


async def test_session_context_and_message_save_is_idempotent(internal, running, db):
    sid, position, ws = running
    ctx = (await internal.get(url(sid))).json()
    assert ctx["id"] == str(sid) and ctx["status"] == "in_progress"
    assert ctx["position"]["elements"] == ["cooperation", "responsibility"]
    assert ctx["position"]["catalog_version"] == position["catalog_version"]
    assert ctx["position"]["scenario"]["session_minutes"] == 120
    assert ctx["division"] is None and ctx["started_at"] and ctx["ends_at"]
    assert 0 <= ctx["t_min_now"] < 1 and ctx["current_element"] is None

    # 요소 카드가 실행된 뒤에는 흐름 카드(report_request)가 나와도 그 요소 창이 열려 있다
    started = datetime.fromisoformat(ctx["started_at"])
    for card_id, status, minute in (
        ("responsibility", "done", 50),
        ("report_request", "done", 110),
    ):
        await db.execute(
            update(SessionEvent)
            .where(SessionEvent.session_id == sid, SessionEvent.card_id == card_id)
            .values(status=status, due_at=started + timedelta(minutes=minute))
        )
    await db.commit()
    assert (await internal.get(url(sid))).json()["current_element"] == "responsibility"

    run_id = str(uuid.uuid4())
    body = {
        "channel": "team",
        "sender": "colleague",
        "content": "안녕하세요",
        "run_id": run_id,
        "seq": 1,
    }
    first = (await internal.post(url(sid, "/messages"), json=body)).json()
    again = (await internal.post(url(sid, "/messages"), json=body)).json()
    assert again == first
    assert (first["channel"], first["sender"], first["run_id"]) == ("team", "colleague", run_id)
    assert ws.types() == ["message.new"]  # 같은 키 재요청은 다시 브로드캐스트하지 않는다

    await internal.post(
        url(sid, "/messages"), json={**body, "seq": 2, "channel": "dm", "content": "DM"}
    )
    all_messages = (await internal.get(url(sid, "/messages"))).json()
    assert [m["content"] for m in all_messages] == ["안녕하세요", "DM"]
    dm_only = (await internal.get(url(sid, "/messages"), params={"channel": "dm"})).json()
    assert [m["content"] for m in dm_only] == ["DM"]
    limited = (await internal.get(url(sid, "/messages"), params={"limit": 1})).json()
    assert len(limited) == 1
    assert all(m["meta"] == {} or "classification" not in m["meta"] for m in all_messages)
    # 소수 분 필터: 시작 직후 1.5분 이후 메시지는 아직 없고, 0.0분 이후는 전부
    later = await internal.get(url(sid, "/messages"), params={"since_t_min": 1.5})
    assert later.status_code == 200 and later.json() == []
    from_start = await internal.get(url(sid, "/messages"), params={"since_t_min": 0.0})
    assert len(from_start.json()) == 2

    bad = await internal.post(url(sid, "/messages"), json={"channel": "team"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_input"

    missing = await internal.get(url(uuid.uuid4()))
    assert missing.status_code == 404


async def test_division_tasks_and_document_writes_are_permissioned(
    internal, running, invite, new_position, service
):
    sid, _, ws = running
    bad = {
        "parts": {
            "1": "candidate",
            "2": "colleague",
            "3": "both",
            "4": "colleague",
            "5": "colleague",
        }
    }
    res = await internal.put(url(sid, "/division"), json={**bad, "decided_by": "candidate"})
    assert res.status_code == 422  # 2번은 지원자 담당이어야 한다
    solo = {
        "parts": {"1": "candidate", "2": "candidate", "3": "both", "4": "both", "5": "candidate"}
    }
    res = await internal.put(url(sid, "/division"), json={**solo, "decided_by": "candidate"})
    assert res.status_code == 422  # 4·5 중 하나는 동료 단독이어야 한다

    good = {
        "parts": {
            "1": "candidate",
            "2": "candidate",
            "3": "both",
            "4": "colleague",
            "5": "colleague",
        },
        "decided_by": "candidate",
    }
    res = await internal.put(url(sid, "/division"), json=good)
    assert res.json()["division"]["parts"] == good["parts"]
    assert res.json()["division"]["decided_by"] == "candidate"
    board = (await internal.get(url(sid, "/board"))).json()["tasks"]
    assert {(t["part_no"], t["assignee"], t["status"]) for t in board} == {
        (1, "candidate", "todo"),
        (2, "candidate", "todo"),
        (3, "both", "todo"),
        (4, "colleague", "todo"),
        (5, "colleague", "todo"),
    }
    assert (await internal.get(url(sid))).json()["division"]["decided_by"] == "candidate"
    frames = len(ws.frames)
    same = await internal.put(url(sid, "/division"), json=good)
    assert same.json() == res.json()  # decided_at 포함 그대로
    assert len(ws.frames) == frames  # 재요청은 브로드캐스트하지 않는다

    # 동료 담당 카드만 바꾼다
    ok = await internal.put(url(sid, "/tasks/4"), json={"status": "doing"})
    assert ok.json() == {"part_no": 4, "assignee": "colleague", "status": "doing"}
    denied = await internal.put(url(sid, "/tasks/2"), json={"status": "doing"})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "forbidden"
    assert {"task.updated"} <= set(ws.types())

    run_id = str(uuid.uuid4())
    put = {"content": "사례 정리", "by": "colleague", "run_id": run_id}
    first = (await internal.put(url(sid, "/document/4"), json=put)).json()
    again = (await internal.put(url(sid, "/document/4"), json=put)).json()
    assert first["revision"] == 1 and again == first
    second = (
        await internal.put(url(sid, "/document/4"), json={**put, "run_id": str(uuid.uuid4())})
    ).json()
    assert second["revision"] == 2
    assert ws.types().count("document.part_updated") == 2
    denied = await internal.put(url(sid, "/document/2"), json=put)
    assert denied.status_code == 403

    state = (await internal.get(url(sid, "/document"))).json()
    assert state["4"]["content"] == "사례 정리" and state["4"]["updated_by"] == "colleague"
    assert (state["4"]["revision"], state["2"]["revision"]) == (2, 0)
    revisions = (await internal.get(url(sid, "/document_revisions"))).json()
    assert [(r["part_no"], r["revision"], r["by"], r["length"]) for r in revisions] == [
        (4, 1, "colleague", 5),
        (4, 2, "colleague", 5),
    ]

    # 종료 뒤: 새 쓰기는 409, 이미 저장된 run_id 재전달은 기존 결과
    await service.complete(sid)
    late = await internal.put(url(sid, "/document/4"), json={**put, "run_id": str(uuid.uuid4())})
    assert (late.status_code, late.json()["error"]["code"]) == (409, "conflict")
    assert (await internal.put(url(sid, "/document/4"), json=put)).json() == first
    assert (await internal.put(url(sid, "/tasks/4"), json={"status": "done"})).status_code == 409

    # in_progress가 아닌 세션의 분업은 409
    other = await invite((await new_position())["id"])
    res = await internal.put(url(other["session_id"], "/division"), json=good)
    assert res.status_code == 409


async def test_documents_listing_and_release_are_idempotent(internal, running):
    sid, position, ws = running
    listing = (await internal.get(url(sid, "/documents"))).json()
    assert listing["catalog_version"] == position["catalog_version"]
    released = {d["doc_id"]: d["released"] for d in listing["documents"]}
    # 시작 공개 4개는 start()가 즉시 released_at을 기록하고, interview_summary만 지연 공개다
    assert released["interview_summary"] is False and released["metrics"] is True
    assert {"doc_id", "title", "released"} == set(listing["documents"][0])

    # 지연 공개의 released_at은 스케줄러가 기록한다. 여기서는 직접 공개한다.
    first = (await internal.post(url(sid, "/releases/interview_summary"))).json()
    again = (await internal.post(url(sid, "/releases/interview_summary"))).json()
    assert first == again and first["released_at"]
    assert ws.types().count("document.released") == 1
    after = (await internal.get(url(sid, "/documents"))).json()["documents"]
    flags = {d["doc_id"]: d["released"] for d in after}
    assert flags["interview_summary"] is True and flags["metrics"] is True
    assert (await internal.post(url(sid, "/releases/nope"))).status_code == 404
    assert (await internal.get(url(sid, "/doc_views"))).json() == []


async def test_observations_are_idempotent_and_evidence_is_checked(internal, running):
    sid, _, _ = running
    msg = (
        await internal.post(
            url(sid, "/messages"),
            json={
                "channel": "team",
                "sender": "colleague",
                "content": "x",
                "run_id": str(uuid.uuid4()),
                "seq": 1,
            },
        )
    ).json()
    body = {
        "element": "cooperation",
        "window_start": "2026-10-20T01:30:00Z",
        "window_end": "2026-10-20T01:50:00Z",
        "metrics": {"response_minutes": {"value": 3, "evidence_ids": [msg["id"]]}},
        "label": "help_now",
        "evidence": [{"type": "message", "id": msg["id"]}],
        "run_id": str(uuid.uuid4()),
    }
    first = (await internal.post(url(sid, "/observations"), json=body)).json()
    again = (
        await internal.post(url(sid, "/observations"), json={**body, "label": "decline"})
    ).json()
    assert set(first) == {"id"} and again == first
    rows = (await internal.get(url(sid, "/observations"))).json()
    assert len(rows) == 1 and rows[0]["label"] == "help_now" and rows[0]["element"] == "cooperation"

    foreign = {"type": "message", "id": str(uuid.uuid4())}
    res = await internal.post(
        url(sid, "/observations"),
        json={**body, "element": "responsibility", "evidence": [foreign]},
    )
    assert res.status_code == 422
    # 종류가 맞지 않는 id도 거부한다(메시지 id를 revision으로 주장)
    res = await internal.post(
        url(sid, "/observations"),
        json={
            **body,
            "element": "responsibility",
            "evidence": [{"type": "revision", "id": msg["id"]}],
        },
    )
    assert res.status_code == 422


async def test_classification_is_saved_on_the_message(internal, running, db):
    sid, _, _ = running
    # 지원자 메시지 접수는 api-candidate 경로와 같은 서비스 함수를 쓴다
    from app.hub import Hub

    message, _, _ = await accept_candidate_message(db, Hub(), sid, "c-1", "team", "도와드릴게요")
    body = {
        "recipient": "colleague",
        "kind": "help",
        "instruction": None,
        "related_card": "cooperation",
    }
    first = (
        await internal.put(url(sid, f"/messages/{message.id}/classification"), json=body)
    ).json()
    again = (
        await internal.put(url(sid, f"/messages/{message.id}/classification"), json=body)
    ).json()
    assert first == again and first["id"] == str(message.id)
    assert first["meta"]["classification"]["related_card"] == "cooperation"
    listed = (await internal.get(url(sid, "/messages"), params={"channel": "team"})).json()
    assert listed[0]["meta"]["classification"]["kind"] == "help"
    stored = (await db.execute(select(Message).where(Message.id == message.id))).scalar_one()
    await db.refresh(stored)
    assert stored.meta["classification"]["related_card"] == "cooperation"
    missing = await internal.put(url(sid, f"/messages/{uuid.uuid4()}/classification"), json=body)
    assert missing.status_code == 404


async def test_assistant_reads_return_calls_and_reuse(internal, running, db):
    sid, _, _ = running
    request = Message(session_id=sid, channel="assistant", sender="candidate", content="질문")
    response = Message(session_id=sid, channel="assistant", sender="assistant", content="답")
    db.add_all([request, response])
    await db.flush()
    call = AssistantCall(
        session_id=sid,
        request_message_id=request.id,
        response_message_id=response.id,
        cited_doc_ids=["metrics"],
    )
    db.add(call)
    await db.flush()
    db.add(AssistantReuse(call_id=call.id, part_no=1, reuse="edited", ratio=0.5))
    await db.commit()

    calls = (await internal.get(url(sid, "/assistant_calls"))).json()
    assert [(c["id"], c["request_message_id"], c["cited_doc_ids"]) for c in calls] == [
        (str(call.id), str(request.id), ["metrics"])
    ]
    assert calls[0]["response_message_id"] == str(response.id) and calls[0]["created_at"]
    reuse = (await internal.get(url(sid, "/assistant_reuse"))).json()
    assert reuse == [{"call_id": str(call.id), "part_no": 1, "reuse": "edited", "ratio": 0.5}]


async def test_report_draft_final_follow_approval(
    api, internal, db, service, admin, new_position, invite, publisher
):
    position = await new_position()
    created = await invite(position["id"])
    sid = uuid.UUID(created["session_id"])
    # 제출 전에는 draft를 받지 않는다
    early = await internal.post(url(sid, "/report/draft"), json={"content": {}})
    assert early.status_code == 409

    sid, content = await to_report_ready(api, internal, db, service, position, created)
    stored = (await db.execute(select(Report))).scalar_one()
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert stored.content_hash == hashlib.sha256(canonical.encode()).hexdigest()
    assert (stored.stage, stored.auto_met, stored.auto_judged, stored.auto_no_record) == (
        "draft",
        4,
        6,
        2,
    )
    # 같은 draft를 다시 받아도 그대로(멱등)
    again = await internal.post(url(sid, "/report/draft"), json={"content": content})
    assert again.json() == {"status": "report_ready"}

    # 승인 전 final은 409
    res = await internal.post(url(sid, "/report/final"), json={"content": content})
    assert (res.status_code, res.json()["error"]["code"]) == (409, "conflict")

    review = await api.post(
        f"/admin/sessions/{sid}/review", json={"adjustments": []}, headers=admin
    )
    assert review.json() == {"status": "approving"}

    other = make_report_content(position["scenario"], [0])
    res = await internal.post(url(sid, "/report/final"), json={"content": other})
    assert (res.status_code, res.json()["error"]["code"]) == (409, "draft_mismatch")

    # 키 순서·공백이 달라도 정규화 해시가 같으면 승인된 draft로 본다
    shuffled = json.loads(json.dumps(content, sort_keys=True))
    final = (await internal.post(url(sid, "/report/final"), json={"content": shuffled})).json()
    assert final["status"] == "reviewed" and final["reviewed_at"]
    replay = (await internal.post(url(sid, "/report/final"), json={"content": content})).json()
    assert replay == final
    row = (await db.execute(select(Report))).scalar_one()
    await db.refresh(row)
    assert (row.stage, row.reviewed_at is not None) == ("final", True)
    report = (await api.get(f"/admin/sessions/{sid}/report", headers=admin)).json()
    assert (report["stage"], report["reviewed_at"]) == ("final", final["reviewed_at"])


async def test_report_failed_marks_the_session_failed(
    api, internal, db, service, new_position, invite
):
    position = await new_position()
    created = await invite(position["id"])
    sid = uuid.UUID(created["session_id"])
    await service.consent(sid)
    await service.start(sid)
    await service.complete(sid)
    res = await internal.post(url(sid, "/report_failed"), json={"error": "retries exhausted"})
    assert res.json() == {"status": "failed"}
    again = await internal.post(url(sid, "/report_failed"), json={"error": "retries exhausted"})
    assert again.json() == {"status": "failed"}
    row = await service.get(sid)
    assert (row.failed_stage, row.failed_reason) == ("report", "retries exhausted")


async def test_test_session_endpoint_is_gated_by_env_flag(ctx):
    body = {"elements": ["cooperation"], "session_minutes": 6, "alias": "e2e"}

    def client(enabled: bool) -> httpx.AsyncClient:
        settings = dataclasses.replace(get_settings(), enable_test_api=enabled)
        app = create_internal_app(dataclasses.replace(ctx, settings=settings))
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://x",
            headers={"X-Internal-Token": get_settings().internal_token},
        )

    off, on = client(False), client(True)
    assert (await off.post("/internal/test/sessions", json=body)).status_code == 404
    res = await on.post("/internal/test/sessions", json=body)
    internal = on
    data = res.json()
    assert res.status_code == 200 and set(data) == {"session_id", "token", "invite_url"}
    assert data["invite_url"].endswith(f"/s/{data['token']}")
    context = (await internal.get(url(data["session_id"]))).json()
    assert (
        context["status"] == "invited" and context["position"]["scenario"]["session_minutes"] == 6
    )
