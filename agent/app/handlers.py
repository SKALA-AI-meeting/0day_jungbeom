"""Task handlers: one entry per agent task type (START, TURN, REPORT, ACCOUNT_REVIEW, ANALYTICS, ...).

Spring keeps the matching TaskHandler bean (dev.dayzero.backend.task) and GET /agent/handlers lets it check that both
sides know the same types. A handler is

    run(msg, ctx)  -> dict   the DONE payload, or {"_interrupt": ask} when the graph paused for a person (APPROVAL_REQUIRED)
    resume(msg)    -> dict   continue the paused graph on the same thread after the decision (None: the type never pauses)

To add a workflow: write its run (and resume) in runner.py and add one Handler to runner.HANDLERS (+ a TaskHandler in Spring).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass

from .harness.runtime import TaskContext

Run = Callable[[dict, TaskContext], Awaitable[dict]]
Resume = Callable[[dict], Awaitable[dict]]


@dataclass(frozen=True)
class Handler:
    type: str
    run: Run
    resume: Resume | None = None
    description: str = ""

    @property
    def resumable(self) -> bool:
        return self.resume is not None

    def describe(self) -> dict:
        return {"type": self.type, "resumable": self.resumable, "description": self.description}


class Registry(Mapping):
    """Read-only type -> Handler map. A duplicate or malformed type is a programming error, raised at import."""

    def __init__(self, handlers: Iterable[Handler] = ()) -> None:
        self._by_type: dict[str, Handler] = {}
        for h in handlers:
            self.register(h)

    def register(self, h: Handler) -> Handler:
        if not h.type or h.type != h.type.upper() or not h.type.replace("_", "").isalnum():
            raise ValueError(f"task type must be UPPER_SNAKE: {h.type!r}")
        if h.type in self._by_type:
            raise ValueError(f"duplicate task handler {h.type}")
        self._by_type[h.type] = h
        return h

    def __getitem__(self, type_: str) -> Handler:
        return self._by_type[type_]

    def __iter__(self) -> Iterator[str]:
        return iter(self._by_type)

    def __len__(self) -> int:
        return len(self._by_type)

    def describe(self) -> list[dict]:
        return [h.describe() for h in self._by_type.values()]
