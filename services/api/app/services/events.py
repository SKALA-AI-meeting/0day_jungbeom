"""카드(이벤트) 실행 한 번. 스케줄러와 제출 처리(보고 요청 즉시 실행)가 함께 쓴다.

호출자가 세션 Lock을 잡고 부른다. 같은 run_id로 묶인 fired 행을 카드 순서로 한 번 실행하고, 행마다
자기 event_id 메시지가 있으면 done, 아니면 attempts를 세서 3회째에 failed(+세션 fail)로 둔다. 러너가
문서 전송 실패(RunResult.error가 DOCUMENT_MISSING으로 시작)를 알리면 문서를 보내는 카드 행에
document_missing=true를 남긴다(그 문서에 의존하는 항목은 리포트에서 사유 document_missing).
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.agent.runner import DOCUMENT_MISSING, Stimulus
from app.models import AgentRun, Invite, Message, Position, Session, SessionEvent
from app.services.runs import run_agent

if TYPE_CHECKING:
    from app.services.session import SessionService

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # 카드 실행은 최초 포함 총 3회


async def _scenario_cards(service: "SessionService", session_id: uuid.UUID) -> dict[str, dict]:
    scenario = await service.db.scalar(
        select(Position.scenario)
        .join(Invite, Invite.position_id == Position.id)
        .join(Session, Session.invite_id == Invite.id)
        .where(Session.id == session_id)
    )
    return {card["card_id"]: {**card, "_order": i} for i, card in enumerate(scenario["cards"])}


async def attempt(service: "SessionService", run_id: uuid.UUID) -> bool:
    """한 번 실행한다. 더 할 일이 없으면(모두 done·failed·skipped이거나 세션이 끝남) True."""
    db = service.db
    rows = list(
        (
            await db.execute(
                select(SessionEvent)
                .where(SessionEvent.run_id == run_id)
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )
    if not rows:
        return True
    session_id = rows[0].session_id
    session = await db.get(Session, session_id, populate_existing=True)
    if session.status != "in_progress":
        return True
    cards = await _scenario_cards(service, session_id)
    rows.sort(key=lambda e: cards.get(e.card_id, {}).get("_order", len(cards)))
    pending = [e for e in rows if e.status == "fired"]
    if not pending:
        return True
    for event in pending:
        event.attempts += 1
    # 러너의 seq 슬롯이 카드 순번을 따르므로 재실행에도 묶음 전체를 같은 순서로 넘긴다
    stimulus = Stimulus("event", event_ids=tuple(e.id for e in rows))
    await _restart_run(db, session_id, stimulus, run_id)
    await db.commit()

    error = None
    try:
        result = await run_agent(
            db, service.runner, service.locks, session_id, stimulus, run_id, lock_held=True
        )
        ok, error = result.ok, result.error
    except Exception:
        log.exception("event run %s failed", run_id)
        ok = False

    posted = set(
        (
            await db.execute(
                select(Message.event_id)
                .where(
                    Message.session_id == session_id,
                    Message.event_id.in_([e.id for e in pending]),
                )
                .distinct()
            )
        ).scalars()
    )
    now = datetime.now(UTC)
    missing = bool(error and error.startswith(DOCUMENT_MISSING))
    failed_cards = []
    for event in pending:
        if missing and cards.get(event.card_id, {}).get("sends_document"):
            event.document_missing = True
        if ok and event.id in posted:
            event.status, event.done_at = "done", now
            # 재시도에서 문서를 결국 보냈으면 앞선 실패 표시를 지운다(C5 "3회째 성공하면 정상")
            event.document_missing = False
        elif event.attempts >= MAX_ATTEMPTS:
            # 결 메시지(texture)는 세션을 실패시키지 않는다
            event.status = "skipped" if event.texture else "failed"
            if not event.texture:
                failed_cards.append(event.card_id)
    if failed_cards:
        # 카드 failed와 세션 fail을 한 트랜잭션으로(fail()이 조회 전 자동 flush 후 커밋한다)
        await service.fail(session_id, "session", f"card_failed:{','.join(failed_cards)}")
    else:
        await db.commit()
    return all(e.status != "fired" for e in pending)


async def _restart_run(db, session_id: uuid.UUID, stimulus: Stimulus, run_id: uuid.UUID) -> None:
    """agent_runs를 started로 되돌린다(재실행이면 시각도 새로). 커밋은 호출자가 한다."""
    stmt = insert(AgentRun).values(
        run_id=run_id, session_id=session_id, stimulus=stimulus.type, ref_ids=stimulus.ref_ids
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["run_id"],
            set_={"status": "started", "started_at": func.now(), "finished_at": None},
        )
    )
