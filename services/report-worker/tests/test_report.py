"""완료 기준: 리포트 형태가 공용 픽스처(report.json)와 같음, 카드 단위 평가표·summary 세 수·basis·
by_source, 근거 record_ref·context·flag(aux_fact·out_of_window), 정직 소섹션 facts, ai_usage 사실만,
최소 테스트 ③④⑤의 워커 소비(PATCH된 promise_kept, target_applied=false 미충족, document_missing),
카드 미발생·전달 지연, 금지어·타 세션 근거 제거.
"""

import uuid

from report_worker.report import build_draft

from tests.conftest import FakeLLM, at, contract

API_KEYS = {"alias", "position", "deliverable", "notes", "connection_gaps", "purge_at"}


def cards(draft, key="sections"):
    """card_id → 카드. sections(리포트 본문) 또는 rubric(평가표)."""
    elements = draft["sections"] if key == "sections" else draft["rubric"]["elements"]
    return {c["card_id"]: c for e in elements for c in e["cards"]}


def autos(card):
    return [(i["id"], i["auto"], i["no_record_reason"]) for i in card["items"]]


async def test_draft_follows_report_contract(fake_api, ids_map):
    draft, usage = await build_draft(fake_api.data, FakeLLM())
    fixture = contract.load_contract("report")
    # 워커가 만드는 부분만(나머지는 api가 GET 때 붙인다)
    assert set(draft) == set(fixture) - API_KEYS
    for key in ("summary", "rubric", "sections", "ai_usage"):
        contract.assert_shape(draft[key], fixture[key], f"report.{key}")
    assert usage["llm_calls"] == 0  # 분류는 observe가 했고 리포트 문장은 카탈로그에서 온다

    assert draft["rubric"]["auto_total"] == {"met": 18, "unmet": 2, "no_record": 0}
    summary = {s["element"]: (s["met"], s["unmet"], s["no_record"]) for s in draft["summary"]}
    assert summary == {
        "responsibility": (3, 1, 0),
        "planning": (4, 0, 0),
        "adaptability": (3, 1, 0),
        "collaboration": (4, 0, 0),
        "honesty": (4, 0, 0),
    }
    rubric = cards(draft, "rubric")
    item = {i["id"]: i for c in rubric.values() for i in c["items"]}
    # label 항목은 미충족이어도 판정 창의 지원자 메시지를 근거로 싣는다(contracts.md)
    assert [e["id"] for e in item["resp_proposed_alternative"]["evidence"]] == [ids_map["m31"]]
    assert item["plan_stated_schedule"]["basis"] == "metric"  # by_source: 보드(task_event) 근거
    assert item["honest_reported_within_10m"]["minutes"] == 2.0

    sections = cards(draft)
    division = sections["planning_division"]
    board = [e["summary"] for e in division["evidence"] if e["type"] == "task_event"]
    assert board == ["1번 담당 → 지원자(12분)", "1번 언제까지 → 40분(12.5분)"]
    assert (division["window"], division["card_at_t_min"]) == (
        {"start_min": 0.0, "end_min": 30.0},
        10,
    )
    share = next(e for e in sections["adaptability_change"]["evidence"] if e["type"] == "share")
    assert share["summary"] == "1번 파트 v2 보냄(84분)"
    assert share["record_ref"] == {"type": "share", "id": ids_map["sh3"], "t_min": 84.0}
    document = next(
        e for e in sections["adaptability_change"]["evidence"] if e["type"] == "document"
    )
    assert document["record_ref"] is None  # 전체 기록에 없는 타입
    view = next(e for e in sections["responsibility_delay"]["evidence"] if e["type"] == "doc_view")
    assert (view["flag"], view["summary"]) == ("aux_fact", "사용자 인터뷰 요약 열람(71분)")
    assert sections["honesty_report"]["facts"]["empty_sections"] == [3, 5]
    assert sections["responsibility_delay"]["evidence"][0]["context"]["prev_persona_message"] == (
        "이도현 · 45.1분: 주담당 쪽은 어느 정도 진행됐어요? 2번 자료는 언제쯤 볼 수 있을까요?"
    )

    events = draft["ai_usage"]["events"]
    assert [(e["t_min"], e["applied_part"]) for e in events] == [(47.5, None), (72.0, 2)]
    assert set(events[0]) == {
        "call_id",
        "t_min",
        "request_quote",
        "response_quote",
        "cited_doc_ids",
        "applied_part",
    }


