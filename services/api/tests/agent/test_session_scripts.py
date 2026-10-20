"""완료 기준(M2): 6분 세션 + 대본 3개(all_five·early_submit·division_refuse)를 실제 세션 그래프로
돈다.

검증 방식: FakeLLM(tests/agent/brain.py) + 격리 DB(임시 DB) + 실제 business-mcp·rag-mcp 하위
프로세스.
시계는 세션 시각 열을 당겨 앞으로 보낸다(script_driver). 대본의 지원자 발화마다 분류 결과(모의 LLM
출력)를 아래 표로 정하고, 관찰 레이블은 대본 expect.labels를 모의 LLM이 낸다. 그래서 이 테스트가
보는 것은 레이블의 정확도가 아니라 그래프·관찰·지표·평가표 입력이 기록대로 만들어지는가다.

- 카드 전부 정시(fired−due ≤ 10초), 행마다 자기 event_id 메시지
- all_five: 보드만으로 분업(set_division 없이 doing), 카드 전 계획, 작업 기억(v1 "재참여", v2 "후속
  모임"·"이번 분기", 같이 파트 골격, 답글 뒤 v3, 진행 질문 2회 같은 답, 보드 doing→done), 반대 의견
  대상(보낸 1번 문서의 문장, 의견은 카탈로그 고정 문장), 창 밖 약속 이행(종료 PATCH), 보고 뒤 제출
  즉시
  completed, 관찰 7장이 평가표(워커 rubric)에서 전부 충족, LangSmith 메타데이터의 run_id
- early_submit: 보고 요청 전 제출 → 보고 요청 즉시 실행 → reporting·resume → 팀장 DM 보고 →
completed
- division_refuse: 분업 최소 조건 위반 1회 되돌림 → 확정, 보고 없이 제출+5분 상한에 completed
"""

import re
import sys
from datetime import timedelta
from pathlib import Path

from app.models import (
    AgentRun,
    Document,
    DocumentVersion,
    Invite,
    Message,
    Observation,
    Position,
    Session,
    SessionEvent,
    Task,
    TaskEvent,
)
from sqlalchemy import select

from tests.agent.brain import Brain, cls, instr
from tests.agent.script_driver import load_script, start

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "report-worker"))
from report_worker import rubric  # noqa: E402

ON_TIME_SECONDS = 10
DELIVERY_SECONDS = 90


async def rows(db, model, *where, order=None):
    query = select(model).where(*where).execution_options(populate_existing=True)
    if order is not None:
        query = query.order_by(order)
    return list((await db.execute(query)).scalars())


async def assert_cards_on_time(db, session_id, skip=()):
    events = await rows(db, SessionEvent, SessionEvent.session_id == session_id)
    first_message = {}
    for m in await rows(db, Message, Message.session_id == session_id, order=Message.created_at):
        if m.event_id is not None:
            first_message.setdefault(m.event_id, m.created_at)
    posted = set(first_message)
    for event in events:
        if event.card_id in skip:
            continue
        assert event.status == "done", (event.card_id, event.status)
        assert event.id in posted, event.card_id
        lag = (event.fired_at - event.due_at).total_seconds()
        assert 0 <= lag <= ON_TIME_SECONDS, (event.card_id, lag)
        # 시점 합격 기준(testing.md): fired→done 10초, fired→카드 메시지 90초
        done = (event.done_at - event.fired_at).total_seconds()
        assert 0 <= done <= ON_TIME_SECONDS, (event.card_id, done)
        delivered = (first_message[event.id] - event.fired_at).total_seconds()
        assert 0 <= delivered <= DELIVERY_SECONDS, (event.card_id, delivered)
    return {e.card_id: e for e in events}


def promised(human: str) -> dict:
    card_t = float(re.search(r"카드 메시지 시각: ([\d.]+)", human).group(1))
    return {"label": "negotiate_timing", "aux": {"promised_t_min": card_t + 1, "is_specific": True}}


