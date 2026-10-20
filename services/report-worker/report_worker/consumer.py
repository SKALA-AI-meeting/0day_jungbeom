"""큐 소비자 3개: report.generate·report.approve·report.dlq (worker-infra/design.md 1·4~7단계).

모두 prefetch 1, manual ack. 메시지 처리 규칙:
- generate: thread 상태 조회 → (멈춤이면 건너뜀) 그래프 실행 → interrupt에서 멈춤
  → POST /report/draft → ack. 체크포인트 → draft 저장 → ack 순서라 ack 뒤 승인에도 재개 대상이 있다.
- approve: 멈춘 thread를 Command(resume=True)로 재개 → finalize(POST /report/final) → ack.
  이미 끝났으면 ack만(중복 approve 멱등). 체크포인트가 없으면 nack 없이 15초 뒤 재발행.
- 실패: attempt+1로 재발행(백오프 5·15·45초 대기 후, 브로커 확인) → 원본 ack.
  attempt ≥ 3이면 report.dlq로 보낸다(최초 포함 총 3회).
- dlq: POST /report_failed 후 ack. api가 내려가 있으면 ack하지 않고 60초 뒤 다시 부른다.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aio_pika
from langgraph.types import Command
from pamqp.commands import Basic

from report_worker.api import ApiError, InternalApi, api_down
from report_worker.graph import has_checkpoint, is_done, is_paused, thread_config

log = logging.getLogger("report_worker.consumer")

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 15, 45)  # attempt 1·2·3 실패 뒤 재발행(3은 DLQ) 전 대기
APPROVE_NOT_READY_SECONDS = 15
DLQ_RETRY_SECONDS = 60

Publish = Callable[[str, dict[str, Any]], Awaitable[None]]
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class Topology:
    """api `app/queue.declare_topology`와 같은 이름. 테스트는 prefix로 공용 브로커에서 분리한다."""

    exchange: str = "dayzero"
    generate: str = "report.generate"
    approve: str = "report.approve"
    dlq: str = "report.dlq"

    @classmethod
    def prefixed(cls, prefix: str) -> "Topology":
        base = cls()
        return cls(
            *(prefix + name for name in (base.exchange, base.generate, base.approve, base.dlq))
        )


DEFAULT_TOPOLOGY = Topology()


class ReportWorker:
    """메시지 본문 하나를 처리하는 규칙. 브로커 연결과 분리해 테스트한다."""

    def __init__(
        self,
        graph: Any,
        api: InternalApi,
        publish: Publish,
        topology: Topology = DEFAULT_TOPOLOGY,
        *,
        sleep: Sleep = asyncio.sleep,
        backoff: tuple[float, ...] = BACKOFF_SECONDS,
        approve_wait: float = APPROVE_NOT_READY_SECONDS,
        dlq_wait: float = DLQ_RETRY_SECONDS,
    ) -> None:
        self.graph = graph
        self.api = api
        self.publish = publish
        self.topology = topology
        self.sleep = sleep
        self.backoff = backoff
        self.approve_wait = approve_wait
        self.dlq_wait = dlq_wait

    async def generate(self, body: dict[str, Any]) -> None:
        session_id = body["session_id"]
        config = thread_config(session_id)
        snapshot = await self.graph.aget_state(config)
        if is_done(snapshot):
            log.info("report %s already final, ack only", session_id)
            return
        if not is_paused(snapshot):
            # 체크포인트가 중간에 멈춰 있으면(None 입력) 거기서 이어서, 없으면 처음부터
            start = None if has_checkpoint(snapshot) else {"session_id": session_id}
            await self.graph.ainvoke(start, config)
            snapshot = await self.graph.aget_state(config)
            if not is_paused(snapshot):
                raise RuntimeError(f"report graph did not stop at approval: {snapshot.next}")
        values = snapshot.values
        await self.api.save_draft(session_id, values["draft"], values.get("usage"))
        log.info("report %s draft saved (thread %s)", session_id, config["configurable"])

    async def approve(self, body: dict[str, Any]) -> None:
        session_id = body["session_id"]
        config = thread_config(session_id)
        snapshot = await self.graph.aget_state(config)
        if is_done(snapshot):
            log.info("report %s already reviewed, ack only", session_id)
            return
        if is_paused(snapshot):
            await self.graph.ainvoke(Command(resume=True), config)
        elif snapshot.next == ("finalize",):
            # 승인 뒤 finalize가 실패했던 thread. final은 api가 같은 해시면 200 기존 값을 준다
            await self.graph.ainvoke(None, config)
        else:
            log.info("report %s not paused yet, republish in %ss", session_id, self.approve_wait)
            await self.sleep(self.approve_wait)
            await self.publish(self.topology.approve, body)
            return
        snapshot = await self.graph.aget_state(config)
        if not is_done(snapshot):
            raise RuntimeError(f"report graph did not finish: {snapshot.next}")
        log.info("report %s final saved (thread %s)", session_id, config["configurable"])

    async def handle(
        self, queue: str, body: dict[str, Any], handler: Callable[[dict], Awaitable[None]]
    ) -> None:
        """handler 실패 시 재발행 또는 DLQ. 여기서 돌아오면 호출자가 원본을 ack한다."""
        try:
            await handler(body)
        except Exception as exc:
            attempt = int(body.get("attempt", 1))
            error = f"{queue} attempt {attempt}: {type(exc).__name__}: {exc}"
            log.warning("report %s failed: %s", body.get("session_id"), error)
            await self.sleep(self.backoff[min(attempt, len(self.backoff)) - 1])
            if attempt >= MAX_ATTEMPTS:
                log.error("report %s → dlq: %s", body.get("session_id"), error)
                await self.publish(self.topology.dlq, {**body, "error": error})
            else:
                await self.publish(queue, {**body, "attempt": attempt + 1})

    async def dead_letter(self, body: dict[str, Any]) -> None:
        """report_failed가 성공하거나 api가 고칠 수 없는 오류(4xx)를 줄 때까지 ack하지 않는다."""
        error = body.get("error") or "report failed"
        while True:
            try:
                await self.api.report_failed(body["session_id"], error)
                log.error("report %s marked failed: %s", body["session_id"], error)
                return
            except Exception as exc:
                if not api_down(exc):
                    if isinstance(exc, ApiError):
                        log.error("report_failed rejected for %s: %s", body["session_id"], exc)
                        return
                    raise
                log.warning("api down, report_failed retry in %ss", self.dlq_wait)
                await self.sleep(self.dlq_wait)


async def declare_topology(
    channel: aio_pika.abc.AbstractChannel, topology: Topology
) -> aio_pika.abc.AbstractExchange:
    """api `app/queue.declare_topology`와 같은 선언(멱등). 어느 쪽이 먼저 떠도 된다."""
    exchange = await channel.declare_exchange(
        topology.exchange, aio_pika.ExchangeType.DIRECT, durable=True
    )
    dlq = await channel.declare_queue(topology.dlq, durable=True)
    await dlq.bind(exchange, routing_key=topology.dlq)
    dead_letter = {
        "x-dead-letter-exchange": topology.exchange,
        "x-dead-letter-routing-key": topology.dlq,
    }
    for name in (topology.generate, topology.approve):
        queue = await channel.declare_queue(name, durable=True, arguments=dead_letter)
        await queue.bind(exchange, routing_key=name)
    return exchange


class RabbitConsumer:
    """브로커 연결. 발행 채널(publisher confirm) 하나와 큐마다 소비 채널(prefetch 1)."""

    def __init__(self, url: str, topology: Topology = DEFAULT_TOPOLOGY) -> None:
        self.url = url
        self.topology = topology
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self.url)
        channel = await self._connection.channel(publisher_confirms=True, on_return_raises=True)
        self._exchange = await declare_topology(channel, self.topology)

    async def publish(self, routing_key: str, body: dict[str, Any]) -> None:
        assert self._exchange is not None, "connect() first"
        message = aio_pika.Message(
            json.dumps(body).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        result = await self._exchange.publish(message, routing_key=routing_key, mandatory=True)
        if not isinstance(result, Basic.Ack):
            raise RuntimeError(f"publish {routing_key} not confirmed: {type(result).__name__}")

    async def consume(self, worker: ReportWorker) -> None:
        assert self._connection is not None, "connect() first"
        t = self.topology
        routes = {
            t.generate: lambda body: worker.handle(t.generate, body, worker.generate),
            t.approve: lambda body: worker.handle(t.approve, body, worker.approve),
            t.dlq: worker.dead_letter,
        }
        for name, process in routes.items():
            channel = await self._connection.channel()
            await channel.set_qos(prefetch_count=1)
            queue = await channel.get_queue(name)
            await queue.consume(self._callback(name, process), no_ack=False)

    def _callback(self, name: str, process: Callable[[dict], Awaitable[None]]):
        async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
            try:
                body = json.loads(message.body)
            except ValueError:
                log.error("%s: invalid body, dropped: %r", name, message.body[:200])
                await message.ack()
                return
            try:
                await process(body)
            except Exception:
                # 재발행 자체가 실패(브로커 장애 등)하면 원본을 되돌려 다시 받는다
                log.exception("%s: processing failed, requeue", name)
                await message.nack(requeue=True)
                return
            await message.ack()

        return on_message

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        self._connection = self._exchange = None