async def test_promise_kept_after_window_is_consumed(fake_api, ids_map):
    """최소 테스트 ③(워커): 창 닫힘에 null이던 promise_kept가 종료 PATCH로 true가 됐으면 그 값과
    창 밖(50분) 메시지를 근거로 쓴다(flag 없음). 근거가 아닌 창 밖 관련 메시지는 out_of_window."""
    stray = str(uuid.uuid4())
    fake_api.data["messages"].append(
        {
            "id": stray,
            "channel": "dm",
            "sender": "candidate",
            "content": "아까 기준 메모 남겨 둘게요",
            "event_id": None,
            "run_id": None,
            "t_min": 55.0,
            "created_at": at(55),
            "meta": {"classification": {"related_card": "collab_help", "kind": "other"}},
        }
    )
    draft, _ = await build_draft(fake_api.data, FakeLLM())
    kept = next(
        i
        for i in cards(draft, "rubric")["collab_help"]["items"]
        if i["id"] == "collab_help_kept_promise"
    )
    assert kept["auto"] == 1 and [e["id"] for e in kept["evidence"]] == [ids_map["m_promise"]]
    evidence = {e["id"]: e for e in cards(draft)["collab_help"]["evidence"]}
    assert "flag" not in evidence[ids_map["m_promise"]]
    assert evidence[stray]["flag"] == "out_of_window"


async def test_unrelated_edit_is_unmet(fake_api, ids_map):
    """최소 테스트 ④(워커): 바뀐 대상이 반영되지 않은 편집은 반영 항목 0이고 문서 근거는 남는다."""
    row = next(o for o in fake_api.data["observations"] if o["card_id"] == "adaptability_change")
    row["label"] = "refuse_or_ignore"
    row["metrics"]["target_applied"] = {"value": False, "evidence_ids": []}
    draft, _ = await build_draft(fake_api.data, FakeLLM())
    items = {i["id"]: i for i in cards(draft, "rubric")["adaptability_change"]["items"]}
    applied = items["adapt_applied_to_doc"]
    assert applied["auto"] == 0
    assert {e["type"] for e in applied["evidence"]} == {"document", "share"}
    assert items["adapt_no_complaint_to_colleague"]["auto"] == 0


async def test_document_missing_reason(fake_api):
    """최소 테스트 ⑤(워커): 초안이 끝내 오지 않은 중간 점검은 두 항목 모두 사유 document_missing."""
    event = next(
        e for e in fake_api.data["session"]["events"] if e["card_id"] == "planning_checkin"
    )
    event["document_missing"] = True
    draft, _ = await build_draft(fake_api.data, FakeLLM())
    checkin = cards(draft)["planning_checkin"]
    assert (checkin["no_record_reason"], checkin["note"], checkin["evidence"]) == (
        "document_missing",
        "시스템: 문서 미제공",
        [],
    )
    assert autos(cards(draft, "rubric")["planning_checkin"]) == [
        ("plan_opened_draft", None, "document_missing"),
        ("plan_responded_draft", None, "document_missing"),
    ]


async def test_by_source_basis_follows_evidence(fake_api, ids_map):
    """보드에 순서·시점이 없고 채팅(aux)으로만 말했으면 plan_stated_schedule은 AI 분류 기반."""
    row = next(o for o in fake_api.data["observations"] if o["card_id"] == "planning_division")
    row["metrics"]["stated_schedule"] = {"value": True, "evidence_ids": [ids_map["m11"]]}
    draft, _ = await build_draft(fake_api.data, FakeLLM())
    item = next(
        i
        for i in cards(draft, "rubric")["planning_division"]["items"]
        if i["id"] == "plan_stated_schedule"
    )
    assert (item["auto"], item["basis"]) == (1, "label")


async def test_unfired_and_delayed_cards(fake_api, ids_map):
    """보고 요청 전 제출로 honesty_report 미발생 → event_not_fired.
    지연 알림이 2분 늦게 나감 → window_missed."""
    events = {e["card_id"]: e for e in fake_api.data["session"]["events"]}
    events["honesty_report"]["status"] = "pending"
    delay = next(m for m in fake_api.data["messages"] if m["id"] == ids_map["m_delay"])
    delay.update(t_min=62.0, created_at=at(62))
    draft, _ = await build_draft(fake_api.data, FakeLLM())
    sections = cards(draft)
    assert (
        sections["honesty_report"]["event_fired"],
        sections["honesty_report"]["no_record_reason"],
    ) == (False, "event_not_fired")
    assert sections["responsibility_delay"]["card_at_t_min"] == 62.0
    assert {
        i["no_record_reason"] for i in cards(draft, "rubric")["responsibility_delay"]["items"]
    } == {"window_missed"}


