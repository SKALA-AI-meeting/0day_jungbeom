"""완료 기준: api를 내린 상태에서 발행 → 3회 시도 후 DLQ, 복구 후 report_failed 반영.

공용 RabbitMQ에 테스트 전용 접두사로 exchange·큐를 만들고 끝나면 지운다(다른 트랙과 겹치지 않음).
백오프와 dlq 재시도 간격만 짧게 바꾼다.
"""

import asyncio
import uuid

import aio_pika
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from report_worker.config import load_settings
from report_worker.consumer import RabbitConsumer, ReportWorker, Topology
from report_worker.graph import build_graph

from tests.conftest import FakeLLM


async def wait_until(predicate, timeout: float = 10.0) -> None:
    async def poll():
        while not predicate():
            await asyncio.sleep(0.02)

    await asyncio.wait_for(poll(), timeout)


@pytest.fixture
async def broker():
    url = load_settings().rabbitmq_url
    topology = Topology.prefixed(f"test-worker-{uuid.uuid4().hex[:8]}.")
    consumer = RabbitConsumer(url, topology)
    try:  # connect 도중 일부 토폴로지만 만들고 실패해도 지운다
        try:
            await consumer.connect()
        except Exception as exc:
            pytest.skip(f"rabbitmq unavailable: {type(exc).__name__}")
        yield consumer
    finally:
        await consumer.close()
        await delete_topology(url, topology)


async def delete_topology(url: str, topology: Topology) -> None:
    try:
        connection = await aio_pika.connect(url)
    except Exception:
        return  # 브로커에 닿지 않으면 만든 것도 없다
    async with connection:
        for name in (topology.generate, topology.approve, topology.dlq, topology.exchange):
            channel = await connection.channel()  # 실패한 삭제가 채널을 닫아도 다음은 새 채널
            try:
                if name == topology.exchange:
                    await channel.exchange_delete(name)
                else:
                    await channel.queue_delete(name)
            except Exception:
                pass


async def test_api_down_retries_then_dlq_then_report_failed(api, fake_api, broker):
    graph = build_graph(api, FakeLLM(), InMemorySaver())
    worker = ReportWorker(
        graph, api, broker.publish, broker.topology, backoff=(0.01, 0.01, 0.01), dlq_wait=0.05
    )
    attempts = []
    generate = worker.generate

    async def tracked(body):
        attempts.append(body["attempt"])
        await generate(body)

    worker.generate = tracked
    fake_api.down = True
    await broker.consume(worker)
    await broker.publish(
        broker.topology.generate, {"session_id": fake_api.session_id, "attempt": 1}
    )

    # 3회 실패 → dlq 소비자가 report_failed를 부르지만 api가 내려가 있어 ack하지 않고 기다림
    await wait_until(lambda: len(fake_api.posts("/report_failed")) >= 2)
    assert attempts == [1, 2, 3]
    assert fake_api.status == "completed"

    fake_api.down = False  # 복구
    await wait_until(lambda: fake_api.status == "failed")
    error = fake_api.posts("/report_failed")[-1]["error"]
    assert error.startswith(f"{broker.topology.generate} attempt 3: ConnectError")
