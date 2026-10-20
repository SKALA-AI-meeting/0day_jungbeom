"""MCP 도구가 없는 두 가지를 api 프로세스 안에서 직접 한다(에이전트가 api 안 모듈이라 가능).

- 분류 저장: 내부 `PUT /internal/sessions/{id}/messages/{message_id}/classification`과 같은 결과
  (messages.meta.classification). business-mcp에 대응 도구가 없다.
- 카드 조회: 자극의 event_ids → card_id. 내부 GET /sessions/{id}는 이벤트 행을 주지 않는다.
"""

import uuid
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Message, SessionEvent

CLASSIFICATION_KEYS = ("recipient", "kind", "instruction", "related_card")


class AgentStore(Protocol):
    async def save_classification(
        self, session_id: uuid.UUID, message_id: uuid.UUID, classification: dict[str, Any]
    ) -> None: ...

    async def event_cards(
        self, session_id: uuid.UUID, event_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]: ...


class DbAgentStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def save_classification(
        self, session_id: uuid.UUID, message_id: uuid.UUID, classification: dict[str, Any]
    ) -> None:
        body = {k: classification.get(k) for k in CLASSIFICATION_KEYS}
        async with self._factory() as db:
            message = await db.get(Message, message_id, populate_existing=True)
            if message is None or message.session_id != session_id:
                return
            message.meta = {**(message.meta or {}), "classification": body}
            await db.commit()

    async def event_cards(
        self, session_id: uuid.UUID, event_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        async with self._factory() as db:
            rows = await db.execute(
                select(SessionEvent.id, SessionEvent.card_id).where(
                    SessionEvent.session_id == session_id, SessionEvent.id.in_(event_ids)
                )
            )
            return {event_id: card_id for event_id, card_id in rows.all()}
