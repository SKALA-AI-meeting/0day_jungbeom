"""agent_runs 기록과 실행 래퍼. 실행은 세션 Lock 안에서 하고 started → finished/failed를 남긴다.

호출 규칙(세션 Lock은 asyncio.Lock이라 재진입되지 않는다):
- 보통은 `run_agent(...)`를 그대로 부른다. 이 함수가 locks(session_id)를 잡는다.
- 호출자가 이미 `async with locks(session_id):` 안이면 `lock_held=True`로 부른다.
  같은 Lock을 다시 잡으면 교착되므로 이 경우 Lock 없이 실행만 한다.
  (SessionService.complete가 이렇게 쓴다.)
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import AgentRunner, RunResult, Stimulus
from app.models import AgentRun, Session
from app.services.locks import SessionLocks


async def start_run(
    db: AsyncSession, session_id: uuid.UUID, stimulus: Stimulus, run_id: uuid.UUID
) -> None:
    """started 행을 만든다(이미 있으면 그대로, 같은 run_id 재실행). 호출자가 커밋한다."""
    stmt = insert(AgentRun).values(
        run_id=run_id, session_id=session_id, stimulus=stimulus.type, ref_ids=stimulus.ref_ids
    )
    await db.execute(stmt.on_conflict_do_nothing(index_elements=["run_id"]))


LLM_FAILURE_LIMIT = 3  # 일반 응답 LLM 실패 연속 3회 → 세션 failed(harness.md Recovery)


async def finish_run(
    db: AsyncSession,
    run_id: uuid.UUID,
    result: RunResult | None,
    session_id: uuid.UUID | None = None,
    stimulus: Stimulus | None = None,
) -> None:
    """agent_runs 종료 기록. 메시지 실행이면 같은 트랜잭션에서 세션 llm_failures를 갱신한다:
    응답이 LLM 실패 폴백이면 +1, 정상 응답이면 0(예외로 끝난 실행은 세지 않음)."""
    ok = result is not None and result.ok
    if session_id is not None and stimulus is not None and stimulus.type == "message" and result:
        value = Session.llm_failures + 1 if result.reply_fallback else 0
        await db.execute(update(Session).where(Session.id == session_id).values(llm_failures=value))
    await db.execute(
        update(AgentRun)
        .where(AgentRun.run_id == run_id)
        .values(
            status="finished" if ok else "failed",
            usage=result.usage if result else {},
            finished_at=datetime.now(UTC),
        )
    )
    await db.commit()


async def run_agent(
    db: AsyncSession,
    runner: AgentRunner,
    locks: SessionLocks,
    session_id: uuid.UUID,
    stimulus: Stimulus,
    run_id: uuid.UUID,
    *,
    lock_held: bool = False,
) -> RunResult:
    """agent_runs started가 이미 커밋돼 있다고 가정하고, Lock 안에서 실행 후 결과를 기록한다.

    RunResult.ok=False면 agent_runs는 failed가 된다. 예외는 failed로 기록한 뒤 다시 올린다.
    """
    if lock_held:
        return await _execute(db, runner, session_id, stimulus, run_id)
    async with locks(session_id):
        return await _execute(db, runner, session_id, stimulus, run_id)


async def _execute(
    db: AsyncSession,
    runner: AgentRunner,
    session_id: uuid.UUID,
    stimulus: Stimulus,
    run_id: uuid.UUID,
) -> RunResult:
    try:
        result = await runner.run(session_id, stimulus, run_id)
    except Exception:
        await finish_run(db, run_id, None)
        raise
    await finish_run(db, run_id, result, session_id, stimulus)
    return result


async def llm_failures_exceeded(db: AsyncSession, session_id: uuid.UUID) -> bool:
    session = await db.get(Session, session_id, populate_existing=True)
    live = session is not None and session.status in ("in_progress", "reporting")
    return live and session.llm_failures >= LLM_FAILURE_LIMIT
