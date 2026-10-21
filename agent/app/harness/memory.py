"""State·Memory: LangGraph checkpointer. PostgreSQL (AsyncPostgresSaver) when DATABASE_URL is set, else in-memory.
Every task runs on its own thread id; a report task paused for approval resumes on the same thread id."""
from __future__ import annotations

import os

from langgraph.checkpoint.memory import InMemorySaver

_saver = None
_cm = None


async def open_checkpointer():
    global _saver, _cm
    if _saver is not None:
        return _saver
    url = os.getenv("DATABASE_URL")
    if url:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        _cm = AsyncPostgresSaver.from_conn_string(url)
        _saver = await _cm.__aenter__()
        await _saver.setup()
    else:
        _saver = InMemorySaver()
    return _saver


async def close_checkpointer() -> None:
    global _saver, _cm
    if _cm is not None:
        await _cm.__aexit__(None, None, None)
    _saver, _cm = None, None


def kind() -> str:
    return type(_saver).__name__ if _saver else "none"
