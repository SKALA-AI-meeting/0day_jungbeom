"""리포트 형태(contracts.md Report, web-admin이 읽는 형태), 이벤트 기반 판단, 메시지 전체 수집."""

import uuid

from report_worker.report import NOTE_NOT_FIRED, build_draft

from tests.conftest import FakeLLM, at, card, event


def by_element(draft, key):
    return {s["element"]: s for s in draft[key]}


async def test_event_status_decides_fired_and_delay(fake_api, ids_map):
    """review는 실행됐지만 respect는 아직 pending인 채 제출 → respect는 미발생.

    책임감 카드 메시지가 예정(60분)보다 2분 늦게 나감 → window_missed, 근거의 카드 시각은 실제 62분.
    """
    data = fake_api.data
    session = data["session"]
    session["position"]["elements"].append("respect")
    scenario = session["position"]["scenario"]
    scenario["elements"].append("respect")
    scenario["cards"].append(card("respect", 90))
    review_id, respect_id = str(uuid.uuid4()), str(uuid.uuid4())
    session["events"] += [
        event(review_id, "review", 90),
        event(respect_id, "respect", 90, "pending"),
    ]
    data["messages"].append(
        {
            "id": str(uuid.uuid4()),
            "channel": "team",
            "sender": "colleague",
            "content": "제 파트 올렸어요, 리뷰 부탁드려요",
            "event_id": review_id,
            "run_id": None,
            "t_min": 90,
            "created_at": at(90),
            "meta": {},
        }
    )
    resp_card = next(m for m in data["messages"] if m["id"] == ids_map["resp_card"])
    resp_card.update(t_min=62, created_at=at(62))

    draft, _ = await build_draft(data, FakeLLM())
    sections, rubric = by_element(draft, "sections"), by_element(draft["rubric"], "elements")

    respect = sections["respect"]
    assert (respect["event_fired"], respect["no_record_reason"]) == (False, "event_not_fired")
    assert respect["note"] == NOTE_NOT_FIRED
    assert {i["no_record_reason"] for i in rubric["respect"]["items"]} == {"event_not_fired"}

    responsibility = sections["responsibility"]
    assert responsibility["event_fired"] and responsibility["no_record_reason"] == "window_missed"
    assert {i["no_record_reason"] for i in rubric["responsibility"]["items"]} == {"window_missed"}
    assert responsibility["evidence"][0]["context"]["card_at_t_min"] == 62

    assert sections["cooperation"]["no_record_reason"] is None
    assert sections["cooperation"]["evidence"][0]["context"]["card_at_t_min"] == 30


async def test_report_shape_matches_admin_view(fake_api, ids_map):
    draft, _ = await build_draft(fake_api.data, FakeLLM())
    coop = by_element(draft, "sections")["cooperation"]

    context = coop["evidence"][0]["context"]
    assert context == {
        "prev_persona_message": "이도현 · 30분: 10분만 같이 봐 주실 수 있어요?",
        "card_at_t_min": 30,
    }
    assert coop["aux_facts"] == []
    assert coop["out_of_window_messages"] == [
        {"t_min": 95, "channel": "dm", "quote": "아까 말한 기준 지금 같이 봐요."}
    ]

    items = {i["id"]: i for i in by_element(draft["rubric"], "elements")["cooperation"]["items"]}
    assert items["coop_replied_within_5m"]["minutes"] == 2.0
    assert "minutes" not in items["coop_replied"]
    assert all("no_record_reason" in i for i in items.values())

    categories = [(e["call_id"], e["category"]) for e in draft["ai_usage"]["evidence"]]
    assert categories == [
        (ids_map["call1"], "context"),
        (ids_map["call2"], "verify"),
        (ids_map["call1"], "delegate"),  # 2번 파트에 고쳐서 반영(edited)
    ]


async def test_collect_reads_all_messages_by_offset(api, fake_api):
    filler = [
        {**fake_api.data["messages"][0], "id": str(uuid.uuid4()), "event_id": None}
        for _ in range(1100)
    ]
    fake_api.data["messages"] += filler
    collected = await api.collect(fake_api.session_id)
    assert len(collected["messages"]) == len(fake_api.data["messages"])
    pages = [c for c in fake_api.calls if c[1].endswith("/messages")]
    assert len(pages) == 3  # 500 + 500 + 나머지
