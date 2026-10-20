"""보드(tasks)와 분업 확정. 지원자 PUT /tasks와 내부 PUT /division·PUT /tasks가 함께 쓴다.

보드가 분업의 정상 경로다(docs/common/scenario-model.md "분업 확정 경로"): 5행의 assignee가 다 차고
division_min을 만족하는 순간 sessions.division을 확정한다. 바뀐 필드마다 task_events를 남기며, 동료
쪽 변경은 (session_id, part_no, field, run_id)로 멱등이다. 커밋과 브로드캐스트는 호출자가 한다.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session, SessionEvent, Task, TaskEvent

FIELDS = ("assignee", "status", "order", "due_min")
# 확정 뒤 재분업 한도: 적응성 카드 전 1회 + 뒤 1회(docs/agent/design.md "업무 중 재분업").
# 경로마다 한 번의 재분업을 세는 단위가 다르다. 채팅(동료 set_division)은 결정 하나가 1회다.
# 보드는 카드 한 장씩 PUT하므로 같은 단계의 첫 보드 재배정 뒤 1분 안에 이어지는 보드 PUT만
# 같은 묶음으로 본다.
# 다른 경로(보드↔채팅)의 변경이나 묶음 밖 변경은 새 재분업이라 같은 단계에서는 거부한다
REDIVIDE_GRACE_MIN = 1.0
REDIVIDE_LIMIT_TEXT = "일정상 지금 더 바꾸긴 어렵겠어요. 지금 분담대로 마무리해 주세요."
COLLEAGUE_PARTS = {"colleague", "both"}


class InvalidDivision(ValueError):
    """division_min 위반·파트 누락(422 invalid_division). 메시지는 화면에 그대로 쓰는 조건 문장."""


def task_json(task: Task) -> dict[str, Any]:
    return {
        "part_no": task.part_no,
        "assignee": task.assignee,
        "status": task.status,
        "order": task.order,
        "due_min": task.due_min,
        "depends_on": list(task.depends_on or []),
    }


def initial_tasks(session_id: uuid.UUID, scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """세션 시작 때 만드는 5행. assignee=null, order=파트 번호, depends_on은 미션에서 복사."""
    return [
        {
            "session_id": session_id,
            "part_no": int(no),
            "order": int(no),
            "depends_on": part.get("depends_on", []),
        }
        for no, part in scenario["parts"].items()
    ]


def check_division(parts: dict[str, str | None], scenario: dict[str, Any]) -> None:
    """모든 파트가 정해지고 division_min을 만족하는지 본다.

    2번 candidate, 3번 colleague 또는 both, 4·5 중 하나 이상 colleague 단독. 위반 문장은 미션의
    division_min_messages(팀 사정 말투)를 쓴다.
    """
    messages = scenario["division_min_messages"]
    if set(parts) != set(scenario["parts"]) or any(v is None for v in parts.values()):
        raise InvalidDivision(messages["missing"])
    rule = scenario["division_min"]
    for no, allowed in rule.items():
        if no != "any_colleague_only" and parts[no] not in allowed:
            raise InvalidDivision(messages[no])
    if not any(parts[str(no)] == "colleague" for no in rule["any_colleague_only"]):
        raise InvalidDivision(messages["any_colleague_only"])


async def redivide_stage(db: AsyncSession, session_id: uuid.UUID) -> str:
    """지금 재분업이 적응성 카드 전(before_change)인지 뒤(after_change)인지."""
    status = await db.scalar(
        select(SessionEvent.status).where(
            SessionEvent.session_id == session_id, SessionEvent.card_id == "adaptability_change"
        )
    )
    return "after_change" if status in ("fired", "done", "failed") else "before_change"


def _session_minutes(session: Session, now: datetime) -> float:
    return (now - session.started_at).total_seconds() / 60


def redivide_allowed(session: Session, stage: str, now: datetime, via: str) -> bool:
    """이 단계의 재분업을 아직 안 썼으면 허용. 썼으면 보드 묶음(보드로 시작한 재분업의 1분 안 보드
    PUT)만 허용한다. via는 board(지원자 보드 PUT)·chat(채팅 결정을 동료가 set_division)."""
    for row in session.redivisions or []:
        if row["stage"] == stage:
            same_batch = via == "board" and row.get("via") == "board"
            elapsed = _session_minutes(session, now) - row["t_min"]
            return same_batch and elapsed <= REDIVIDE_GRACE_MIN
    return True


async def use_redivide(db: AsyncSession, session: Session, via: str) -> None:
    """확정 뒤 담당 재배정 한 번. 한도를 넘으면 InvalidDivision(422). 보드 PUT·동료 set_division
    공용."""
    stage, now = await redivide_stage(db, session.id), datetime.now(UTC)
    if not redivide_allowed(session, stage, now, via):
        raise InvalidDivision(REDIVIDE_LIMIT_TEXT)
    if all(row["stage"] != stage for row in session.redivisions or []):
        row = {"stage": stage, "via": via, "t_min": round(_session_minutes(session, now), 2)}
        session.redivisions = [*(session.redivisions or []), row]


async def load_tasks(db: AsyncSession, session_id: uuid.UUID, lock: bool = False) -> list[Task]:
    query = select(Task).where(Task.session_id == session_id).order_by(Task.part_no)
    if lock:
        # 보드 쓰기를 직렬화한다: "다 찼는지" 판단이 동시 PUT에서 엇갈리지 않게
        query = query.with_for_update()
    rows = await db.execute(query.execution_options(populate_existing=True))
    return list(rows.scalars())


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


async def _record(
    db: AsyncSession,
    session_id: uuid.UUID,
    part_no: int,
    by: str,
    name: str,
    old: Any,
    new: Any,
    run_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """task_event 한 행. 동료 변경의 같은 run_id 재요청이면 None(이미 있음)."""
    stmt = (
        insert(TaskEvent)
        .values(
            session_id=session_id,
            part_no=part_no,
            by=by,
            field=name,
            old_value=_text(old),
            new_value=_text(new),
            run_id=run_id,
        )
        .on_conflict_do_nothing(
            index_elements=["session_id", "part_no", "field", "run_id"],
            index_where=TaskEvent.run_id.is_not(None),
        )
        .returning(TaskEvent.id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


@dataclass
class BoardChange:
    """지원자 보드 변경 결과. division_changed면 동료에게 division 자극을 보낸다."""

    task: Task
    event_ids: list[uuid.UUID] = field(default_factory=list)
    confirmed: bool = False  # 이번 변경으로 처음 확정됨(division.confirmed)
    division_changed: bool = False  # 확정 또는 확정 뒤 재배정


async def candidate_update(
    db: AsyncSession,
    session: Session,
    scenario: dict[str, Any],
    part_no: int,
    changes: dict[str, Any],
) -> BoardChange:
    """지원자가 카드 한 장의 필드를 바꾼다. 위반이면 InvalidDivision을 올리고 호출자가 롤백한다."""
    tasks = await load_tasks(db, session.id, lock=True)
    by_part = {t.part_no: t for t in tasks}
    task = by_part.get(part_no)
    if task is None:
        raise LookupError(f"task {part_no} not found")
    result = BoardChange(task=task)
    for name in FIELDS:
        if name not in changes or getattr(task, name) == changes[name]:
            continue
        old = getattr(task, name)
        setattr(task, name, changes[name])
        event_id = await _record(
            db, session.id, part_no, "candidate", name, old, changes[name], None
        )
        result.event_ids.append(event_id)

    parts = {str(t.part_no): t.assignee for t in tasks}
    if "assignee" not in changes or all(v is None for v in parts.values()):
        return result
    if any(v is None for v in parts.values()):
        return result  # 아직 채우는 중
    check_division(parts, scenario)
    current = session.division or {}
    if current.get("parts") == parts:
        return result
    if current:
        await use_redivide(db, session, "board")
    result.division_changed = True
    result.confirmed = not current
    session.division = {
        "parts": parts,
        "decided_by": current.get("decided_by", "candidate"),
        "decided_at": current.get("decided_at") or datetime.now(UTC).isoformat(),
    }
    return result


async def set_division(
    db: AsyncSession,
    session: Session,
    scenario: dict[str, Any],
    parts: dict[str, str],
    decided_by: str,
    run_id: uuid.UUID,
) -> tuple[list[Task], bool]:
    """동료 set_division(채팅 분업·기본안). (tasks, changed). 같은 내용 재요청은 changed=False."""
    check_division(parts, scenario)
    current = session.division or {}
    tasks = await load_tasks(db, session.id, lock=True)
    if current.get("parts") == parts:
        return tasks, False
    if current:
        await use_redivide(db, session, "chat")
    for task in tasks:
        new = parts[str(task.part_no)]
        if task.assignee != new:
            await _record(
                db, session.id, task.part_no, "colleague", "assignee", task.assignee, new, run_id
            )
            task.assignee = new
    session.division = {
        "parts": parts,
        # 지원자가 보드로 먼저 확정했으면 그 결정 주체를 유지한다(이 호출은 재배정)
        "decided_by": current.get("decided_by", decided_by),
        "decided_at": current.get("decided_at") or datetime.now(UTC).isoformat(),
    }
    return tasks, True


async def colleague_status(
    db: AsyncSession, session_id: uuid.UUID, part_no: int, status: str, run_id: uuid.UUID
) -> Task:
    """동료는 자기 담당(colleague·both) 카드의 상태만 바꾼다. 아니면 PermissionError(403)."""
    task = await db.get(Task, (session_id, part_no), populate_existing=True, with_for_update=True)
    if task is None:
        raise LookupError(f"task {part_no} not found")
    if task.assignee not in COLLEAGUE_PARTS:
        raise PermissionError("not a colleague task")
    if task.status != status:
        if await _record(
            db, session_id, part_no, "colleague", "status", task.status, status, run_id
        ):
            task.status = status
    return task