ALL_FIVE_CLASSIFY = {
    "안녕하세요, 오늘 합류한 기획자입니다. 주담당 맡아서 잘 정리해 보겠습니다.": cls("other"),
    "보드에 적어 뒀어요. 1번 먼저 끝내고 2번은 인터뷰 받는 대로, 3번은 같이, 4·5번은 도현님이 맡아 "
    "주세요. 4번 사례는 재참여 기능이 있는 서비스 위주로 봐 주세요.": cls(
        "redivide",
        decision="decide",
        parts={"1": "candidate", "2": "candidate", "3": "both", "4": "colleague", "5": "colleague"},
        instructions=[instr(4, "4번 사례는 재참여 기능이 있는 서비스 위주로", "재참여")],
        related_card="planning_division",
    ),
    "지금 1번 정리 중이라 1분 뒤에 DM 드릴게요.": cls("other", related_card="collab_help"),
    "도현님, 4번은 지금 어디까지 됐어요?": cls("progress_query", part_no=4),
    "아 그리고 4번 진행 상황 한 번만 더 알려 주세요.": cls("progress_query", part_no=4),
    "도현님, 4번 기준 지금 같이 봐요. 재참여 기능이 있는 서비스 두세 개로 좁혀 볼까요?": cls(
        "instruction",
        instructions=[instr(4, "재참여 기능이 있는 서비스 두세 개로 좁힌다", "재참여")],
        related_card="collab_help",
    ),
    "사례 2는 후속 모임 기능이 약해 보여서 다른 걸로 바꾸면 좋겠어요.": cls(
        "doc_feedback", part_no=4, wants_revision=True, related_card="planning_checkin"
    ),
    "2번 자료는 인터뷰 요약 오면 바로 정리해서 보내 드릴게요.": cls(
        "other", related_card="planning_checkin"
    ),
    "인터뷰 자료 공개가 늦어진대요. 2번이 밀려서 도현님 3번도 영향이 있을 것 같아요. 그동안 1번 "
    "문제 정의를 먼저 끝내 둘게요.": cls("other", related_card="responsibility_delay"),
    "도현님, 3번은 첫 모임 뒤 48시간 안 후속 모임 제안 하나로 좁히고, 5번 출시는 이번 분기로 바꿔 "
    "주세요.": cls(
        "instruction",
        instructions=[
            instr(3, "3번은 첫 모임 뒤 48시간 안 후속 모임 제안 하나로", "후속 모임"),
            instr(5, "5번 출시는 이번 분기로", "이번 분기"),
        ],
        related_card="adaptability_change",
    ),
    "4번 사례 하나는 후속 모임 제안 기능이 있는 서비스로 바꿔 주세요.": cls(
        "doc_feedback", part_no=4, wants_revision=True
    ),
    "말씀 일리 있어요. 다만 2·8번처럼 일정을 놓친 경우는 후속 모임 알림으로 바로 풀 수 있어서 "
    "일정을 주원인으로 두고, 관계는 보조 원인으로 적을게요.": cls(
        "other", related_card="collab_disagree"
    ),
    "1·2번은 제가 썼고, 3번은 도현님 골격에 제가 보탰고, 4·5번은 도현님이 썼습니다. 5번 일정은 "
    "아직 초안 수준이에요.": cls("report", related_card="honesty_report"),
}

ALL_FIVE_LABELS = {
    "planning_division": {"label": "assign_with_schedule", "aux": {"mentions_schedule": True}},
    "collab_help": promised,
    "planning_checkin": {"label": "feedback"},
    "responsibility_delay": {
        "label": "notify_with_alternative",
        "aux": {"mentions_impact": True, "has_alternative": True},
    },
    "adaptability_change": {
        "label": "replan_and_apply",
        "aux": {"target_applied": True, "mentions_scope": True},
    },
    "collab_disagree": {"label": "explain_with_reason"},
    "honesty_report": {
        "label": "fair_report",
        "aux": {
            "credits_colleague": True,
            "claims_colleague_work": False,
            "discloses_incomplete": True,
        },
    },
}


async def colleague_versions(db, session_id) -> dict[int, list[str]]:
    docs = await rows(
        db, Document, Document.session_id == session_id, Document.owner == "colleague"
    )
    out = {}
    for doc in docs:
        versions = await rows(
            db, DocumentVersion, DocumentVersion.doc_id == doc.id, order=DocumentVersion.version
        )
        out[doc.part_no] = [v.content for v in versions]
    return out


