"""5초 루프 스케줄러(docs/api/design.md "스케줄러").

run.py가 같은 asyncio 루프에서 run(ctx)를 띄운다.

tick 한 번이 차례로 본다(진행 중인 세션만):
  releases  release_at<=now, released_at 없음 → 기록 → document.released
            (시작 공개분은 start()가 이미 기록한다)
  events    세션별로 미완료 카드(fired)와 due된 pending 중 due_at이 가장 이른 묶음 하나만 본다.
            pending이면 같은 due_at 행을 카드 순서로 묶어 run_id 하나 → fired 커밋 → 실행.
            fired면 이 프로세스에서 돌고 있으면 기다리고, 아니면(재시작) fired_at<now-60s일 때 같은
            run_id로 재실행. 앞 묶음이 done·failed·skipped가 되기 전에는 뒤 묶음을 띄우지 않는다
  retry     failed 필수 카드가 남은 진행 중 세션 → fail(session)
            (카드 failed와 세션 fail 사이에 죽은 경우의 복구)
  runs      메시지 agent_runs started, started_at<now-120s → 같은 run_id로 재실행
  timeouts  ends_at<=now, submitted_at 없음 → complete("timeout")
  ending    submitted_at 있음 → complete() 재실행(종료 run_id 고정, 멱등)
  outbox    60초마다 미발행 세션 재발행(queue.republish_pending)

fired 기록은 tick 안에서 바로 커밋한다(±10초 목표는 이 시각). 실행(카드·메시지·종료)은 세션 Lock을
기다리므로 백그라운드 작업으로 띄우고, 같은 키(run_id, 종료는 ("end", session_id))는 한 번에 하나만
돈다. WS의 메시지 실행도 spawn으로 띄워 runs 단계가 진행 중인 실행을 겹쳐 돌리지 않게 한다.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Hashable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import Stimulus
from app.models import AgentRun, DocumentRelease, Invite, Message, Position, Session, SessionEvent
from app.queue import republish_pending
from app.services.context import AppContext
from app.services.runs import run_agent

log = logging.getLogger(__name__)

INTERVAL = 5.0
RETRY_AFTER = timedelta(seconds=60)
STALE_RUN = timedelta(seconds=120)
OUTBOX_EVERY = timedelta(seconds=60)
MAX_ATTEMPTS = 3  # 카드 실행은 최초 포함 총 3회
RETRY_DELAY = 2.0

_LIVE = (Session.status == "in_progress", Session.submitted_at.is_(None))

_inflight: set[Hashable] = set()
_tasks: set[asyncio.Task] = set()


def spawn(key: Hashable, job: Callable[[], Awaitable[Any]]) -> bool:
    """같은 키가 돌고 있으면 띄우지 않는다. 예외는 로그로만 남기고 다음 tick이 다시 집는다."""
    if key in _inflight:
        return False
    _inflight.add(key)

    async def wrapper() -> None:
        try:
            await job()
        except Exception:
            log.exception("scheduled job %s failed", key)
        finally:
            _inflight.discard(key)

    task = asyncio.create_task(wrapper())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


async def drain() -> None:
    """현재 루프에서 띄운 작업이 모두 끝날 때까지 기다린다(테스트·종료용)."""
    loop = asyncio.get_running_loop()
    while pending := [t for t in _tasks if t.get_loop() is loop and not t.done()]:
        await asyncio.gather(*pending, return_exceptions=True)


async def run(ctx: AppContext) -> None:
    scheduler = Scheduler(ctx)
    while True:
        try:
            await scheduler.tick()
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(INTERVAL)


class Scheduler:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._outbox_at: datetime | None = None

    async def tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        async with self.ctx.session_factory() as db:
            await self._releases(db, now)
            await self._events(db, now)
            await self._retry(db, now)
            await self._stale_runs(db, now)
            await self._endings(db, now)
            if self._outbox_at is None or now - self._outbox_at >= OUTBOX_EVERY:
                self._outbox_at = now
                await republish_pending(db, self.ctx.publisher)

    async def _releases(self, db: AsyncSession, now: datetime) -> None:
        rows = (
            await db.execute(
                select(DocumentRelease, Position.scenario)
                .join(Session, Session.id == DocumentRelease.session_id)
                .join(Invite, Invite.id == Session.invite_id)
                .join(Position, Position.id == Invite.position_id)
                .where(
                    DocumentRelease.release_at <= now,
                    DocumentRelease.released_at.is_(None),
                    Session.status == "in_progress",
                )
            )
        ).all()
        if not rows:
            return
        for release, _ in rows:
            release.released_at = now
        await db.commit()
        for release, scenario in rows:
            title = next(d["title"] for d in scenario["documents"] if d["doc_id"] == release.doc_id)
            payload = {"doc_id": release.doc_id, "title": title}
            await self.ctx.hub.broadcast(release.session_id, "document.released", payload)

    async def _events(self, db: AsyncSession, now: datetime) -> None:
        rows = (
            (
                await db.execute(
                    select(SessionEvent)
                    .join(Session, Session.id == SessionEvent.session_id)
                    .where(
                        or_(
                            SessionEvent.status == "fired",
                            and_(SessionEvent.status == "pending", SessionEvent.due_at <= now),
                        ),
                        *_LIVE,
                    )
                    .order_by(SessionEvent.session_id, SessionEvent.due_at)
                )
            )
            .scalars()
            .all()
        )
        # 세션별 맨 앞 묶음(가장 이른 due_at)만. 상태를 가진 그래프가 카드 순서를 뒤집지 않게 한다
        heads: dict[uuid.UUID, list[SessionEvent]] = {}
        for event in rows:
            head = heads.setdefault(event.session_id, [event])
            if head[0] is not event and head[0].due_at == event.due_at:
                head.append(event)
        fired: list[tuple[uuid.UUID, uuid.UUID]] = []
        for session_id, head in heads.items():
            started = next((e for e in head if e.status == "fired"), None)
            if started is not None:
                stale = started.fired_at < now - RETRY_AFTER
                if started.run_id not in _inflight and stale:
                    spawn(started.run_id, partial(run_events, self.ctx, session_id, started.run_id))
                continue
            run_id = uuid.uuid4()
            for event in head:
                event.status, event.fired_at, event.run_id = "fired", now, run_id
            fired.append((session_id, run_id))
        if not fired:
            return
        await db.commit()
        for session_id, run_id in fired:
            spawn(run_id, partial(run_events, self.ctx, session_id, run_id))

    async def _retry(self, db: AsyncSession, now: datetime) -> None:
        """필수 카드가 failed인데 세션이 아직 진행 중이면 실패로 수렴시킨다."""
        rows = (
            await db.execute(
                select(SessionEvent.session_id, SessionEvent.card_id)
                .join(Session, Session.id == SessionEvent.session_id)
                .where(
                    SessionEvent.status == "failed",
                    SessionEvent.texture.is_(False),
                    Session.status == "in_progress",
                )
                .order_by(SessionEvent.session_id, SessionEvent.due_at)
            )
        ).all()
        failed: defaultdict[uuid.UUID, list[str]] = defaultdict(list)
        for session_id, card_id in rows:
            failed[session_id].append(card_id)
        for session_id, cards in failed.items():
            await self.ctx.session_service(db).fail(
                session_id, "session", f"card_failed:{','.join(cards)}"
            )

    async def _stale_runs(self, db: AsyncSession, now: datetime) -> None:
        """멈춘 메시지 실행만. 카드 실행 복구는 _events가 세션별 순서를 지키며 한다."""
        runs = (
            (
                await db.execute(
                    select(AgentRun)
                    .join(Session, Session.id == AgentRun.session_id)
                    .where(
                        AgentRun.status == "started",
                        AgentRun.stimulus == "message",
                        AgentRun.started_at < now - STALE_RUN,
                        *_LIVE,
                    )
                )
            )
            .scalars()
            .all()
        )
        for run in runs:
            job = partial(run_message, self.ctx, run.session_id, run.ref_ids[0], run.run_id)
            spawn(run.run_id, job)

    async def _endings(self, db: AsyncSession, now: datetime) -> None:
        rows = (
            await db.execute(
                select(Session.id, Session.ends_at, Session.submitted_at).where(
                    Session.status == "in_progress",
                    or_(Session.ends_at <= now, Session.submitted_at.is_not(None)),
                )
            )
        ).all()
        for session_id, ends_at, submitted_at in rows:
            reason = "submitted" if submitted_at and submitted_at < ends_at else "timeout"
            spawn(("end", session_id), partial(complete, self.ctx, session_id, reason))


async def complete(ctx: AppContext, session_id: uuid.UUID, reason: str) -> None:
    """Lock 밖에서 부른다. complete()가 세션 Lock을 잡고 진행 중 실행이 끝나기를 기다린다."""
    async with ctx.session_factory() as db:
        await ctx.session_service(db).complete(session_id, reason)


async def run_message(
    ctx: AppContext, session_id: uuid.UUID, message_id: uuid.UUID, run_id: uuid.UUID
) -> None:
    """지원자 메시지 실행. agent_runs started는 accept_candidate_message가 이미 커밋했다."""
    async with ctx.session_factory() as db:
        stimulus = Stimulus("message", message_id=message_id)
        await run_agent(db, ctx.runner, ctx.locks, session_id, stimulus, run_id)


async def run_events(ctx: AppContext, session_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """같은 run_id로 묶인 카드 실행. 실패하면 같은 run_id로 다시(최초 포함 3회)."""
    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            await asyncio.sleep(RETRY_DELAY)
        async with ctx.session_factory() as db, ctx.locks(session_id):
            if await _attempt_events(ctx, db, session_id, run_id):
                return


async def _card_order(db: AsyncSession, session_id: uuid.UUID) -> dict[str, int]:
    scenario = await db.scalar(
        select(Position.scenario)
        .join(Invite, Invite.position_id == Position.id)
        .join(Session, Session.invite_id == Invite.id)
        .where(Session.id == session_id)
    )
    return {card["card_id"]: index for index, card in enumerate(scenario["cards"])}


async def _attempt_events(
    ctx: AppContext, db: AsyncSession, session_id: uuid.UUID, run_id: uuid.UUID
) -> bool:
    """세션 Lock 안에서 한 번 실행한다. 더 할 일이 없으면 True."""
    session = await db.get(Session, session_id)
    if session.status != "in_progress" or session.submitted_at is not None:
        return True
    order = await _card_order(db, session_id)
    events = sorted(
        (
            await db.execute(
                select(SessionEvent).where(
                    SessionEvent.session_id == session_id, SessionEvent.run_id == run_id
                )
            )
        )
        .scalars()
        .all(),
        key=lambda e: order.get(e.card_id, len(order)),
    )
    pending = [e for e in events if e.status == "fired"]
    if not pending:
        return True
    for event in pending:
        event.attempts += 1
    # 러너의 seq 슬롯이 카드 순번을 따르므로 재실행에도 묶음 전체를 같은 순서로 넘긴다
    stimulus = Stimulus("event", event_ids=tuple(e.id for e in events))
    await _restart_run(db, session_id, stimulus, run_id)
    await db.commit()

    try:
        result = await run_agent(
            db, ctx.runner, ctx.locks, session_id, stimulus, run_id, lock_held=True
        )
        ok = result.ok
    except Exception:
        log.exception("event run %s failed", run_id)
        ok = False

    # 행마다 자기 event_id를 단 메시지가 있어야 done(러너가 카드 발생을 감지하는 기준과 같다)
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
    failed_cards = []
    for event in pending:
        if ok and event.id in posted:
            event.status, event.done_at = "done", now
        elif event.attempts >= MAX_ATTEMPTS:
            # 결 메시지(texture)는 세션을 실패시키지 않는다
            event.status = "skipped" if event.texture else "failed"
            if not event.texture:
                failed_cards.append(event.card_id)
    if failed_cards:
        # 카드 failed와 세션 fail을 한 트랜잭션으로(fail()이 조회 전 자동 flush 후 커밋한다)
        reason = f"card_failed:{','.join(failed_cards)}"
        await ctx.session_service(db).fail(session_id, "session", reason)
    else:
        await db.commit()
    return all(e.status != "fired" for e in pending)


async def _restart_run(
    db: AsyncSession, session_id: uuid.UUID, stimulus: Stimulus, run_id: uuid.UUID
) -> None:
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
