"""완료 기준(M2 컨텍스트·규칙): 근거 정확성 픽스처 10건, 팀장 DM 판단 요청에 "주담당이 정해 주세요",
보내지 않은 지원자 문서 질문에 "아직 못 봤어요", 미래 상황·알림·미공개 내용이 페르소나 입력에 없음,
선점 금지 6건(지금 열린 창의 금지와 창 안에서 해도 되는 것이 동료 입력에 들어감).

검증 방식: FakeLLM(Brain) + 격리 DB + 실제 business-mcp·rag-mcp(2-gram 임베딩). 모의 LLM이라 응답
문구 자체(의미 조건)는 보지 않고, 코드가 정하는 것(도구·검색 결과·인용 문서·고정 문장·입력 블록)을
본다.
같은 픽스처를 실제 모델로 돌리는 것은 test_live.py.
"""

import re

import yaml
from app.agent.guard import guard_for
from app.agent.mcp_client import ASSISTANT_TOOLS, MANAGER_RESPOND_TOOLS, RAG, McpClient
from app.agent.session.nodes import REDIRECT_TEXT, UNSENT_TEXT
from app.config import REPO_ROOT
from app.models import Message
from langchain_core.messages import AIMessage

from tests.agent.brain import Brain, cls
from tests.agent.script_driver import start
from tests.agent.test_session_scripts import rows, stack_scenario

FIXTURES = REPO_ROOT / "scenarios" / "missions" / "planning" / "prompts" / "fixtures"
ALL_FIVE = ["responsibility", "planning", "adaptability", "collaboration", "honesty"]
TITLES = {
    "company_intro": "회사·서비스 소개",
    "metrics": "지표 현황",
    "interview_summary": "사용자 인터뷰 요약",
    "policy": "운영 정책",
    "meeting_notes": "지난주 회의록",
}


def fixture(name: str) -> list[dict]:
    return yaml.safe_load((FIXTURES / f"{name}.yaml").read_text("utf-8"))["cases"]


async def last_reply(db, session_id) -> Message:
    replies = await rows(
        db,
        Message,
        Message.session_id == session_id,
        Message.sender.in_(("colleague", "manager")),
        order=Message.created_at,
    )
    return replies[-1]


def respond_calls(stack):
    return [c for c in stack.llm.calls if c.tools]


async def test_grounding_fixtures(stack, service, make_position, db):
    """질문별 기대 도구·허용 문서·인용 일치 10건. 동료 5건은 세션 그래프로(기대 도구 호출, 모델에 준
    검색
    결과에 허용 문서, 응답 meta의 인용 문서 = 본문 인용, 미공개는 고정 문장), 어시스턴트 5건은 그
    그래프의
    허용 도구로 rag 결과만 본다(답변 생성은 agent-assistant). 인용 문장·핵심 사실 자체는 live에서
    본다."""
    cases = fixture("grounding")
    assert len(cases) == 10
    colleague = [c for c in cases if c["persona"] == "colleague"]
    brain = Brain(
        {c["question"]: cls("question") for c in colleague},
        tools={"인터뷰 요약에 첫 참여자들이": ("get_document", {"doc_id": "interview_summary"})},
    )
    stack.llm.default = brain
    driver = await start(
        stack, service, make_position, ["responsibility"], 6
    )  # 인터뷰 요약 지연 공개
    scenario = await stack_scenario(db, driver.session_id)
    async with driver.client() as http:
        for index, case in enumerate(colleague):
            before = len(stack.llm.calls)
            await driver.say({"channel": "dm", "content": case["question"]}, f"g{index}", http)
            reply = await last_reply(db, driver.session_id)
            calls = stack.llm.calls[before:]
            first = next(c for c in calls if c.tools)
            assert "[문서 검색 결과]" in first.text  # search_documents는 코드가 먼저 부른다
            used = {"search_documents"} | {
                t["name"]
                for c in calls
                for m in c.messages
                if isinstance(m, AIMessage)
                for t in m.tool_calls
            }
            assert set(case["expected_tools"]) <= used, case["id"]
            # 모델에 준 검색 결과에 허용 문서가 있고(답할 수 있는 질문), 응답 meta의 인용 문서는
            # 본문과 같다
            titles = set(
                re.findall(
                    r"^- \[([^\]]+)\]",
                    first.text.split("[문서 검색 결과] (공개된 문서만)")[-1],
                    re.M,
                )
            )
            allowed_titles = {TITLES[d] for d in case["allowed_docs"]}
            assert (
                (titles & allowed_titles) if allowed_titles else "사용자 인터뷰 요약" not in titles
            ), (
                case["id"],
                titles,
            )
            assert reply.meta["cited_docs"] == guard_for(scenario).cited_docs(reply.content)
            if not case["allowed_docs"]:  # 미공개 문서: 코드가 고정 문장을 넣는다
                assert re.search(case["expected_fact"], reply.content), (case["id"], reply.content)
            assert "아는 사람이 없어서 어색했다" not in "".join(c.text for c in calls)

    released = {"company_intro", "metrics", "policy", "meeting_notes"}
    async with McpClient({RAG: stack.servers.mcp_urls[RAG]}, driver.session_id) as mcp:
        tools = mcp.scope(ASSISTANT_TOOLS)
        for case in (c for c in cases if c["persona"] == "assistant"):
            if "get_document" in case["expected_tools"]:
                result = await tools.call("get_document", {"doc_id": "interview_summary"})
                assert result["error"]["code"] == "not_released", case["id"]
                continue
            found = (await tools.call("search_documents", {"query": case["question"], "top_k": 3}))[
                "data"
            ]
            assert {r["doc_id"] for r in found} <= released, case["id"]  # 공개된 문서만
            allowed = set(case["allowed_docs"]) & released
            if allowed:
                assert allowed & {r["doc_id"] for r in found}, (case["id"], found)