async def test_all_five_script(stack, service, make_position, db):
    script = load_script("all_five")
    brain = Brain(ALL_FIVE_CLASSIFY, ALL_FIVE_LABELS)
    stack.llm.default = brain
    driver = await start(stack, service, make_position, script["elements"], script["minutes"])
    await driver.run(script["steps"])
    sid = driver.session_id

    session = await db.get(Session, sid, populate_existing=True)
    assert session.status == "completed" and session.completed_at == session.reported_at
    events = await assert_cards_on_time(db, sid)

    # 보드만으로 분업 확정: division 자극은 set_division 없이 작업 기억·보드 doing
    assert session.division["decided_by"] == "candidate"
    by_colleague = await rows(
        db,
        TaskEvent,
        TaskEvent.session_id == sid,
        TaskEvent.by == "colleague",
        order=TaskEvent.created_at,
    )
    assert not [e for e in by_colleague if e.field == "assignee"]
    statuses = [(e.part_no, e.new_value) for e in by_colleague if e.field == "status"]
    assert statuses == [
        (3, "doing"),
        (4, "doing"),
        (5, "doing"),
        (3, "done"),
        (4, "done"),
        (5, "done"),
    ]
    tasks = {t.part_no: t.status for t in await rows(db, Task, Task.session_id == sid)}
    assert [tasks[p] for p in (3, 4, 5)] == ["done", "done", "done"]

    # 작업 기억: v1에 그 전 지시, v2에 적응성 뒤 지시, 같이 파트 골격, 답글 뒤 v3
    versions = await colleague_versions(db, sid)
    assert sorted(versions) == [3, 4, 5]
    assert len(versions[3]) == 2 and len(versions[5]) == 2 and len(versions[4]) == 3
    assert "재참여" in versions[4][0]
    assert "후속모임" in versions[3][1].replace(" ", "") and "이번분기" in versions[5][1].replace(
        " ", ""
    )
    assert "재참여" in versions[4][1]
    drafts = [human for kind, human in brain.calls if kind == "draft"]
    assert any("3번 핵심 기능 제안 v1 골격" in h for h in drafts)
    # 진행 질문 2회에 같은 답
    persona = await rows(db, Message, Message.session_id == sid, Message.sender == "colleague")
    answers = [m.content for m in persona if (m.meta or {}).get("node") == "respond"]
    progress = [a for a in answers if a.startswith("지금 4번은")]
    assert len(progress) == 2 and progress[0] == progress[1]

    # 반대 의견: 보낸 1번 문서의 원인 가정 문장을 가리키고 의견 본문은 카탈로그 고정 문장
    card = next(
        c for c in (await stack_scenario(db, sid))["cards"] if c["card_id"] == "collab_disagree"
    )
    [disagree] = [m for m in persona if m.event_id == events["collab_disagree"].id]
    assert "주원인 가정: 다음 모임 일정을 놓쳐서." in disagree.content
    assert disagree.content.endswith(card["fixed_opinions"][0]["opinion"].strip())
    assert "보내" not in disagree.content.split("1번에")[0]

    # 관찰 7장: 키(card_id, window_start), 근거 타입, 창 밖 약속 이행(종료 PATCH), 평가표 전부 충족
    observations = {
        o.card_id: o for o in await rows(db, Observation, Observation.session_id == sid)
    }
    assert set(observations) == set(ALL_FIVE_LABELS)
    starts = {
        c: round((o.window_start - session.started_at).total_seconds() / 60, 2)
        for c, o in observations.items()
    }
    assert starts["planning_division"] == 0.0 and starts["collab_help"] == 1.5
    for card_id, types in script["expect"]["evidence_types"].items():
        found = {e["type"] for e in observations[card_id].evidence}
        assert set(types) <= found, (card_id, found)
    help_obs = observations["collab_help"]
    assert help_obs.metrics["promise_kept"]["value"] is True and help_obs.updated_run_id is not None
    kept = await db.get(Message, help_obs.metrics["promise_kept"]["evidence_ids"][0])
    assert kept.content.startswith("도현님, 4번 기준 지금 같이 봐요")
    scenario = await stack_scenario(db, sid)
    cards = {c["card_id"]: c for c in scenario["cards"]}
    for element, expected in script["expect"]["rubric"].items():
        values = []
        for card_id, obs in observations.items():
            if cards[card_id]["element"] != element:
                continue
            row = {
                "label": obs.label,
                "metrics": obs.metrics,
                "aux": obs.aux,
                "evidence": obs.evidence,
            }
            values += [item["auto"] for item in rubric.evaluate(cards[card_id], row)]
        assert rubric.tally(values) == expected, (element, values)

    # LangSmith: LLM 호출마다 이 실행의 run_id가 메타데이터·태그에 붙는다
    run = await rows(db, AgentRun, AgentRun.session_id == sid, AgentRun.stimulus == "event")
    run_ids = {str(r.run_id) for r in run}
    traced = {c.config["metadata"]["run_id"] for c in stack.llm.calls}
    assert run_ids <= traced
    assert all(
        f"run_id:{c.config['metadata']['run_id']}" in c.config["tags"] for c in stack.llm.calls
    )


async def stack_scenario(db, session_id):
    return await db.scalar(
        select(Position.scenario)
        .join(Invite, Invite.position_id == Position.id)
        .join(Session, Session.invite_id == Invite.id)
        .where(Session.id == session_id)
    )


EARLY_CLASSIFY = {
    "1·2번은 제가, 3번은 같이, 4·5번은 도현님이 맡아 주세요.": cls(
        "redivide",
        decision="decide",
        parts={"1": "candidate", "2": "candidate", "3": "both", "4": "colleague", "5": "colleague"},
    ),
    "4·5번은 도현님이 썼고, 1~3번은 아직 비어 있어요.": cls(
        "report", related_card="honesty_report"
    ),
}