async def test_forbidden_words_and_foreign_evidence_removed(fake_api, ids_map):
    card = next(
        c
        for c in fake_api.data["session"]["position"]["scenario"]["cards"]
        if c["card_id"] == "collab_help"
    )
    card["label_texts"]["negotiate_timing"] = "도울 시점을 제안함. 상위 10% 응답으로 합격권임."
    row = next(o for o in fake_api.data["observations"] if o["card_id"] == "collab_help")
    row["evidence"].append({"type": "message", "id": ids_map["foreign"]})
    row["metrics"]["responded_to_request"]["evidence_ids"].append(ids_map["foreign"])
    draft, _ = await build_draft(fake_api.data, FakeLLM())
    section = cards(draft)["collab_help"]
    assert section["observed"] == "도울 시점을 제안함."
    collab = next(s for s in draft["summary"] if s["element"] == "collaboration")
    assert "합격" not in collab["line"]
    ids = {e["id"] for e in section["evidence"]} | {
        e["id"] for i in cards(draft, "rubric")["collab_help"]["items"] for e in i["evidence"]
    }
    assert ids_map["foreign"] not in ids and ids_map["m_help_reply"] in ids


async def test_all_no_record_card_hides_observed(fake_api):
    """관문 3 리뷰 A2: 창을 놓친 카드는 항목이 전부 기록 없음이고 관찰 문장·요약 줄도 비운다."""
    row = next(o for o in fake_api.data["observations"] if o["card_id"] == "honesty_report")
    row["metrics"]["window_missed"] = {"value": True, "evidence_ids": []}
    draft, _ = await build_draft(fake_api.data, FakeLLM())
    section = cards(draft)["honesty_report"]
    assert (section["observed"], section["no_record_reason"]) == (None, "window_missed")
    honesty = next(s for s in draft["summary"] if s["element"] == "honesty")
    assert (honesty["line"], honesty["met"], honesty["unmet"], honesty["no_record"]) == (
        None,
        0,
        0,
        4,
    )


async def test_window_without_observation_uses_actual_times(fake_api, ids_map):
    """관문 3 리뷰 A3: 관찰 행이 없는 조기 제출. 보고 요청이 20분에 실제로 나가고 25분에 끝났으면
    창은 20–25분이다(예정 시각 110분으로 역전되지 않음)."""
    fake_api.data["observations"] = [
        o for o in fake_api.data["observations"] if o["card_id"] != "honesty_report"
    ]
    event = next(e for e in fake_api.data["session"]["events"] if e["card_id"] == "honesty_report")
    event.update(due_at=at(20), fired_at=at(20))
    request = next(m for m in fake_api.data["messages"] if m["id"] == ids_map["m_report_req"])
    request.update(t_min=20.0, created_at=at(20))
    fake_api.data["session"]["completed_at"] = at(25)
    draft, _ = await build_draft(fake_api.data, FakeLLM())
    section = cards(draft)["honesty_report"]
    assert (section["card_at_t_min"], section["window"]) == (
        20.0,
        {"start_min": 20.0, "end_min": 25.0},
    )


async def test_flags_survive_when_also_in_observation(fake_api, ids_map):
    """관문 3 리뷰 A4: 관찰 근거에도 들어간 aux 사실(dv2)은 aux_fact, aux.related_message_ids에
    들어간 창 밖 메시지는 out_of_window. 점수에 쓰인 50분 약속 메시지는 flag 없음."""
    delay = next(o for o in fake_api.data["observations"] if o["card_id"] == "responsibility_delay")
    delay["evidence"].append({"type": "doc_view", "id": ids_map["dv2"]})
    stray = str(uuid.uuid4())
    fake_api.data["messages"].append(
        {
            "id": stray,
            "channel": "dm",
            "sender": "candidate",
            "content": "아까 기준 메모 남겨 둘게요",
            "event_id": None,
            "run_id": None,
            "t_min": 55.0,
            "created_at": at(55),
            "meta": {"classification": {"related_card": "collab_help", "kind": "other"}},
        }
    )
    help_row = next(o for o in fake_api.data["observations"] if o["card_id"] == "collab_help")
    help_row.setdefault("aux", {}).setdefault("related_message_ids", []).append(stray)
    draft, _ = await build_draft(fake_api.data, FakeLLM())
    view = next(
        e for e in cards(draft)["responsibility_delay"]["evidence"] if e["id"] == ids_map["dv2"]
    )
    assert view["flag"] == "aux_fact"
    evidence = {e["id"]: e for e in cards(draft)["collab_help"]["evidence"]}
    assert evidence[stray]["flag"] == "out_of_window"
    assert "flag" not in evidence[ids_map["m_promise"]]
