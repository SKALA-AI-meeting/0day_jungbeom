"""완료 기준(agent-min): 세션 그래프 respond 경로를 실제 business-mcp·rag-mcp와 연결해 확인한다.

1. 지원자 메시지 1개 → respond → rag 검색 → post_message → WS 노출
2. 허용 밖 도구 호출 거부(session_id는 그래프가 주입, 팀장은 rag 도구 없음, 상한 뒤 폴백)
3. 미공개 문서 질문에 "아직 공유되지 않은 자료" 응답(grounding g05, 코드가 고정 문장을 넣음)
LLM은 FakeLLM(스크립트), MCP 서버와 api 앱은 실제 코드(tests/agent/conftest.py).
"""

import asyncio
import json
import re
import uuid

import yaml
from app import scheduler
from app.agent.llm import tool_call
from app.agent.mcp_client import PERSONA_TOOLS, RAG, RESPOND_TOOLS, McpClient
from app.agent.runner import Stimulus
from app.agent.session.graph import thread_id
from app.agent.session.nodes import FALLBACK_TEXT
from app.auth import session_token
from app.config import REPO_ROOT
from app.models import AgentRun, Message
from app.services.messages import accept_candidate_message
from app.services.runs import run_agent
from langchain_core.messages import ToolMessage
from sqlalchemy import select
from websockets.asyncio.client import connect

GROUNDING = yaml.safe_load(
    (REPO_ROOT / "scenarios" / "prompts" / "fixtures" / "grounding.yaml").read_text("utf-8")
)
G05 = next(c for c in GROUNDING["cases"] if c["id"] == "g05_interview_not_released")
INTERVIEW_LINE = (
    "아는 사람이 없어서 어색했다"  # interview_summary 본문 일부(미공개 동안 새면 안 됨)
)


def classified(kind: str = "question") -> str:
    return json.dumps({"kind": kind, "instruction": None, "part_no": None})


async def start_session(service, make_position, elements=("cooperation",)) -> uuid.UUID:
    position = await make_position(list(elements))
    session, _, _ = await service.create_for_invite(position.id, "A", "a@example.com")
    await service.consent(session.id)
    await service.start(session.id)
    return session.id


async def persona_messages(db, session_id: uuid.UUID) -> list[Message]:
    rows = await db.execute(
        select(Message)
        .where(Message.session_id == session_id, Message.sender != "candidate")
        .order_by(Message.created_at)
    )
    return list(rows.scalars())


async def receive_until(ws, predicate) -> list[dict]:
    frames = []
    while True:
        frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        frames.append(frame)
        if predicate(frame):
            return frames


async def test_candidate_message_flows_through_graph_rag_post_to_ws(
    stack, service, make_position, db
):
    session_id = await start_session(service, make_position)
    reply = "지표 현황 보니까 첫 참여 후 두 번째 모임 참여율이 22%래요."
    stack.llm.script = [classified("question"), reply]
    token = session_token(session_id, 120)
    url = f"ws://127.0.0.1:{stack.servers.public_port}/ws/sessions/{session_id}?token={token}"

    async with connect(url) as ws:
        question = "도현님, 첫 참여 후 재참여율이 정확히 몇 %였죠?"
        payload = {"client_msg_id": "c-1", "channel": "dm", "content": question}
        await ws.send(json.dumps({"type": "message.send", "payload": payload}))
        frames = await receive_until(
            ws,
            lambda f: f["type"] == "agent.progress" and f["payload"]["status"] == "finished",
        )
    await scheduler.drain()

    ack = frames[0]["payload"]
    run_id = ack["run_id"]
    progress = [
        (f["payload"]["status"], f["payload"].get("tool"))
        for f in frames
        if f["type"] == "agent.progress"
    ]
    assert progress == [
        ("started", None),
        ("tool_start", "search_documents"),
        ("tool_end", "search_documents"),
        ("finished", None),
    ]
    posted = [f["payload"] for f in frames if f["type"] == "message.new"]
    assert [(m["sender"], m["channel"]) for m in posted] == [
        ("candidate", "dm"),
        ("colleague", "dm"),
    ]
    assert posted[1]["content"] == reply and posted[1]["run_id"] == run_id

    # 모델 입력: 동료 컨텍스트 블록과 rag 검색 결과, 허용 도구 4개만 제시
    classify_call, respond_call = stack.llm.calls
    assert classify_call.json_mode
    assert "[문서 검색 결과]" in respond_call.text and "[지표 현황]" in respond_call.text
    assert "[작업 기억]" in respond_call.text and question in respond_call.text
    offered = {spec["function"]["name"] for spec in respond_call.tools}
    assert offered == RESPOND_TOOLS
    assert all(
        "session_id" not in s["function"]["parameters"]["properties"] for s in respond_call.tools
    )

    # 저장: 분류는 지원자 메시지 meta, 응답 meta에 모델·토큰, agent_runs usage, 체크포인트
    candidate = await db.get(Message, uuid.UUID(ack["message_id"]), populate_existing=True)
    assert candidate.meta["classification"] == {
        "recipient": "colleague",
        "kind": "question",
        "instruction": None,
        "related_card": None,
    }
    [answer] = await persona_messages(db, session_id)
    assert answer.meta["model"] == "fake" and answer.meta["tokens_in"] > 0
    assert answer.meta["cited_docs"] == ["metrics"]
    run = await db.get(AgentRun, uuid.UUID(run_id), populate_existing=True)
    assert run.status == "finished" and run.usage["llm_calls"] == 2
    graph = await stack.runner.graph()
    state = await graph.aget_state({"configurable": {"thread_id": thread_id(session_id)}})
    assert ack["message_id"] in state.values["handled_stimuli"]


