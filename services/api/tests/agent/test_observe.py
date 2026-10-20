"""완료 기준(관찰): 카드 7장 픽스처로 레이블·aux·근거 타입(rubric.md 이름), 창 밖 메시지는
related_card일
때만, 정직 카드 facts 대조(동료 몫을 자기 것으로 → misattributes), 활동 없으면 no_evidence(LLM
미호출),
허용 밖 레이블 unclassified. 최소 테스트 중 카드 전 계획·무관한 편집도 여기서 본다.

검증 방식: 순수 함수 + FakeLLM(관찰 분류 응답을 스크립트로). 평가표 값은 워커 rubric(경로 import).
"""

import json
import sys
from pathlib import Path

import pytest
from app.agent import observe
from app.agent.llm import FakeLLM, Trace, Usage
from app.config import REPO_ROOT
from app.services.scenario import build_scenario

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "report-worker"))
from report_worker import rubric  # noqa: E402

SCENARIO, _ = build_scenario(
    REPO_ROOT / "scenarios",
    ["responsibility", "planning", "adaptability", "collaboration", "honesty"],
    120,
)
CARDS = {c["card_id"]: c for c in SCENARIO["cards"]}
PROMPT = SCENARIO["prompts"]["observe_labels.md"]
PARTS = {"1": "candidate", "2": "candidate", "3": "both", "4": "colleague", "5": "colleague"}


def msg(id_, t, content, channel="dm", sender="candidate", **classification):
    meta = {"classification": {"recipient": "colleague", "kind": "other", **classification}}
    return {
        "id": id_,
        "t_min": t,
        "content": content,
        "channel": channel,
        "sender": sender,
        "meta": meta,
    }


def answer(label, evidence, **aux):
    return json.dumps(
        {"label": label, "evidence": [{"type": t, "id": i} for t, i in evidence], "aux": aux}
    )


def window(card_id, start, end, card_t=None, due=None, event_ids=("ev",)):
    card = CARDS[card_id]
    return observe.Window(
        card=card,
        start=start,
        end=end,
        due=start if due is None else due,
        card_t_min=start if card_t is None else card_t,
        event_ids=list(event_ids),
    )


async def run(win, inputs, reply):
    llm = FakeLLM([reply] if reply is not None else [])
    body = await observe.observe(
        win, inputs, llm, PROMPT, usage=Usage(), trace=Trace("r", "s", "observe")
    )
    return body, llm


def values(card_id, body):
    row = {k: body[k] for k in ("label", "metrics", "aux", "evidence")}
    return [item["auto"] for item in rubric.evaluate(CARDS[card_id], row)]


FACTS = {
    "shares": [
        {"doc_id": "c4", "owner": "colleague", "part_no": 4, "versions": [{"version": 2}]},
        {"doc_id": "c5", "owner": "colleague", "part_no": 5, "versions": [{"version": 2}]},
    ],
    "final_sections": [],
    "tasks": [],
    "empty_sections": [5],
    "tasks_not_done": [],
    "changed_after_adaptability": True,
}

