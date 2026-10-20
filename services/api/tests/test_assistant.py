"""완료 기준(agent-assistant): 공개 문서만 인용(미공개 문서 질문 → 고정 문장, grounding g09), 인용
doc_id ⊂ 이번 검색 결과, guard 치환, LLM 실패 폴백, ASSISTANT_RUNNER=graph 연결(POST assistant →
assistant_calls.cited_doc_ids).

rag-mcp는 인메모리 대역(FakeRag: 공개 문서만 돌려주는 글자 2-gram 검색), LLM은 FakeLLM이다.
체크포인터는 이 실행의 임시 DB에 둔다.
"""

import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import tiktoken
import yaml
from app.agent.assistant import AssistantGraphRunner
from app.agent.assistant.graph import FALLBACK_TEXT
from app.agent.llm import FakeLLM, OpenAILLM
from app.agent.mcp_client import fail, ok
from app.config import get_settings
from app.models import AssistantCall
from app.services.context import build_context
from app.services.scenario import build_scenario
from sqlalchemy import select

from tests.conftest import ALL_FIVE, SCENARIOS
from tests.routers.support import bearer, build_clients

PROMPTS = Path(SCENARIOS) / "missions" / "planning" / "prompts"
GROUNDING = {
    c["id"]: c
    for c in yaml.safe_load((PROMPTS / "fixtures" / "grounding.yaml").read_text())["cases"]
}
SCENARIO, _ = build_scenario(SCENARIOS, ALL_FIVE, 120)
ALL_DOCS = [d["doc_id"] for d in SCENARIO["documents"]]


def _bigrams(text: str) -> set[str]:
    compact = "".join(text.split())
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


class FakeRag:
    """search_documents·get_document 대역. 공개 문서(released)만 돌려주고 미공개는 not_released."""

    def __init__(self, released: list[str]) -> None:
        self.released = set(released)
        self.calls: list[tuple[str, dict]] = []
        self.searched: set[str] = set()  # search_documents가 돌려준 doc_id 누적
        self.searchable: set[str] | None = None  # 지정하면 검색이 이 문서만 돌려준다

    async def call(self, name: str, args: dict | None = None) -> dict:
        args = dict(args or {})
        self.calls.append((name, args))
        docs = {d["doc_id"]: d for d in SCENARIO["documents"]}
        if name == "get_document":
            doc = docs.get(args["doc_id"])
            if doc is None:
                return fail("not_found", "no such document")
            if doc["doc_id"] not in self.released:
                return fail("not_released", "not released")
            return ok({"doc_id": doc["doc_id"], "title": doc["title"], "content": doc["content"]})
        query = _bigrams(args["query"])
        chunks = [
            (len(query & _bigrams(doc["content"][i : i + 400])), doc, doc["content"][i : i + 400])
            for doc in docs.values()
            if doc["doc_id"] in self.released
            and (self.searchable is None or doc["doc_id"] in self.searchable)
            for i in range(0, len(doc["content"]), 400)
        ]
        chunks.sort(key=lambda c: -c[0])
        top = chunks[: args.get("top_k", 3)]
        self.searched |= {d["doc_id"] for _, d, _ in top}
        return ok(
            [
                {"doc_id": d["doc_id"], "title": d["title"], "chunk": text, "score": score}
                for score, d, text in top
            ]
        )


def make_runner(llm, rag: FakeRag, database_url: str) -> AssistantGraphRunner:
    @asynccontextmanager
    async def open_rag(session_id):
        yield rag

    async def scenario(session_id):
        return SCENARIO

    return AssistantGraphRunner(llm=llm, rag=open_rag, scenario=scenario, database_url=database_url)


@pytest.fixture
async def graph_runner(database_url):
    """(runner, llm, rag). 인터뷰 요약을 뺀 4개 문서가 공개된 상태."""
    llm = FakeLLM()
    rag = FakeRag([d for d in ALL_DOCS if d != "interview_summary"])
    runner = make_runner(llm, rag, database_url)
    await runner.graph()
    yield runner, llm, rag
    await runner.aclose()