async def test_early_submit_script(stack, service, make_position, db):
    script = load_script("early_submit")
    stack.llm.default = Brain(
        EARLY_CLASSIFY,
        {
            "honesty_report": {
                "label": "fair_report",
                "aux": {
                    "credits_colleague": True,
                    "claims_colleague_work": False,
                    "discloses_incomplete": True,
                },
            }
        },
    )
    driver = await start(stack, service, make_position, script["elements"], script["minutes"])
    await driver.run(script["steps"])
    sid = driver.session_id

    session = await db.get(Session, sid, populate_existing=True)
    log = [entry for _, entry in driver.log]
    assert "submit:reporting" in log and "resume:reporting" in log
    assert session.status == "completed" and session.completed_at == session.reported_at
    events = await assert_cards_on_time(db, sid, skip=("honesty_report",))
    report = events["honesty_report"]
    # 제출로 당겨진 보고 요청이 제출 시각에 바로 실행됐다
    assert report.status == "done" and report.due_at == session.submitted_at
    assert session.submitted_at < session.started_at + timedelta(minutes=5.5)
    [obs] = await rows(db, Observation, Observation.session_id == sid)
    assert obs.card_id == "honesty_report" and obs.label == "fair_report"
    assert obs.window_end == session.completed_at
    assert obs.metrics["has_report_message"]["value"] is True
    assert obs.facts["empty_sections"] == [1, 2, 3]


REFUSE_CLASSIFY = {
    "안녕하세요.": cls("other"),
    "2번 인터뷰 근거는 도현님이 하고 1·3·4·5번은 제가 할게요.": cls(
        "redivide",
        decision="decide",
        parts={
            "1": "candidate",
            "2": "colleague",
            "3": "candidate",
            "4": "candidate",
            "5": "candidate",
        },
        related_card="planning_division",
    ),
    "아 그렇네요. 그럼 1·2번은 제가, 3번은 같이, 4·5번은 도현님이 해 주세요.": cls(
        "redivide",
        decision="decide",
        parts={"1": "candidate", "2": "candidate", "3": "both", "4": "colleague", "5": "colleague"},
        related_card="planning_division",
    ),
    "인터뷰 자료가 늦어진대요. 먼저 할 수 있는 1번부터 진행할게요.": cls(
        "other", related_card="responsibility_delay"
    ),
    "확인했습니다.": cls("other"),
    "공유합니다.": cls("other"),
}


async def test_division_refuse_script(stack, service, make_position, db):
    script = load_script("division_refuse")
    stack.llm.default = Brain(
        REFUSE_CLASSIFY,
        {
            "planning_division": {"label": "assign_only", "aux": {"mentions_schedule": False}},
            "planning_checkin": {"label": "ignore"},
            "responsibility_delay": {
                "label": "notify_with_alternative",
                "aux": {"mentions_impact": False, "has_alternative": True},
            },
        },
    )
    driver = await start(stack, service, make_position, script["elements"], script["minutes"])
    await driver.run(script["steps"])
    sid = driver.session_id

    session = await db.get(Session, sid, populate_existing=True)
    assert session.status == "reporting" and session.reported_at is None
    await driver.advance_to(5.6 + 5.1)  # 보고 없이 제출+5분 상한
    session = await db.get(Session, sid, populate_existing=True)
    assert session.status == "completed" and session.completed_at == session.deadline_at
    await assert_cards_on_time(db, sid)

    assert session.division["decided_by"] == "candidate"
    assert session.division["parts"] == script_parts()
    replies = [
        m
        for m in await rows(
            db,
            Message,
            Message.session_id == sid,
            Message.sender == "colleague",
            order=Message.created_at,
        )
        if (m.meta or {}).get("node") == "negotiate"
    ]
    # 되돌림 1회(의존 관계 이유) → 다음 결정에 수락. 위반안은 저장되지 않았다
    assert len(replies) == 2
    assignee = await rows(db, TaskEvent, TaskEvent.session_id == sid, TaskEvent.field == "assignee")
    assert {(str(e.part_no), e.new_value) for e in assignee} == set(script_parts().items())
    observations = {
        o.card_id: o for o in await rows(db, Observation, Observation.session_id == sid)
    }
    assert observations["planning_division"].label == "assign_only"
    assert observations["planning_division"].metrics["division_by_candidate"]["value"] is True


def script_parts():
    return {"1": "candidate", "2": "candidate", "3": "both", "4": "colleague", "5": "colleague"}
