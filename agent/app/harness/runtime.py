"""Per-task runtime shared by all harness components (contextvar, so graph nodes need no extra arguments)."""
from __future__ import annotations

import contextvars
from collections import Counter
from dataclasses import dataclass, field

from .events import EventPublisher
from .loop import Limits
from .observability import Tracer


@dataclass
class TaskContext:
    task_id: str
    session_id: str | None
    attempt: int
    events: EventPublisher
    tracer: Tracer
    limits: Limits = field(default_factory=Limits)
    tool_counts: Counter = field(default_factory=Counter)
    model_calls: int = 0


_CURRENT: contextvars.ContextVar[TaskContext | None] = contextvars.ContextVar("dayzero_task", default=None)


def current() -> TaskContext | None:
    return _CURRENT.get()


def bind(ctx: TaskContext):
    return _CURRENT.set(ctx)


def unbind(token) -> None:
    _CURRENT.reset(token)


async def emit(type_: str, data: dict | None = None) -> None:
    ctx = current()
    if ctx is not None:
        await ctx.events.emit(type_, {**(data or {}), "attempt": ctx.attempt})
