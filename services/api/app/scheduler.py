"""5초 루프 스케줄러(docs/api/design.md "스케줄러").

run.py가 같은 asyncio 루프에서 run(ctx)를 띄운다.

tick 한 번이 차례로 본다:
  releases  진행·보고 대기 세션의 지연 공개(release_at 도래, released_at 없음) → 공개와 "공개됨" 줄.
            시작 공개분은 start()가 이미 기록한다
  events    제출 전 세션마다 미완료 카드(fired)와 due된 pending 중 due_at이 가장 이른 묶음 하나만.
            pending이면 같은 due_at 행을 카드 순서로 묶어 run_id 하나 → fired 커밋 → 실행.
            fired면 이 프로세스에서 돌고 있으면 기다리고, 아니면(재시작) 60초 지나 같은 run_id로
            재실행. 앞 묶음이 done·failed·skipped가 되기 전에는 뒤 묶음을 띄우지 않는다
  retry     failed 필수 카드가 남은 진행 중 세션 → fail(session)
  runs      메시지·division agent_runs가 120초 넘게 started → 같은 run_id로 재실행
  endings   in_progress: ends_at 도달 또는 submitted_at만 남은 세션(재시작) → submit()
            reporting: reported_at 있음 또는 deadline_at 도달 → complete()
  outbox    60초마다 미발행 세션 재발행(queue.republish_pending)

fired 기록은 tick 안에서 바로 커밋한다(±10초 목표는 이 시각). 실행(카드·메시지·제출·종료)은 세션
Lock을 기다리므로 백그라운드 작업으로 띄우고, 같은 키(run_id, 종료는 ("end", session_id))는 한 번에
하나만 돈다. WS의 메시지 실행과 보드 확정의 division 실행도 spawn으로 띄운다.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Hashable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import Stimulus
from app.models import AgentRun, DocumentRelease, Invite, Position, Session, SessionEvent
from app.queue import republish_pending
from app.services import events as event_runs
from app.services import releases
from app.services.context import AppContext
from app.services.runs import LLM_FAILURE_LIMIT, llm_failures_exceeded, run_agent

log = logging.getLogger(__name__)

INTERVAL = 5.0
RETRY_AFTER = timedelta(seconds=60)
STALE_RUN = timedelta(seconds=120)
OUTBOX_EVERY = timedelta(seconds=60)
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
            await self._retry(db)
            await self._stale_runs(db, now)
            await self._endings(db, now)
            if self._outbox_at is None or now - self._outbox_at >= OUTBOX_EVERY:
                self._outbox_at = now
                await republish_pending(db, self.ctx.publisher)

    async def _releases(self, db: AsyncSession, now: datetime) -> None:
        rows = (
            await db.execute(
                select(DocumentRelease.session_id, DocumentRelease.doc_id, Position.scenario)
                .join(Session, Session.id == DocumentRelease.session_id)
                .join(Invite, Invite.id == Session.invite_id)
                .join(Position, Position.id == Invite.position_id)
                .where(
                    DocumentRelease.release_at <= now,
                    DocumentRelease.released_at.is_(None),
                    Session.status.in_(("in_progress", "reporting")),
                )
            )
        ).all()
        for session_id, doc_id, scenario in rows:
            await releases.release(db, self.ctx.hub, session_id, scenario, doc_id, now)

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

    async def _retry(self, db: AsyncSession) -> None:
        """필수 카드가 failed이거나 일반 응답 LLM 실패가 연속 3회인데 세션이 아직 진행 중이면 실패로
        수렴시킨다(실행 직후 전이 전에 죽은 경우)."""
        stuck = (
            await db.execute(
                select(Session.id).where(
                    Session.llm_failures >= LLM_FAILURE_LIMIT,
                    Session.status.in_(("in_progress", "reporting")),
                )
            )
        ).scalars()
        for session_id in list(stuck):
            await self.ctx.session_service(db).fail(session_id, "session", "llm_failures")
        rows = (
            await db.execute(
                select(SessionEvent.session_id, SessionEvent.card_id)
                .join(Session, Session.id == SessionEvent.session_id)
                .where(
                    SessionEvent.status == "failed",
                    SessionEvent.texture.is_(False),
                    Session.status.in_(("in_progress", "reporting")),
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
        """멈춘 메시지·division 실행만. 카드 실행 복구는 _events가 세션별 순서를 지키며 한다."""
        runs = (
            (
                await db.execute(
                    select(AgentRun)
                    .join(Session, Session.id == AgentRun.session_id)
                    .where(
                        AgentRun.status == "started",
                        AgentRun.stimulus.in_(("message", "division")),
                        AgentRun.started_at < now - STALE_RUN,
                        Session.status.in_(("in_progress", "reporting")),
                    )
                )
            )
            .scalars()
            .all()
        )
        for run in runs:
            if run.stimulus == "message":
                stimulus = Stimulus("message", message_id=run.ref_ids[0])
            else:
                stimulus = Stimulus("division", task_event_ids=tuple(run.ref_ids))
            spawn(run.run_id, partial(run_stimulus, self.ctx, run.session_id, stimulus, run.run_id))

    async def _endings(self, db: AsyncSession, now: datetime) -> None:
        rows = (
            await db.execute(
                select(Session).where(
                    or_(
                        and_(
                            Session.status == "in_progress",
                            or_(Session.ends_at <= now, Session.submitted_at.is_not(None)),
                        ),
                        and_(
                            Session.status == "reporting",
                            or_(Session.reported_at.is_not(None), Session.deadline_at <= now),
                        ),
                    )
                )
            )
        ).scalars()
        for session in rows:
            if session.status == "in_progress":
                reason = "timeout" if session.submitted_at is None else ended_reason(session)
                spawn(("submit", session.id), partial(submit, self.ctx, session.id, reason))
            else:
                job = partial(complete, self.ctx, session.id, ended_reason(session))
                spawn(("end", session.id), job)


def ended_reason(session: Session) -> str:
    """session.ended의 reason. 만료 자동 제출(submitted_at이 ends_at 이후)이면 timeout."""
    if session.submitted_at is not None and session.submitted_at < session.ends_at:
        return "submitted"
    return "timeout"


async def submit(ctx: AppContext, session_id: uuid.UUID, reason: str) -> None:
    """Lock 밖에서 부른다. submit()이 세션 Lock을 잡고 진행 중 실행이 끝나기를 기다린다."""
    async with ctx.session_factory() as db:
        await ctx.session_service(db).submit(session_id, reason)


async def complete(ctx: AppContext, session_id: uuid.UUID, reason: str) -> None:
    """Lock 밖에서 부른다. complete()가 세션 Lock을 잡고 진행 중 실행이 끝나기를 기다린다."""
    async with ctx.session_factory() as db:
        await ctx.session_service(db).complete(session_id, reason)


async def run_message(
    ctx: AppContext, session_id: uuid.UUID, message_id: uuid.UUID, run_id: uuid.UUID
) -> None:
    """지원자 메시지 실행. agent_runs started는 accept_candidate_message가 이미 커밋했다."""
    await run_stimulus(ctx, session_id, Stimulus("message", message_id=message_id), run_id)


async def run_stimulus(
    ctx: AppContext, session_id: uuid.UUID, stimulus: Stimulus, run_id: uuid.UUID
) -> None:
    """메시지·division 자극 실행. agent_runs started는 호출 전에 커밋돼 있다."""
    async with ctx.session_factory() as db:
        await run_agent(db, ctx.runner, ctx.locks, session_id, stimulus, run_id)
        if await llm_failures_exceeded(db, session_id):
            await ctx.session_service(db).fail(session_id, "session", "llm_failures")


async def run_events(ctx: AppContext, session_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """같은 run_id로 묶인 카드 실행. 실패하면 같은 run_id로 다시(최초 포함 3회)."""
    for attempt in range(event_runs.MAX_ATTEMPTS):
        if attempt:
            await asyncio.sleep(RETRY_DELAY)
        async with ctx.session_factory() as db, ctx.locks(session_id):
            if await event_runs.attempt(ctx.session_service(db), run_id):
                return
