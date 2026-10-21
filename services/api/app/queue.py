"""RabbitMQ 발행. 메시지는 persistent, 채널은 publisher confirm이다.

publish()가 예외 없이 끝나면 브로커가 받은 것이다.

토폴로지(docs/worker-infra/design.md): exchange `dayzero`(direct), 큐 report.generate·report.approve
(durable, DLX → report.dlq), report.dlq.
발행 실패는 예외로 올라가고 호출자는 *_enqueued_at을 비워 둔다.
비워 둔 세션은 republish_pending()(스케줄러가 60초마다 호출)이 다시 발행한다.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Protocol

import aio_pika
from pamqp.commands import Basic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session

log = logging.getLogger(__name__)

EXCHANGE = "dayzero"
GENERATE = "report.generate"
APPROVE = "report.approve"
DLQ = "report.dlq"


class PublishNotConfirmed(RuntimeError):
    """브로커가 Basic.Ack로 확인하지 않음(라우팅 실패 반환 등). enqueued_at을 기록하지 않는다."""


class Publisher(Protocol):
    async def publish(self, routing_key: str, body: dict[str, Any]) -> None: ...


class RabbitPublisher:
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def _ensure(self) -> aio_pika.abc.AbstractExchange:
        if self._exchange is None:
            self._connection = await aio_pika.connect_robust(self._url)
            # on_return_raises: 라우팅되지 않아 반환된 메시지를 PublishError로 올린다
            channel = await self._connection.channel(publisher_confirms=True, on_return_raises=True)
            self._exchange = await declare_topology(channel)
        return self._exchange

    async def publish(self, routing_key: str, body: dict[str, Any]) -> None:
        exchange = await self._ensure()
        message = aio_pika.Message(
            json.dumps(body).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        result = await exchange.publish(message, routing_key=routing_key, mandatory=True)
        if not isinstance(result, Basic.Ack):
            raise PublishNotConfirmed(f"{routing_key}: {type(result).__name__}")

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        self._connection = self._exchange = None


async def declare_topology(channel: aio_pika.abc.AbstractChannel) -> aio_pika.abc.AbstractExchange:
    exchange = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue(DLQ, durable=True)
    await dlq.bind(exchange, routing_key=DLQ)
    dead_letter = {"x-dead-letter-exchange": EXCHANGE, "x-dead-letter-routing-key": DLQ}
    for name in (GENERATE, APPROVE):
        queue = await channel.declare_queue(name, durable=True, arguments=dead_letter)
        await queue.bind(exchange, routing_key=name)
    return exchange


def report_body(session_id: uuid.UUID, eval_round: int, attempt: int = 1) -> dict[str, Any]:
    """contracts.md 큐 메시지 {session_id, attempt, eval_round}. 첫 발행은 attempt=1.

    워커는 실패 시 attempt+1로 재발행하고 3에 이르면 DLQ로 보낸다.
    """
    return {"session_id": str(session_id), "attempt": attempt, "eval_round": eval_round}


class MemoryPublisher:
    """테스트·개발용. 발행한 (routing_key, body)를 기록한다. fail=True면 발행 실패를 흉내 낸다."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.fail = False

    async def publish(self, routing_key: str, body: dict[str, Any]) -> None:
        if self.fail:
            raise ConnectionError("publisher down")
        self.published.append((routing_key, body))


async def publish_report(
    db: AsyncSession, publisher: Publisher, session: Session, routing_key: str, now: datetime
) -> bool:
    """발행하고 브로커 확인 뒤에만 enqueued_at을 기록·커밋한다.

    실패하면 False를 돌려주고 기록을 비워 둔다(outbox가 다시 시도).
    """
    column = "report_enqueued_at" if routing_key == GENERATE else "approve_enqueued_at"
    try:
        await publisher.publish(routing_key, report_body(session.id, session.eval_round))
    except Exception:
        log.warning("publish %s failed for session %s", routing_key, session.id, exc_info=True)
        return False
    setattr(session, column, now)
    await db.commit()
    return True


async def republish_pending(db: AsyncSession, publisher: Publisher, now: datetime) -> int:
    """outbox 재탐색. 미발행 세션을 다시 발행한다.

    completed인데 report_enqueued_at 없음 → generate.
    approving인데 approve_enqueued_at 없음 → approve.
    """
    targets = [
        (GENERATE, Session.status == "completed", Session.report_enqueued_at.is_(None)),
        (APPROVE, Session.status == "approving", Session.approve_enqueued_at.is_(None)),
    ]
    published = 0
    for routing_key, *conditions in targets:
        rows = (await db.execute(select(Session).where(*conditions))).scalars().all()
        for session in rows:
            published += await publish_report(db, publisher, session, routing_key, now)
    return published
