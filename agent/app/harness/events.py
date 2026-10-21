"""Progress events (TOKEN, TOOL_START, TOOL_END, APPROVAL_REQUIRED, DONE, FAILED) -> Spring Boot -> SSE.

The agent does not know which screen listens (publish/subscribe). Events are batched to keep
TOKEN traffic cheap; terminal events flush immediately and keep order.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable

import httpx

log = logging.getLogger("dayzero.events")
TERMINAL = {"DONE", "FAILED", "APPROVAL_REQUIRED"}
Sink = Callable[[str, list[dict]], Awaitable[None]]


def spring_sink() -> Sink:
    base = os.getenv("BACKEND_INTERNAL_URL", "http://127.0.0.1:8081")
    key = os.getenv("INTERNAL_KEY", "dev-internal-key-change-me")
    client = httpx.AsyncClient(base_url=base, headers={"X-Internal-Key": key}, timeout=10)

    async def send(task_id: str, batch: list[dict]) -> None:
        for attempt in range(3):
            try:
                r = await client.post(f"/internal/tasks/{task_id}/events", json=batch)
                r.raise_for_status()
                return
            except Exception as e:  # events are best-effort, never break the task
                log.warning("event post failed (%s), attempt %d", e, attempt + 1)
                await asyncio.sleep(0.3 * (attempt + 1))

    return send


class MemorySink:
    """Test sink: records every event in order."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def __call__(self, task_id: str, batch: list[dict]) -> None:
        self.events += [(task_id, e) for e in batch]


class EventPublisher:
    def __init__(self, task_id: str, sink: Sink, flush_every: float = 0.12) -> None:
        self.task_id, self.sink, self.flush_every = task_id, sink, flush_every
        self._buf: list[dict] = []
        self._lock = asyncio.Lock()
        self._loop_task: asyncio.Task | None = None

    async def emit(self, type_: str, data: dict) -> None:
        self._buf.append({"type": type_, "data": data})
        if type_ in TERMINAL or len(self._buf) >= 24:
            await self.flush()
        elif self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._delayed())

    async def _delayed(self) -> None:
        await asyncio.sleep(self.flush_every)
        await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            if not self._buf:
                return
            batch, self._buf = self._buf, []
            await self.sink(self.task_id, batch)

    async def close(self) -> None:
        await self.flush()