# 카드 7장: (창, 입력, 모의 분류 응답, 기대 레이블, 기대 근거 타입, 기대 평가표 값)
CASES = {
    "planning_division": (
        window("planning_division", 0, 30, card_t=10, due=10),
        observe.Inputs(
            messages=[
                msg("m1", 11, "1·2번 제가, 3번 같이, 4·5번 도현님. 2번은 50분까지", kind="redivide")
            ],
            task_events=[
                {
                    "id": "t1",
                    "part_no": 1,
                    "by": "candidate",
                    "field": "due_min",
                    "old_value": None,
                    "new_value": "40",
                    "t_min": 12,
                },
            ],
            division={"parts": PARTS, "decided_by": "candidate", "decided_t_min": 11.5},
        ),
        answer(
            "assign_with_schedule",
            [("message", "m1"), ("task_event", "t1")],
            mentions_schedule=True,
        ),
        "assign_with_schedule",
        {"message", "task_event"},
        [1, 1],
    ),
    "planning_checkin": (
        window("planning_checkin", 45, 60, event_ids=("ev-checkin",)),
        observe.Inputs(
            messages=[
                msg(
                    "m1",
                    47,
                    "사례 2는 후속 모임 기능이 약해 보여요",
                    channel="team",
                    related_card="planning_checkin",
                )
            ],
            shares=[
                {
                    "id": "s1",
                    "doc_id": "c4",
                    "owner": "colleague",
                    "part_no": 4,
                    "version": 1,
                    "channel": "team",
                    "event_id": "ev-checkin",
                    "t_min": 45,
                }
            ],
            opens=[{"id": "o1", "doc_id": "c4", "part_no": 4, "version": 1, "t_min": 46}],
        ),
        answer("feedback", [("open", "o1"), ("message", "m1")]),
        "feedback",
        {"open", "message"},
        [1, 1],
    ),
    "collab_help": (
        window("collab_help", 30, 45),
        observe.Inputs(
            messages=[msg("m1", 31, "10분 뒤에 같이 볼까요?", related_card="collab_help")]
        ),
        answer("negotiate_timing", [("message", "m1")], promised_t_min=41, is_specific=True),
        "negotiate_timing",
        {"message"},
        [1, None],  # 약속 이행은 종료 때 확정(창 닫힘엔 null)
    ),
    "collab_disagree": (
        window("collab_disagree", 90, 110),
        observe.Inputs(
            messages=[
                msg(
                    "m1",
                    92,
                    "일리 있어요. 다만 지표상 일정이 주원인이라 유지할게요",
                    channel="team",
                    related_card="collab_disagree",
                )
            ]
        ),
        answer("explain_with_reason", [("message", "m1")]),
        "explain_with_reason",
        {"message"},
        [1, 1],
    ),
    "responsibility_delay": (
        window("responsibility_delay", 60, 75),
        observe.Inputs(
            messages=[
                msg(
                    "m1",
                    62,
                    "인터뷰 자료가 늦어진대요. 도현님 3번도 밀려서 그동안 1번 먼저 할게요",
                    channel="team",
                    related_card="responsibility_delay",
                )
            ],
            doc_views=[{"id": "v1", "doc_id": "interview_summary", "t_min": 71}],
            division={"parts": PARTS, "decided_by": "candidate", "decided_t_min": 11},
            release_at=70,
        ),
        answer(
            "notify_with_alternative",
            [("message", "m1")],
            mentions_impact=True,
            has_alternative=True,
        ),
        "notify_with_alternative",
        {"message"},
        [1, 1, 1, 1],
    ),
    "adaptability_change": (
        window("adaptability_change", 75, 90),
        observe.Inputs(
            messages=[
                msg(
                    "m1",
                    76,
                    "도현님, 5번 출시를 이번 분기로 바꿔 주세요",
                    kind="instruction",
                    related_card="adaptability_change",
                )
            ],
            revisions=[
                {
                    "id": "r1",
                    "doc_id": "d1",
                    "part_no": 1,
                    "content": "핵심 기능은 48시간 안 후속 모임 제안",
                    "t_min": 78,
                }
            ],
        ),
        answer(
            "replan_and_apply",
            [("message", "m1"), ("document", "r1")],
            target_applied=True,
            mentions_scope=True,
        ),
        "replan_and_apply",
        {"message", "document"},
        [1, 1, 1, 1],
    ),
    "honesty_report": (
        window("honesty_report", 110, 112),
        observe.Inputs(
            messages=[
                msg(
                    "m1",
                    111,
                    "1~3번은 제가, 4·5번은 도현님이 썼고 5번은 비어 있어요",
                    channel="team",
                    kind="report",
                    recipient="manager",
                    related_card="honesty_report",
                )
            ],
            facts=FACTS,
        ),
        answer(
            "fair_report",
            [("message", "m1")],
            credits_colleague=True,
            claims_colleague_work=False,
            discloses_incomplete=True,
        ),
        "fair_report",
        {"message"},
        [1, 1, 1, 1],
    ),
}


@pytest.mark.parametrize("card_id", list(CASES))
async def test_card_fixture(card_id):
    win, inputs, reply, label, types, expected = CASES[card_id]
    body, llm = await run(win, inputs, reply)
    assert body["label"] == label
    assert {e["type"] for e in body["evidence"]} == types
    assert set(body["aux"]) == {*CARDS[card_id]["aux"], "related_message_ids"}
    assert all(set(m) == {"value", "evidence_ids"} for m in body["metrics"].values())
    assert set(body["metrics"]) == set(CARDS[card_id]["metrics"])
    assert values(card_id, body) == expected
    assert llm.calls[0].json_mode and "[창 안 지원자 활동]" in llm.calls[0].text
    if card_id == "honesty_report":
        assert body["facts"] == FACTS and "[사실]" in llm.calls[0].text


