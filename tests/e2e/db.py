"""러너가 읽기 전용으로 보는 DB 값: agent_runs(턴 결정·상태), 세션 비용, 의도 분류 지연.

내부 REST에 없는 관측값이라 `E2E_DATABASE_URL`(없으면 `DATABASE_URL`)로 직접 읽는다. 없으면
NullDb라서 이 값에 의존하는 단언은 빈 값으로 본다(summary에 비용·지연 "-"로 남는다).
"""

import json
from typing import Any, Protocol


class Db(Protocol):
    available: bool

    async def agent_runs(self, session_id: str) -> list[dict[str, Any]]: ...
    async def costs(self, session_id: str) -> dict[str, Any]: ...
    async def intent_latency_ms(self, session_id: str) -> list[int]: ...
    async def close(self) -> None: ...


class NullDb:
    available = False

    async def agent_runs(self, session_id: str) -> list[dict[str, Any]]:
        return []

    async def costs(self, session_id: str) -> dict[str, Any]:
        return {}

    async def intent_latency_ms(self, session_id: str) -> list[int]:
        return []

    async def close(self) -> None:
        return None


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


class PgDb:
    available = True

    def __init__(self, url: str) -> None:
        self.url = url.replace("postgresql+asyncpg://", "postgresql://")
        self._conn: Any = None

    async def _connect(self) -> Any:
        if self._conn is None:
            import asyncpg

            self._conn = await asyncpg.connect(self.url)
        return self._conn

    async def agent_runs(self, session_id: str) -> list[dict[str, Any]]:
        conn = await self._connect()
        rows = await conn.fetch(
            "SELECT run_id::text, stimulus, status, decision, usage FROM agent_runs "
            "WHERE session_id = $1::uuid ORDER BY queued_at",
            session_id,
        )
        return [
            {**dict(r), "decision": _json(r["decision"]), "usage": _json(r["usage"])} for r in rows
        ]

    async def costs(self, session_id: str) -> dict[str, Any]:
        conn = await self._connect()
        row = await conn.fetchrow(
            "SELECT cost_usd::float, debate_cost_usd::float FROM sessions WHERE id = $1::uuid",
            session_id,
        )
        return dict(row) if row else {}

    async def intent_latency_ms(self, session_id: str) -> list[int]:
        conn = await self._connect()
        rows = await conn.fetch(
            "SELECT latency_ms FROM message_intents WHERE session_id = $1::uuid "
            "AND latency_ms IS NOT NULL",
            session_id,
        )
        return [r["latency_ms"] for r in rows]

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