async def test_unreleased_document_question_gets_fixed_sentence(graph_runner):
    runner, llm, rag = graph_runner
    case = GROUNDING["g09_assistant_not_released"]
    rag.released = set(case["released"])

    result = await runner.answer(uuid.uuid4(), case["question"], uuid.uuid4())

    assert re.search(case["expected_fact"], result.content)
    assert result.cited_docs == case["expected_citation"] == []
    assert {name for name, _ in rag.calls} >= set(case["expected_tools"])
    assert llm.calls == []  # 미공개 문서 내용을 짐작할 기회를 주지 않는다


async def test_cited_docs_stay_within_search_results(graph_runner):
    runner, llm, rag = graph_runner
    llm.script = [
        "두 번째 모임 참여율은 22%입니다 [지표 현황]. 첫 참여자는 어색함을 말했어요 "
        "[사용자 인터뷰 요약].\n출처: 지표 현황, 사용자 인터뷰 요약",
        "네, 앞의 내용을 두 줄로 줄였어요.",
    ]
    session_id = uuid.uuid4()

    prompt = "첫 참여 후 재참여율 지표가 몇 %야? 답은 me@example.com 으로"
    result = await runner.answer(session_id, prompt, uuid.uuid4())

    assert result.cited_docs == ["metrics"] and set(result.cited_docs) <= rag.searched
    assert "[사용자 인터뷰 요약]" not in result.content
    assert result.content.endswith("\n출처: 지표 현황")
    # 컨텍스트에는 공개 문서 청크만 들어간다
    interview = next(d for d in SCENARIO["documents"] if d["doc_id"] == "interview_summary")
    assert interview["content"][:40] not in llm.calls[0].text
    assert "me@example.com" not in llm.calls[0].text  # 질문은 마스킹 뒤 LLM·검색에 들어간다
    assert all("me@example.com" not in args.get("query", "") for _, args in rag.calls)
    # 같은 thread의 다음 호출은 자기 대화를 이어 본다
    await runner.answer(session_id, "두 줄로 줄여줘", uuid.uuid4())
    assert "첫 참여 후 재참여율 지표가 몇 %야?" in llm.calls[1].text
    assert "me@example.com" not in llm.calls[1].text


async def test_citations_allow_searched_or_fetched_docs_only(graph_runner):
    """인용 허용 집합 = 검색 결과 ∪ get_document로 읽은 공개 문서. 도구는 검색 포함 3회까지."""
    runner, llm, rag = graph_runner
    rag.searchable = {"metrics"}
    llm.script = [
        "참여율은 22%입니다 [지표 현황]. 위치는 동네 단위만 보여요 [운영 정책]. "
        "회의록 이야기는 하지 않을게요. 소개는 이렇습니다 [회사·서비스 소개].\n"
        "출처: 지표 현황, 운영 정책, 지난주 회의록, 회사·서비스 소개"
    ]
    prompt = "운영 정책, 회사 소개, 회의록 기준으로 지표를 정리해줘"

    result = await runner.answer(uuid.uuid4(), prompt, uuid.uuid4())

    names = [name for name, _ in rag.calls]
    assert names == ["search_documents", "get_document", "get_document"]
    fetched = {args["doc_id"] for name, args in rag.calls if name == "get_document"}
    assert fetched == {"company_intro", "policy"}
    assert result.cited_docs == ["company_intro", "metrics", "policy"]
    assert "지난주 회의록" not in result.content  # 허용 집합 밖 출처는 지운다
    assert result.content.endswith("\n출처: 회사·서비스 소개, 지표 현황, 운영 정책")


async def test_guard_replaces_verdict_sentences(graph_runner):
    runner, llm, _ = graph_runner
    notice = yaml.safe_load((PROMPTS / "guard_patterns.yaml").read_text())["notices"]["evaluation"]
    llm.script = ["문제 정의를 먼저 쓰면 좋아요. 이렇게 하시면 합격이에요."]

    result = await runner.answer(uuid.uuid4(), "기획안 순서 추천해줘", uuid.uuid4())

    assert "합격" not in result.content
    assert result.content == f"문제 정의를 먼저 쓰면 좋아요. {notice}"


