"""완료 기준(docs/worker-infra/design.md):
- draft 생성 후 그래프가 멈춤 → approve로 같은 thread 재개 → final 저장(draft와 동일 해시)
- 중복 approve 멱등, final 저장 후 ack 전 재전달은 200 기존 값
- 재생성: final 뒤 세션이 completed로 돌아오면 thread를 지우고 새 draft
- 사용량은 LLM 호출 없이 기록(리포트 문장은 카탈로그에서 온다)
"""

import uuid

import psycopg
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from report_worker.config import load_settings
from report_worker.consumer import ReportWorker, Topology
from report_worker.graph import build_graph, is_done, is_paused, thread_config

from tests.conftest import FakeLLM, content_hash


async def no_sleep(_seconds: float) -> None:
    return None


class Published(list):
    async def __call__(self, routing_key, body):
        self.append((routing_key, body))


def make_worker(api, checkpointer, llm=None):
    llm = llm or FakeLLM()
    published = Published()
    graph = build_graph(api, llm, checkpointer)
    worker = ReportWorker(graph, api, published, Topology(), sleep=no_sleep)
    return worker, graph, llm, published


@pytest.fixture(params=["memory", "postgres"])
async def checkpointer(request):
    """InMemorySaver와 실제 PostgresSaver. postgres는 공용 DB의 임시 스키마를 쓰고 끝나면 지운다."""
    if request.param == "memory":
        yield InMemorySaver()
        return
    url = load_settings().database_url
    schema = f"test_worker_{uuid.uuid4().hex[:8]}"
    try:
        admin = await psycopg.AsyncConnection.connect(url, autocommit=True)
    except Exception as exc:
        pytest.skip(f"postgres unavailable: {type(exc).__name__}")
    conn = None
    try:  # 중간에 실패해도 스키마를 지운다
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        conn = await psycopg.AsyncConnection.connect(
            url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
            options=f"-c search_path={schema}",
        )
        saver = AsyncPostgresSaver(conn)
        await saver.setup()
        yield saver
    finally:
        if conn is not None:
            await conn.close()
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.close()


async def test_draft_pauses_then_approve_resumes_with_same_hash(api, fake_api, checkpointer):
    worker, graph, llm, _ = make_worker(api, checkpointer)
    body = {"session_id": fake_api.session_id, "attempt": 1}
    config = thread_config(fake_api.session_id)
    assert config["configurable"]["thread_id"] == f"report:{fake_api.session_id}"

    await worker.handle("report.generate", body, worker.generate)
    assert is_paused(await graph.aget_state(config))
    assert fake_api.status == "report_ready"
    draft = fake_api.posts("/report/draft")[0]["content"]
    assert draft["stage"] == "draft"
    assert draft["rubric"]["auto_total"] == {"met": 18, "unmet": 2, "no_record": 0}

    # generate 재전달: 멈춘 thread는 collect·draft를 다시 돌지 않고 draft 저장만 한다
    await worker.handle("report.generate", body, worker.generate)
    assert len(fake_api.posts("/report/draft")) == 2

    fake_api.status = "approving"  # 담당자 검토 완료(api)
    await worker.handle("report.approve", body, worker.approve)
    assert is_done(await graph.aget_state(config))
    final = fake_api.posts("/report/final")[0]["content"]
    assert content_hash(final) == content_hash(draft)
    assert fake_api.status == "reviewed"
    assert llm.calls == 0


async def test_duplicate_approve_is_idempotent(api, fake_api):
    worker, _, _, published = make_worker(api, InMemorySaver())
    body = {"session_id": fake_api.session_id, "attempt": 1}
    await worker.handle("report.generate", body, worker.generate)
    fake_api.status = "approving"
    await worker.handle("report.approve", body, worker.approve)
    await worker.handle("report.approve", body, worker.approve)
    assert len(fake_api.posts("/report/final")) == 1  # 이미 reviewed면 상태 확인 후 ack만
    assert published == []


async def test_redelivery_after_final_before_ack_returns_existing(api, fake_api):
    worker, graph, _, published = make_worker(api, InMemorySaver())
    body = {"session_id": fake_api.session_id, "attempt": 1}
    await worker.handle("report.generate", body, worker.generate)
    fake_api.status = "approving"
    fake_api.lose_final_response_once = True  # api는 final을 저장했지만 워커가 응답을 못 받음

    await worker.handle("report.approve", body, worker.approve)
    assert fake_api.status == "reviewed"
    assert published == [("report.approve", {**body, "attempt": 2})]

    await worker.handle("report.approve", published[0][1], worker.approve)
    finals = fake_api.posts("/report/final")
    assert len(finals) == 2 and content_hash(finals[0]["content"]) == content_hash(
        finals[1]["content"]
    )
    state = await graph.aget_state(thread_config(fake_api.session_id))
    assert is_done(state) and state.values["final"]["status"] == "reviewed"  # 200 기존 값


async def test_regenerate_after_final_starts_new_thread(api, fake_api, checkpointer):
    """리포트 재생성: final 뒤 api가 draft를 지우고 completed로 되돌리면 이전 승인 체크포인트를
    이어받지 않고 다시 모은 데이터로 새 draft를 만든다."""
    worker, graph, _, _ = make_worker(api, checkpointer)
    body = {"session_id": fake_api.session_id, "attempt": 1}
    await worker.handle("report.generate", body, worker.generate)
    fake_api.status = "approving"
    await worker.handle("report.approve", body, worker.approve)

    fake_api.status, fake_api.report = "completed", None
    row = next(o for o in fake_api.data["observations"] if o["card_id"] == "adaptability_change")
    row["label"] = "no_evidence"
    await worker.handle("report.generate", body, worker.generate)
    assert is_paused(await graph.aget_state(thread_config(fake_api.session_id)))
    drafts = fake_api.posts("/report/draft")
    assert len(drafts) == 2 and fake_api.status == "report_ready"
    assert drafts[1]["content"]["rubric"]["auto_total"] == {"met": 15, "unmet": 1, "no_record": 4}


async def test_usage_recorded_with_draft(api, fake_api):
    worker, _, _, _ = make_worker(api, InMemorySaver())
    await worker.handle(
        "report.generate", {"session_id": fake_api.session_id, "attempt": 1}, worker.generate
    )
    usage = fake_api.posts("/report/draft")[0]["usage"]
    assert usage["model"] == "gpt-4o-mini"
    assert (usage["llm_calls"], usage["tokens_in"], usage["tokens_out"]) == (0, 0, 0)