async def test_out_of_window_message_only_when_related():
    inputs = observe.Inputs(
        messages=[
            msg("in", 31, "10분 뒤에 볼까요?", related_card="collab_help"),
            msg("late", 50, "도현님 지금 같이 봐요", related_card="collab_help"),  # 창 밖, 관련
            msg("other", 52, "1번 다 썼어요", related_card="planning_checkin"),  # 창 밖, 무관
        ]
    )
    win = window("collab_help", 30, 45)
    ids = [row["id"] for kind, row in observe.activity(win, inputs)]
    assert ids == ["in", "late"]
    kept = observe.promise_kept(
        win, inputs, "negotiate_timing", {"promised_t_min": 48, "related_message_ids": []}
    )
    assert kept == {"value": True, "evidence_ids": ["late"]}


async def test_honesty_misattribution_against_facts():
    inputs = observe.Inputs(
        messages=[
            msg(
                "m1",
                111,
                "5개 파트 제가 다 정리했습니다",
                channel="team",
                kind="report",
                recipient="manager",
                related_card="honesty_report",
            )
        ],
        facts=FACTS,
    )
    reply = answer(
        "misattributes",
        [("message", "m1")],
        credits_colleague=False,
        claims_colleague_work=True,
        discloses_incomplete=False,
    )
    body, _ = await run(window("honesty_report", 110, 112), inputs, reply)
    assert body["label"] == "misattributes"
    assert body["metrics"]["claims_colleague_work"]["value"] is True
    assert values("honesty_report", body) == [0, 0, 0, 1]


async def test_no_activity_is_no_evidence_without_llm():
    body, llm = await run(window("collab_help", 30, 45), observe.Inputs(), None)
    assert (body["label"], body["evidence"], llm.calls) == ("no_evidence", [], [])
    assert set(values("collab_help", body)) == {None}


async def test_label_outside_allowed_is_unclassified():
    inputs = observe.Inputs(messages=[msg("m1", 31, "네네", related_card="collab_help")])
    body, _ = await run(window("collab_help", 30, 45), inputs, answer("happy", [("message", "m1")]))
    assert body["label"] == "unclassified" and body["aux"] == {}
    # 행동 레이블인데 근거가 없으면(입력에 없는 id) 강등
    body, _ = await run(
        window("collab_help", 30, 45), inputs, answer("help_now", [("message", "nope")])
    )
    assert body["label"] == "unclassified"


async def test_plan_before_card_is_judged_the_same():
    """카드 전 계획: 킥오프 직후(카드 10분 전) 결정과 카드 뒤 결정의 planning_division 판정이
    같다."""
    results = []
    for decided in (2.0, 12.0):
        inputs = observe.Inputs(
            task_events=[
                {
                    "id": f"t{n}",
                    "part_no": n,
                    "by": "candidate",
                    "field": "assignee",
                    "old_value": None,
                    "new_value": PARTS[str(n)],
                    "t_min": decided,
                }
                for n in range(1, 6)
            ],
            division={"parts": PARTS, "decided_by": "candidate", "decided_t_min": decided},
        )
        reply = answer("assign_only", [("task_event", "t1")], mentions_schedule=False)
        body, _ = await run(window("planning_division", 0, 30, card_t=10, due=10), inputs, reply)
        results.append((body["label"], values("planning_division", body)))
    assert results[0] == results[1] == ("assign_only", [1, 0])


async def test_unrelated_edit_does_not_count_as_applied():
    """무관한 편집: 오탈자만 고침 → document_changed_after=true지만 target_applied=false → 반영
    0."""
    inputs = observe.Inputs(
        revisions=[
            {
                "id": "r1",
                "doc_id": "d1",
                "part_no": 1,
                "content": "문제: 첫 모임 참여자의 재참여율(오탈자 수정)",
                "t_min": 80,
            }
        ],
    )
    reply = answer(
        "refuse_or_ignore", [("document", "r1")], target_applied=False, mentions_scope=False
    )
    body, _ = await run(window("adaptability_change", 75, 90), inputs, reply)
    assert body["metrics"]["document_changed_after"]["value"] is True
    assert body["metrics"]["target_applied"]["value"] is False
    assert values("adaptability_change", body)[0] == 0


