"""`python -m report_worker`. heartbeat 루프와 큐 소비자 3개를 같은 asyncio 루프에서 돌린다."""

import asyncio
import logging
import os

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from report_worker import heartbeat
from report_worker.api import InternalApi
from report_worker.assessment import AssessmentClient
from report_worker.config import load_settings
from report_worker.consumer import RabbitConsumer, ReportWorker
from report_worker.graph import Deps, build_graph
from report_worker.llm import FakeEvaluatorLLM, OpenAILLM


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("report_worker")
    settings = load_settings()
    beating = asyncio.create_task(heartbeat.run())
    log.info("heartbeat at %s", heartbeat.heartbeat_path())

    api = InternalApi(settings.api_internal_url, settings.internal_token)
    deps = Deps(
        api=api,
        assessment=AssessmentClient(settings.assessment_mcp_url, settings.assessment_mcp_token),
        llm=FakeEvaluatorLLM()
        if os.environ.get("LLM_FAKE") == "1"
        else OpenAILLM(settings.model_evaluator, os.environ),
    )
    consumer = RabbitConsumer(settings.rabbitmq_url)
    # 워커는 thread report:{session_id}:{eval_round}만 접근한다
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
        await saver.setup()
        graph = build_graph(deps, saver)
        await consumer.connect()
        await consumer.consume(ReportWorker(graph, api, consumer.publish))
        log.info("consuming report.generate, report.approve, report.dlq (model %s)", deps.llm.model)
        try:
            await beating  # heartbeat는 끝나지 않는다. 소비는 aio-pika 콜백으로 돈다
        finally:
            await consumer.close()
            await api.close()


if __name__ == "__main__":
    asyncio.run(main())
