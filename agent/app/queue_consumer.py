"""RabbitMQ consumer (bonus: 대기열). Spring publishes tasks to agent.tasks; failures are retried with
backoff by republishing with x-attempt+1, and after the last attempt the message goes to the DLQ."""
from __future__ import annotations

import asyncio
import json
import logging
import os

import aio_pika

from . import runner

log = logging.getLogger("dayzero.queue")
EXCHANGE, QUEUE, DLX, DLQ = "dayzero.tasks", "agent.tasks", "dayzero.tasks.dlx", "agent.tasks.dlq"


async def consume(stop: asyncio.Event) -> None:
    url = os.environ["RABBIT_URL"]
    conn = await aio_pika.connect_robust(url)
    async with conn:
        ch = await conn.channel()
        await ch.set_qos(prefetch_count=4)
        ex = await ch.declare_exchange(EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True)
        dlx = await ch.declare_exchange(DLX, aio_pika.ExchangeType.DIRECT, durable=True)
        q = await ch.declare_queue(QUEUE, durable=True, arguments={"x-dead-letter-exchange": DLX, "x-dead-letter-routing-key": DLQ})
        dlq = await ch.declare_queue(DLQ, durable=True)
        await q.bind(ex, QUEUE)
        await dlq.bind(dlx, DLQ)

        async def handle(message: aio_pika.abc.AbstractIncomingMessage) -> None:
            attempt = int((message.headers or {}).get("x-attempt", 1))
            body = json.loads(message.body)
            final = attempt >= runner.MAX_ATTEMPTS
            try:
                await runner.execute({**body, "attempt": attempt}, final_attempt=final)
                await message.ack()
            except runner.NonRetryable:
                await message.reject(requeue=False)  # FAILED already reported -> DLQ
            except Exception as e:
                if final:
                    await message.reject(requeue=False)
                    return
                log.warning("task %s attempt %d failed (%s), retrying", body.get("taskId"), attempt, e)
                await asyncio.sleep(2 ** attempt)
                await ex.publish(aio_pika.Message(message.body, headers={"x-attempt": attempt + 1}, content_type="application/json",
                                                  delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key=QUEUE)
                await message.ack()

        await q.consume(lambda m: asyncio.create_task(handle(m)))
        log.info("consuming %s", QUEUE)
        await stop.wait()