MANAGER = {
    "md01_deadline": cls("question"),
    "md02_document_meaning": cls("question"),
    "md03_judgment_request": cls("question", judgment_request=True),
    "md04_choice_request": cls("question", judgment_request=True),
    "md05_extra_data": cls("question"),
}


async def test_manager_dm_rules(stack, service, make_position, db):
    cases = fixture("manager_dm")
    stack.llm.default = Brain({c["candidate"]["content"]: MANAGER[c["id"]] for c in cases})
    driver = await start(stack, service, make_position, ALL_FIVE, 6)
    async with driver.client() as http:
        for index, case in enumerate(cases):
            before = len(stack.llm.calls)
            await driver.say(case["candidate"], f"m{index}", http)
            reply = await last_reply(db, driver.session_id)
            assert (reply.sender, reply.channel) == ("manager", "manager_dm")
            redirected = reply.content.startswith(REDIRECT_TEXT)
            assert redirected == (case["kind"] == "redirect"), (case["id"], reply.content)
            [call] = [c for c in stack.llm.calls[before:] if c.tools]
            assert {t["function"]["name"] for t in call.tools} == MANAGER_RESPOND_TOOLS
            if case["id"] == "md02_document_meaning":
                assert "[지난주 회의록]" in call.text


async def test_context_excludes_future_notice_and_unsent(stack, service, make_position, db):
    """미래 카드·알림·보내지 않은 문서는 어느 페르소나 입력에도 없다(context_leak 4건 + notice)."""
    leak = {c["id"]: c for c in fixture("context_leak")}
    unsent = leak["unsent_document"]["candidate"]["content"]
    stack.llm.default = Brain({unsent: cls("question", asks_my_part=1)})
    driver = await start(stack, service, make_position, ALL_FIVE, 6)
    future = {  # 아직 오지 않은 카드의 내용 조각
        "responsibility_delay": "늦어집니다",
        "adaptability_change": "48시간",
        "collab_disagree": "아는 사람이 생기지 않아",
        "honesty_report": "다 됐다고 전해도",
    }

    def persona_inputs(start_index):
        return [
            "\n".join(str(m.content) for m in c.messages[1:])
            for c in stack.llm.calls[start_index:]
            if c.tools
        ]

    async with driver.client() as http:
        await driver.advance_to(1.6)
        before = len(stack.llm.calls)
        await driver.say(leak["future_next_event"]["candidate"], "f1", http)
        for text in persona_inputs(before):
            assert not any(piece in text for piece in future.values())

        await driver.advance_to(2.3)
        r = await http.put(
            f"/sessions/{driver.session_id}/my-documents/1", json={"content": "UNSENT-1번 초안"}
        )
        assert r.status_code == 200
        before = len(stack.llm.calls)
        await driver.say(leak["unsent_document"]["candidate"], "f2", http)
        assert (await last_reply(db, driver.session_id)).content.startswith(UNSENT_TEXT)
        assert all("UNSENT-1번" not in c.text for c in stack.llm.calls)

        await driver.advance_to(3.1)  # 지연 알림은 지원자에게만(notice)
        before = len(stack.llm.calls)
        await driver.say(leak["future_direction_change"]["candidate"], "f3", http)
        for text in persona_inputs(before):
            assert "48시간" not in text and "대표님" not in text and "늦어집니다" not in text

        await driver.advance_to(3.8)
        before = len(stack.llm.calls)
        await driver.say(leak["future_review_opinion"]["candidate"], "f4", http)
        for text in persona_inputs(before):
            assert future["collab_disagree"] not in text and "늦어집니다" not in text


PREEMPTION_AT = {  # 픽스처 setup의 창이 열려 있는 세션 시각(L=6, 5요소)
    "division_schedule_first": 0.6,
    "checkin_no_nagging": 2.3,
    "delay_alternative": 3.1,
    "change_redirect_first": 3.8,
    "report_direct_to_manager": 5.6,
    "ghostwrite_candidate_part": 5.7,
}


async def test_preemption_rules_reach_colleague(stack, service, make_position, db):
    cases = fixture("preemption")
    assert len(cases) == 6
    persona = yaml.safe_load(
        (REPO_ROOT / "scenarios" / "missions" / "planning" / "persona.yaml").read_text("utf-8")
    )["colleague"]
    rules = {r["window"]: r["rule"] for r in persona["must_not_preempt"]}
    classify = {c["candidate"]["content"]: cls("question") for c in cases}
    classify[cases[0]["candidate"]["content"]] = cls("other", decision="ask")
    stack.llm.default = Brain(classify)
    driver = await start(stack, service, make_position, ALL_FIVE, 6)
    async with driver.client() as http:
        for index, case in enumerate(cases):
            await driver.advance_to(PREEMPTION_AT[case["id"]])
            before = len(stack.llm.calls)
            await driver.say(case["candidate"], f"p{index}", http)
            # 이 메시지에 답한 동료 호출(분류 뒤 respond 또는 negotiate)의 입력
            text = [c.text for c in stack.llm.calls[before:] if "[지금 지킬 것]\n" in c.text][-1]
            window = case["setup"]["current_card"]
            block = text.split("[지금 지킬 것]\n")[-1].split("\n\n")[0]
            if window:
                assert rules[window] in block, case["id"]
            assert rules["any"] in block and "해도 됨" in block
            reply = await last_reply(db, driver.session_id)
            assert reply.sender == "colleague"