async def test_model_input_stays_within_token_budget(graph_runner):
    """system·검색 결과·질문·history 합계가 gpt-4o-mini 인코딩으로 6k 토큰 이내(2토큰 한글 포함)."""
    runner, llm, _ = graph_runner
    encoding = tiktoken.encoding_for_model("gpt-4o-mini")
    session_id = uuid.uuid4()

    for _ in range(4):
        result = await runner.answer(session_id, "힣" * 2000, uuid.uuid4())

    for call in llm.calls:
        body = sum(len(encoding.encode(str(m.content))) for m in call.messages)
        assert body + 4 * len(call.messages) + 3 <= 6000
    assert "힣" * 500 in llm.calls[-1].messages[-1].content  # 질문 앞부분은 남는다
    assert result.content.startswith("질문이 길어서 앞부분까지만 보고 답했어요.")


async def test_llm_failure_falls_back_without_citation(graph_runner):
    runner, llm, _ = graph_runner
    llm.script = [RuntimeError("boom")] * 3

    result = await runner.answer(uuid.uuid4(), "지표 현황 요약해줘", uuid.uuid4())

    assert (result.content, result.cited_docs) == (FALLBACK_TEXT, [])
    assert result.usage["retries"] == 2 and result.usage["fallback_used"] is True


async def test_assistant_endpoint_uses_graph_runner(monkeypatch, database_url, db):
    monkeypatch.setenv("ASSISTANT_RUNNER", "graph")
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        ctx = build_context()
    finally:
        get_settings.cache_clear()
    assert isinstance(ctx.assistant, AssistantGraphRunner)
    llm = FakeLLM(["재참여율은 22%예요 [지표 현황].\n출처: 지표 현황"])
    ctx.assistant.llm = llm
    public, internal = build_clients(ctx)
    try:
        sid, auth = await _start_session(public)
        listed = (await internal.get(f"/internal/sessions/{sid}/documents")).json()
        rag = FakeRag([d["doc_id"] for d in listed["documents"] if d["released"]])

        @asynccontextmanager
        async def open_rag(session_id):
            yield rag

        ctx.assistant.rag = open_rag
        await ctx.assistant.graph()

        res = await public.post(
            f"/sessions/{sid}/assistant", json={"prompt": "재참여율 지표 알려줘"}, headers=auth
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["content"] == "재참여율은 22%예요 [지표 현황].\n출처: 지표 현황"
        assert body["cited_docs"] == ["metrics"]
        call = await db.scalar(select(AssistantCall).where(AssistantCall.session_id == sid))
        assert call.cited_doc_ids == ["metrics"]
        assert "interview_summary" not in rag.released  # 시작 시점에는 인터뷰 요약이 미공개
    finally:
        await public.aclose()
        await internal.aclose()
        await ctx.assistant.aclose()
        await ctx.engine.dispose()


async def _start_session(api) -> tuple[uuid.UUID, dict[str, str]]:
    """회원가입 → 채용 건 → 초대 → 입장·동의·시작."""
    signup = await api.post(
        "/admin/auth/signup",
        json={"email": "assist@example.com", "password": "pw-12345", "company_name": "회사"},
    )
    admin = bearer(signup.json()["token"])
    position = await api.post(
        "/admin/positions", json={"name": "프로덕트 기획", "elements": ALL_FIVE}, headers=admin
    )
    row = (
        await api.post(
            f"/admin/positions/{position.json()['id']}/invites",
            json={"alias": "지원자A", "email": "cand@example.com"},
            headers=admin,
        )
    ).json()
    token = row["invite_url"].rsplit("/", 1)[-1]
    consent = (await api.post(f"/s/{token}/consent")).json()
    auth = bearer(consent["session_token"])
    started = await api.post(f"/s/{token}/start", headers=auth)
    assert started.status_code == 200, started.text
    return uuid.UUID(row["session_id"]), auth


@pytest.mark.live
async def test_live_assistant_grounded_answer(graph_runner):
    """실제 gpt-4o-mini 1회(g06). 공개 문서 인용과 핵심 사실을 확인한다."""
    runner, _, rag = graph_runner
    settings = get_settings()
    assert settings.openai_api_key, "OPENAI_API_KEY가 infra/.env에 필요하다"
    runner.llm = OpenAILLM(settings.openai_api_key, settings.openai_model)
    rag.released = set(ALL_DOCS)
    case = GROUNDING["g06_main_users"]

    result = await runner.answer(uuid.uuid4(), case["question"], uuid.uuid4())

    print(result.content, result.cited_docs, result.usage)
    assert re.search(case["expected_fact"], result.content)
    assert set(result.cited_docs) <= set(case["allowed_docs"])
    assert all(t in result.content for t in case["expected_citation"])