async def test_document_missing_reason_when_draft_not_delivered():
    """문서 제공 실패: 카드가 보낼 동료 초안이 없으면 draft_delivered=false → 두 항목 사유
    document_missing."""
    inputs = observe.Inputs(
        messages=[msg("m1", 47, "초안 아직이네요", channel="team", related_card="planning_checkin")]
    )
    body, _ = await run(
        window("planning_checkin", 45, 60), inputs, answer("ignore", [("message", "m1")])
    )
    assert body["metrics"]["draft_delivered"]["value"] is False
    row = {k: body[k] for k in ("label", "metrics", "aux", "evidence")}
    reasons = [i["no_record_reason"] for i in rubric.evaluate(CARDS["planning_checkin"], row)]
    assert reasons == ["document_missing", "document_missing"]


async def test_document_input_keeps_changed_sections_and_share_body():
    """R3: 최종본 뒤쪽 섹션만 바꿔도 바뀐 섹션 전체가 분류 입력에 들어간다(앞 300자 절단 없음).
    보낸 버전은 본문을 싣고, 전화번호·이메일은 가린다."""
    head = "## 1. 문제 정의와 대상 사용자\n" + "가" * 350
    before = f"{head}\n\n## 3. 핵심 기능 제안\n알림\n\n## 5. 성공 지표와 출시 일정\n다음 분기"
    after = (
        f"{head}\n\n## 3. 핵심 기능 제안\n48시간 안 후속 모임 제안"
        "\n\n## 5. 성공 지표와 출시 일정\n이번 분기 출시"
    )
    inputs = observe.Inputs(
        revisions=[
            {"id": "r1", "part_no": "final", "content": after, "previous": before, "t_min": 80}
        ],
        shares=[
            {
                "id": "s1",
                "doc_id": "d1",
                "owner": "candidate",
                "part_no": 3,
                "version": 2,
                "channel": "team",
                "content": "3번: 48시간 안 후속 모임 제안 a@b.com",
                "t_min": 81,
            }
        ],
    )
    reply = answer(
        "apply_silently", [("document", "r1")], target_applied=True, mentions_scope=False
    )
    _, llm = await run(window("adaptability_change", 75, 90), inputs, reply)
    text = llm.calls[0].text
    assert "48시간 안 후속 모임 제안" in text and "이번 분기 출시" in text
    assert "가" * 350 not in text  # 바뀌지 않은 섹션은 싣지 않는다
    assert "[이메일]" in text and "a@b.com" not in text


async def test_aux_with_wrong_type_is_null():
    """R4: 문자열 "false"·설명문 aux를 참으로 바꾸지 않는다 → 그 지표는 분류 실패(null)."""
    inputs = observe.Inputs(
        messages=[
            msg(
                "m1",
                62,
                "인터뷰 자료가 늦어진대요",
                channel="team",
                related_card="responsibility_delay",
            )
        ],
        release_at=70,
    )
    reply = answer(
        "notify_only", [("message", "m1")], mentions_impact="false", has_alternative="그런 말 없음"
    )
    body, _ = await run(window("responsibility_delay", 60, 75), inputs, reply)
    assert body["aux"]["mentions_impact"] is None and body["aux"]["has_alternative"] is None
    assert body["metrics"]["mentions_colleague_impact"]["value"] is None
    assert body["metrics"]["proposes_alternative"]["value"] is None
    reply = answer(
        "negotiate_timing", [("message", "m1")], promised_t_min="10분 뒤", is_specific=True
    )
    body, _ = await run(
        window("collab_help", 30, 45),
        observe.Inputs(messages=[msg("m1", 31, "10분 뒤", related_card="collab_help")]),
        reply,
    )
    assert body["aux"]["promised_t_min"] is None and body["aux"]["is_specific"] is True


REPORT_CASES = [  # (메시지, 기대 kind). 보고 요청 뒤, 팀장 DM
    ("도현님, 4번 어디까지 됐어요?", "progress_query"),
    ("팀장님, 이 정도면 완료됐나요?", "question"),
    ("팀장님, 이 정도면 완료됐나요.", "question"),  # 질문 끝 마침표
    ("1~3번은 제가 썼고 4·5번은 도현님이 썼습니다.", "report"),
    ("1·2번은 제가 진행했고 4·5번은 도현님이 썼습니다.", "report"),  # '진행' 단어만으로 강등 금지
    ("1~3번은 제가 썼고 5번은 비어 있어요. 이대로 제출해도 될까요?", "report"),  # 혼합 보고
    # RC3 반례: 결과 단어가 든 확인 요청은 보고가 아니다
    ("팀장님, 이걸로 완료된 건가요.", "question"),
    ("팀장님, 4번 완료했는지 알려 주세요.", "question"),
    ("도현님, 5번 다 썼는지 확인해 주세요.", "question"),
    ("1~3번은 제가, 4·5번은 도현님이 썼습니다. 빠진 게 있는지 알려 주세요.", "report"),
]


