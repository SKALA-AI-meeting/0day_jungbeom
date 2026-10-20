"""완료 기준(api-candidate): 지원자 엔드포인트가 계약 픽스처와 같은 형태, 문서 보내기→문서 카드
메시지·버전 1 증가, 자동 저장마다 document_revisions 1행, 공유 안 된 버전 열기 404, 최종본
가져오기 출처 기록(덮어쓰기), 보드만으로 분업 확정(최소 테스트 ①), 카드 전 계획의 보드 이력(②),
reporting 재접속(⑥ REST 쪽).
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import DocumentRevision, DocView, Message, Session, SessionEvent, TaskEvent
from app.queue import GENERATE
from sqlalchemy import func, select, update

from tests.conftest import FakeSocket
from tests.contract import assert_contract
from tests.routers.support import bearer


async def enter(api, new_position, invite, elements=None):
    """채용 건·초대 → 입장·동의·시작. (position, session_id, token, auth)."""
    position = await new_position(elements) if elements else await new_position()
    row = await invite(position["id"])
    token = row["invite_url"].rsplit("/", 1)[-1]
    entry = (await api.get(f"/s/{token}")).json()
    assert_contract(entry, "candidate_entry")
    consent = (await api.post(f"/s/{token}/consent")).json()
    assert_contract(consent, "candidate_session_token")
    auth = bearer(consent["session_token"])
    started = (await api.post(f"/s/{token}/start", headers=auth)).json()
    assert_contract(started, "candidate_start")
    return position, uuid.UUID(row["session_id"]), token, auth


async def assign(api, sid, auth, parts: dict[int, str]):
    out = None
    for part_no, assignee in parts.items():
        out = await api.put(
            f"/sessions/{sid}/tasks/{part_no}", json={"assignee": assignee}, headers=auth
        )
    return out


DEFAULT = {1: "candidate", 2: "candidate", 3: "both", 4: "colleague", 5: "colleague"}


async def test_candidate_rest_follows_contract(
    api, internal, db, ctx, new_position, invite, publisher
):
    position, sid, token, auth = await enter(api, new_position, invite)
    state = (await api.get(f"/sessions/{sid}/state", headers=auth)).json()
    assert_contract(state, "state_start")
    assert state["session"]["alias"] == "지원자A" and len(state["messages"]) == 0
    assert state["division"] is None and [t["assignee"] for t in state["tasks"]] == [None] * 5
    assert state["persona"] == {
        "manager": "한서윤 팀장",
        "colleague": "이도현",
        "candidate_role": "주담당",
    }

    docs = (await api.get(f"/sessions/{sid}/documents", headers=auth)).json()
    assert_contract(docs, "documents")
    delayed = {d["doc_id"]: d for d in docs}["interview_summary"]
    assert (delayed["released"], delayed["release_at_min"]) == (False, 70)
    locked = await api.get(f"/sessions/{sid}/documents/interview_summary", headers=auth)
    assert (locked.status_code, locked.json()["error"]["code"]) == (423, "not_released")
    metrics = (await api.get(f"/sessions/{sid}/documents/metrics", headers=auth)).json()
    assert_contract(metrics, "document")
    assert list((await db.execute(select(DocView.doc_id))).scalars()) == ["metrics"]

    task = (await assign(api, sid, auth, DEFAULT)).json()
    assert_contract(task, "task")

    # 자동 저장마다 revision 1행, 같은 본문은 늘지 않음 → 보내기는 version과 문서 카드 메시지
    saved = (
        await api.put(f"/sessions/{sid}/my-documents/1", json={"content": "초안"}, headers=auth)
    ).json()
    assert_contract(saved, "my_document_save")
    await api.put(f"/sessions/{sid}/my-documents/1", json={"content": "초안 2"}, headers=auth)
    again = await api.put(
        f"/sessions/{sid}/my-documents/1", json={"content": "초안 2"}, headers=auth
    )
    assert again.json()["revision"] == 2
    assert await db.scalar(select(func.count()).select_from(DocumentRevision)) == 2
    shared = (
        await api.post(
            f"/sessions/{sid}/my-documents/1/share",
            json={"channel": "team", "note": "1번 초안이에요"},
            headers=auth,
        )
    ).json()
    assert_contract(shared, "my_document_share")
    assert shared["version"] == 1
    card = await db.get(Message, uuid.UUID(shared["message_id"]))
    assert (card.sender, card.content) == ("candidate", "1번 초안이에요")  # 본문은 지원자의 note뿐

    # 동료가 4번 v1을 보냄(내부 API) → 지원자가 열기, 공유 안 된 버전은 404
    sent = await internal.post(
        f"/internal/sessions/{sid}/docs/send",
        json={
            "part_no": 4,
            "content": "사례 1·2",
            "channel": "team",
            "run_id": str(uuid.uuid4()),
            "seq": 40,
        },
    )
    assert_contract(sent.json(), "internal_docs_send")
    k4 = sent.json()["doc_id"]
    opened = (
        await api.post(f"/sessions/{sid}/documents/{k4}/open", json={"version": 1}, headers=auth)
    ).json()
    assert_contract(opened, "document_open")
    missing = await api.post(
        f"/sessions/{sid}/documents/{k4}/open", json={"version": 2}, headers=auth
    )
    assert missing.status_code == 404

    # 최종본: 가져오기(덮어쓰기, 출처·edited=false) → 직접 편집(edited=true)
    imported = (
        await api.put(
            f"/sessions/{sid}/final/sections/4/import",
            json={"source_doc_id": k4, "version": 1},
            headers=auth,
        )
    ).json()
    assert_contract(imported, "final_section_import")
    assert (imported["content"], imported["source_version"], imported["edited"]) == (
        "사례 1·2",
        1,
        False,
    )
    await api.put(
        f"/sessions/{sid}/my-documents/final",
        json={"sections": [{"part_no": 4, "content": "사례 1·2 (고침)"}]},
        headers=auth,
    )
    # 보내지 않은 내 문서는 version null로 현재 저장본을 가져온다(source_version null)
    await api.put(f"/sessions/{sid}/my-documents/2", json={"content": "인터뷰 근거"}, headers=auth)
    c2 = next(
        d["doc_id"]
        for d in (await api.get(f"/sessions/{sid}/my-documents", headers=auth)).json()["documents"]
        if d["part_no"] == 2
    )
    own = await api.put(
        f"/sessions/{sid}/final/sections/2/import",
        json={"source_doc_id": c2, "version": None},
        headers=auth,
    )
    assert (own.json()["content"], own.json()["source_version"]) == ("인터뷰 근거", None)
    unsent = await api.put(
        f"/sessions/{sid}/final/sections/4/import",
        json={"source_doc_id": k4, "version": None},
        headers=auth,
    )
    assert unsent.status_code == 404  # 동료 문서는 보낸 버전만
    mine = (await api.get(f"/sessions/{sid}/my-documents", headers=auth)).json()
    assert_contract(mine, "my_documents")
    section = next(s for s in mine["final"]["sections"] if s["part_no"] == 4)
    assert (section["source_doc_id"], section["edited"]) == (k4, True)
    assert mine["received"][0]["versions"][0]["opened"] is True

    answer = (
        await api.post(f"/sessions/{sid}/assistant", json={"prompt": "재참여율은?"}, headers=auth)
    ).json()
    assert_contract(answer, "assistant_response")
    state = (await api.get(f"/sessions/{sid}/state", headers=auth)).json()
    assert_contract(state, "state")
    assert [m["shared_doc"]["version"] for m in state["messages"] if m["shared_doc"]] == [1, 1]

    # 제출 → reporting(deadline_at), 이후 문서 쓰기는 409 session_ending
    submitted = (await api.post(f"/sessions/{sid}/submit", headers=auth)).json()
    assert_contract(submitted, "submit", {"deadline_at"})
    assert submitted["status"] == "reporting"
    late = await api.put(f"/sessions/{sid}/my-documents/1", json={"content": "x"}, headers=auth)
    assert (late.status_code, late.json()["error"]["code"]) == (409, "session_ending")
    assert_contract(
        (await api.get(f"/sessions/{sid}/state", headers=auth)).json(), "state_reporting"
    )

    # 보고 종료 → 디브리핑(완료 입장 화면, 디브리핑, 설문 한 번)
    await ctx.session_service(db).complete(sid)
    assert publisher.published == [(GENERATE, {"session_id": str(sid), "attempt": 1})]
    ended = (await api.get(f"/s/{token}")).json()
    assert_contract(ended, "candidate_entry_completed")
    reader = bearer(ended["debrief_token"])
    debrief = (await api.get(f"/sessions/{sid}/debrief", headers=reader)).json()
    assert_contract(debrief, "debrief")
    assert [e["card_id"] for e in debrief["events"]] == ["honesty_report"]  # done인 요소 카드만
    body = {"answers": [{"q": "natural", "value": 4}, {"q": "fair", "value": 5}]}
    survey = (await api.post(f"/sessions/{sid}/debrief/survey", json=body, headers=reader)).json()
    assert_contract(survey, "debrief_survey")
    assert (
        await api.post(f"/sessions/{sid}/debrief/survey", json=body, headers=reader)
    ).json() == survey


async def test_board_only_division_confirms(api, db, ctx, new_position, invite, hub):
    """최소 테스트 ① 보드만으로 분업 확정: 담당 없는 5행 → PUT 5번 → division·task_events·WS·동료
    자극 저장. division_min 위반 조합(2번 colleague)의 마지막 PUT은 422 invalid_division이고
    저장하지 않는다."""
    _, sid, _, auth = await enter(api, new_position, invite)
    ws = FakeSocket()
    await hub.connect(sid, ws)

    wrong = {**DEFAULT, 2: "colleague"}
    rejected = await assign(api, sid, auth, wrong)
    assert (rejected.status_code, rejected.json()["error"]["code"]) == (422, "invalid_division")
    assert "2번 인터뷰 근거는" in rejected.json()["error"]["message"]
    board = (await api.get(f"/sessions/{sid}/state", headers=auth)).json()["tasks"]
    assert board[4]["assignee"] is None  # 위반한 마지막 PUT(5번)은 저장되지 않음
    assert "division.confirmed" not in ws.types()

    await assign(api, sid, auth, {2: "candidate", 5: "colleague"})
    session = await db.get(Session, sid, populate_existing=True)
    assert session.division["parts"] == {str(k): v for k, v in DEFAULT.items()}
    assert session.division["decided_by"] == "candidate"
    events = (
        (await db.execute(select(TaskEvent).where(TaskEvent.session_id == sid))).scalars().all()
    )
    assert sorted((e.part_no, e.by, e.field, e.new_value) for e in events) == sorted(
        [(no, "candidate", "assignee", who) for no, who in wrong.items() if no != 5]
        + [(2, "candidate", "assignee", "candidate"), (5, "candidate", "assignee", "colleague")]
    )
    confirmed = [f["payload"] for f in ws.frames if f["type"] == "division.confirmed"]
    assert len(confirmed) == 1 and confirmed[0]["decided_by"] == "candidate"
    updated = [f["payload"] for f in ws.frames if f["type"] == "task.updated"]
    assert updated[-1]["by"] == "candidate"
    from app.models import AgentRun
    from app.scheduler import drain

    await drain()
    runs = (await db.execute(select(AgentRun).where(AgentRun.session_id == sid))).scalars().all()
    division = [r for r in runs if r.stimulus == "division"]
    assert len(division) == 1 and len(division[0].ref_ids) == 1  # 확정시킨 task_event


async def test_plan_before_card_keeps_board_history(api, db, ctx, new_position, invite, admin):
    """최소 테스트 ② 카드 전 계획: 분업 카드(L/12) 전에 정한 담당·순서·언제까지와 카드 뒤 변경이
    task_events에 각자의 시각으로 남고, 확정 시각(decided_at)은 처음 확정 그대로다. 전체 기록의
    보드 변경 요약은 "n번 <필드> → <새 값>(t분)"이다."""
    _, sid, _, auth = await enter(api, new_position, invite)
    await assign(api, sid, auth, DEFAULT)
    await api.put(f"/sessions/{sid}/tasks/1", json={"order": 2, "due_min": 30}, headers=auth)
    before = await db.get(Session, sid, populate_existing=True)
    decided_at = before.division["decided_at"]
    card = await db.scalar(
        select(SessionEvent).where(
            SessionEvent.session_id == sid, SessionEvent.card_id == "planning_division"
        )
    )
    assert card.due_at - before.started_at == timedelta(minutes=10)

    # 시계를 11분 앞으로: 지금까지의 결정·세션 시작·카드 시각을 함께 당겨 분업 카드가 지난 상태
    shift = timedelta(minutes=11)
    await db.execute(
        update(TaskEvent)
        .where(TaskEvent.session_id == sid)
        .values(created_at=TaskEvent.created_at - shift)
    )
    await db.execute(
        update(SessionEvent)
        .where(SessionEvent.session_id == sid)
        .values(due_at=SessionEvent.due_at - shift)
    )
    await db.execute(
        update(Session).where(Session.id == sid).values(started_at=Session.started_at - shift)
    )
    await db.commit()
    card = await db.get(SessionEvent, card.id, populate_existing=True)

    # 카드 뒤 재배정(3번 both → colleague)은 이력에 더해지고 확정 시각은 바뀌지 않는다
    await api.put(f"/sessions/{sid}/tasks/3", json={"assignee": "colleague"}, headers=auth)
    after = await db.get(Session, sid, populate_existing=True)
    assert (
        after.division["parts"]["3"] == "colleague" and after.division["decided_at"] == decided_at
    )
    history = (
        (
            await db.execute(
                select(TaskEvent).where(TaskEvent.session_id == sid).order_by(TaskEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert [(e.part_no, e.field) for e in history][-3:] == [
        (1, "order"),
        (1, "due_min"),
        (3, "assignee"),
    ]
    before_card = [e for e in history if e.created_at < card.due_at]
    after_card = [e for e in history if e.created_at > card.due_at]
    assert len(before_card) == 7 and [(e.part_no, e.field) for e in after_card] == [(3, "assignee")]
    internal_events = (await api.get(f"/sessions/{sid}/state", headers=auth)).json()["tasks"][0]
    assert (internal_events["order"], internal_events["due_min"]) == (2, 30)
    record = (await api.get(f"/admin/sessions/{sid}/record", headers=admin)).json()
    board = [e["summary"].split("(")[0] for e in record if e["type"] == "task_event"]
    assert board[-3:] == ["1번 순서 → 2", "1번 언제까지 → 30분", "3번 담당 → 동료"]


async def test_reporting_resume_restores_state(api, db, ctx, new_position, invite):
    """최소 테스트 ⑥ reporting 재접속(REST): 제출 뒤 resume은 200·새 JWT, state에
    reporting·deadline_at, 끊긴 구간은 connection_gaps, 팀장 DM 메시지는 받는다.
    보고(kind=report)로 completed(WS 쪽은 test_candidate_ws)."""
    _, sid, token, auth = await enter(api, new_position, invite, ["honesty"])
    await api.post(f"/sessions/{sid}/submit", headers=auth)
    resumed = await api.post(f"/s/{token}/resume")
    assert resumed.status_code == 200
    fresh = bearer(resumed.json()["session_token"])
    from app.models import ConnectionGap

    now = datetime.now(UTC)
    db.add(
        ConnectionGap(
            session_id=sid, disconnected_at=now - timedelta(seconds=30), reconnected_at=now
        )
    )
    await db.commit()
    state = (await api.get(f"/sessions/{sid}/state", headers=fresh)).json()
    assert_contract(state, "state_reporting")
    assert state["session"]["status"] == "reporting" and state["session"]["deadline_at"]
    assert len(state["connection_gaps"]) == 1