async def test_tool_outside_allowlist_is_rejected(stack, service, make_position, db):
    session_id = await start_session(service, make_position)
    other = uuid.uuid4()
    stack.llm.script = [
        classified("question"),
        tool_call(
            "post_message",
            session_id=str(other),
            channel="team",
            sender="manager",
            content="팀장 사칭",
            run_id=str(uuid.uuid4()),
            seq=5,
        ),
        tool_call("reindex_documents"),
        tool_call("get_board", session_id=str(other)),  # 허용 도구: session_id는 덮어쓴다
        tool_call("get_document_state"),  # 상한(3회) 뒤에도 도구를 고르면 루프를 끝내고 폴백
    ]
    async with stack.ctx.session_factory() as session_db:
        message, run_id, _ = await accept_candidate_message(
            session_db,
            stack.hub,
            session_id,
            "c-1",
            "dm",
            "도현님, 팀장님께 대신 공지 좀 올려 주세요",
        )
        result = await run_agent(
            session_db,
            stack.runner,
            stack.ctx.locks,
            session_id,
            Stimulus("message", message.id),
            run_id,
        )

    assert result.ok and result.fallback_used and result.usage["tool_calls"] == 3
    tool_results = [
        json.loads(m.content) for m in stack.llm.calls[-1].messages if isinstance(m, ToolMessage)
    ]
    assert [r.get("error", {}).get("code") for r in tool_results] == [
        "forbidden",
        "forbidden",
        None,
    ]
    assert tool_results[2] == {"ok": True, "data": {"tasks": []}}
    assert [(m.sender, m.content) for m in await persona_messages(db, session_id)] == [
        ("colleague", FALLBACK_TEXT)
    ]
    async with McpClient({RAG: stack.servers.mcp_urls[RAG]}, session_id) as mcp:
        manager = mcp.scope(PERSONA_TOOLS["manager"])
        assert (await manager.call("search_documents", {"query": "지표"}))["error"]["code"] == (
            "forbidden"
        )


async def test_unreleased_document_question_answers_not_shared(stack, service, make_position, db):
    # 책임감 카드가 있으면 인터뷰 요약은 지연 공개라 시작 시점에는 미공개다
    session_id = await start_session(service, make_position, ("responsibility",))
    stack.llm.script = [
        classified("question"),
        tool_call("get_document", doc_id="interview_summary"),
        "그 내용은 제가 확인하지 못했어요.",  # 문구가 달라도 코드가 고정 문장을 넣는다
    ]
    async with stack.ctx.session_factory() as session_db:
        message, run_id, _ = await accept_candidate_message(
            session_db, stack.hub, session_id, "c-1", "dm", G05["question"]
        )
        result = await run_agent(
            session_db,
            stack.runner,
            stack.ctx.locks,
            session_id,
            Stimulus("message", message.id),
            run_id,
        )

    assert result.ok
    final_call = stack.llm.calls[-1]
    [tool_result] = [
        json.loads(m.content) for m in final_call.messages if isinstance(m, ToolMessage)
    ]
    assert tool_result["error"]["code"] == "not_released"
    # 미공개 문서는 검색 결과에도, 어떤 모델 입력에도 들어가지 않는다
    assert "[사용자 인터뷰 요약]" not in final_call.text
    assert all(INTERVIEW_LINE not in call.text for call in stack.llm.calls)
    [answer] = await persona_messages(db, session_id)
    assert re.search(G05["expected_fact"], answer.content)