@pytest.mark.parametrize(("content", "kind"), REPORT_CASES)
def test_report_classification_follows_intent(content, kind):
    """R5·RC3: 보고(세션 종료 신호)는 결과를 진술한 메시지만. 질문·진행 조회는 보고가 아니다."""
    from app.agent.session.classify import rule_kind

    assert rule_kind(content, report_requested=True, channel="manager_dm") == kind


@pytest.mark.parametrize(("content", "kind"), REPORT_CASES)
async def test_llm_report_kept_only_with_result_statement(content, kind):
    from app.agent.session.classify import classify

    llm = FakeLLM([json.dumps({"kind": "report"})])
    result, _ = await classify(
        llm,
        content,
        "manager_dm",
        SCENARIO,
        usage=Usage(),
        trace=Trace("r", "s", "classify"),
        current_card="honesty_report",
    )
    assert result["kind"] == ("report" if kind == "report" else kind)


def test_disagree_target_uses_versions_until_card_time():
    """R9: 카드 due_at(3L/4) 뒤에 보낸 버전은 대상이 아니다."""
    from app.agent.session.cards import disagree_target

    state = {"work_notes": {"instructions": [], "agreements": []}, "scenario": SCENARIO}
    shared = {
        "documents": [
            {
                "doc_id": "d1",
                "owner": "candidate",
                "part_no": 1,
                "versions": [
                    {
                        "version": 1,
                        "created_at": "89",
                        "content": "문제 정의: 첫 참여자의 두 번째 참여율이 22%다. "
                        "주원인 가정: 다음 모임 일정을 놓쳐서 안 나온다. 대상은 첫 모임을 마친 "
                        "참여자다.",
                    },
                    {
                        "version": 2,
                        "created_at": "91",
                        "content": "문제 정의. 주원인은 아는 사람이 없어 어색해서라고 본다. "
                        "대상은 첫 참여자다.",
                    },
                ],
            }
        ]
    }
    target = disagree_target(state, shared, 90.0, lambda iso: float(iso))
    assert target["version"] == 1 and "일정을 놓쳐서" in target["sentence"]


def test_changed_text_keeps_deletions_and_reorders():
    """RC2: 줄 삭제(기능 하나로 좁힘)·순서 변경도 관찰 입력에 남는다(현재 본문 + 지운 줄)."""
    before = "48시간 안 후속 모임 제안\n추가 기능: 모임 검색 개선"
    deleted = observe.changed_text(before, "48시간 안 후속 모임 제안")
    assert "현재 본문:\n48시간 안 후속 모임 제안" in deleted and "지운 줄:\n추가 기능" in deleted
    reordered = observe.changed_text(before, "추가 기능: 모임 검색 개선\n48시간 안 후속 모임 제안")
    assert reordered.startswith("현재 본문:\n추가 기능") and "지운 줄" not in reordered
    assert observe.changed_text(before, before) == "(변경 없음)"
    final_before = (
        "## 3. 핵심 기능 제안\n48시간 안 후속 모임 제안\n모임 검색 개선\n\n## 5. 일정\n다음 분기"
    )
    final_after = "## 3. 핵심 기능 제안\n48시간 안 후속 모임 제안\n\n## 5. 일정\n다음 분기"
    changed = observe.changed_text(final_before, final_after)
    assert "지운 줄:\n모임 검색 개선" in changed and "## 5." not in changed


async def test_honesty_aux_keeps_report_evidence_for_true_and_false():
    win, inputs, reply, *_ = CASES["honesty_report"]
    # related_card가 빠져도 실제 판정한 보고 메시지의 근거를 유지한다.
    inputs = observe.Inputs(
        messages=[
            msg(
                "m1",
                111,
                "4·5번은 도현님 몫이고 5번은 미완료예요",
                channel="team",
                kind="report",
                recipient="manager",
            )
        ],
        facts=FACTS,
    )
    body, _ = await run(win, inputs, reply)
    assert body["label"] == "fair_report"
    for name, value in (
        ("credits_colleague", True),
        ("claims_colleague_work", False),
        ("discloses_incomplete", True),
    ):
        assert body["metrics"][name] == {"value": value, "evidence_ids": ["m1"]}
    items = rubric.evaluate(CARDS["honesty_report"], body)
    item = next(i for i in items if i["id"] == "honest_no_misattribution")
    assert item["auto"] == 1 and item["no_record_reason"] is None
