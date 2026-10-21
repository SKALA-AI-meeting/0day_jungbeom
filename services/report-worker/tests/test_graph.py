"""리포트 그래프·소비자(FakeLLM, 가짜 assessment·api, 메모리 체크포인터).

완료 기준(worker-infra/design.md): 요소당 1회 호출·결과 격리, save_evaluation 1회(척도 버전·프롬프트
버전 맵·모델), 재전달·저장 직후 장애에 LLM 재호출 없음, 리포트 형태, 카드 장면 = report_template,
eval_round·thread 규칙, interrupt·resume과 final 해시, LLM 타임아웃 → 저장 없이 큐 재시도,
3회 → DLQ, 계약 테스트 C7(정직 대조).
"""

import copy
import json
import logging
import shutil

import yaml
from report_worker.evaluate import ELEMENTS, load_prompts
from report_worker.graph import evaluation_run_id, thread_config
from report_worker.llm import FakeEvaluatorLLM, LLMUnavailable

from tests.conftest import (
    SCENARIOS,
    Harness,
    content_hash,
    contract,
    element_outputs,
    load,
    merged_report,
)


def dimension_ids(element: str) -> set[str]:
    rubric = load("internal_rubric")
    return {
        d["dimension_id"]
        for e in rubric["elements"]
        if e["element"] == element
        for d in e["dimensions"]
    }


async def test_generate_evaluates_each_element_once_and_saves_draft(h):
    await h.generate()

    # 요소마다 1회, 다른 요소의 차원·결과가 프롬프트에 없음
    assert [c[0] for c in h.llm.calls] == list(ELEMENTS)
    outputs = element_outputs()
    for element, system, user in h.llm.calls:
        block = user.split("[요소 척도]\n", 1)[1].split("\n\n[요소 지침]", 1)[0]
        scale = json.loads(block)
        assert {d["dimension_id"] for d in scale["dimensions"]} == dimension_ids(element)
        for other in ELEMENTS:  # 다른 요소의 판단 결과(요약·rationale)가 입력에 없음
            if other != element:
                assert outputs[other]["summary"] not in user
                assert not any(d["rationale"] in user for d in outputs[other]["dimensions"])
        assert "평가 에이전트 공통 지침" in system
    assert h.llm.temperature <= 0.2

    # save_evaluation 1회: 척도 버전·프롬프트 버전 맵·모델, 19차원·5요소
    assert h.assessment.calls.count("save_evaluation") == 1
    saved = h.assessment.saved[0]
    assert saved["run_id"] == evaluation_run_id("sess-1", 1)
    assert saved["rubric_version"] == "rubric-v1-20261021"
    assert set(saved["prompt_versions"]) == {"common", *ELEMENTS}
    assert saved["model"] == "gpt-4o-mini"
    contract.validate(saved, contract.SHAPES["evaluation_save"], "evaluation_save")

    # draft 저장(usage 포함), 그래프는 approval에서 멈춤
    assert len(h.api.drafts) == 1 and h.published == []
    draft, usage = h.api.drafts[0]
    assert usage["llm_calls"] == 5 and usage["reused"] is False
    snapshot = await h.graph.aget_state(thread_config("sess-1", 1))
    assert snapshot.next == ("approval",)
    assert snapshot.config["configurable"]["thread_id"] == "report:sess-1:1"


async def test_draft_shape_matches_report_contract(h):
    await h.generate()
    draft, _ = h.api.drafts[0]
    record = load("session_record")
    contract.validate(merged_report(draft, record), contract.REPORT, "report")

    text = json.dumps(draft, ensure_ascii=False)
    assert "total" not in {k for k in draft} and "총점" not in text
    # 근거: 같은 세션 행, 메시지 근거마다 record_ref와 앞 5·뒤 3 맥락
    for dimension in draft["dimensions"]:
        assert [e["ref"] for e in dimension["evidence"]] == dimension["evidence_refs"]
        if dimension["level"] is not None:
            counted = {e["ref"] for e in dimension["evidence"] if e["counted"]}
            assert len(counted) >= (2 if dimension["level"] >= 4 else 1)
        for evidence in dimension["evidence"]:
            if evidence["kind"] == "message":
                assert len(evidence["context"]["before"]) <= 5
                assert len(evidence["context"]["after"]) <= 3
                assert evidence["record_ref"]["id"] == evidence["ref"][4:]
    # 카드 장면은 시나리오 report_template 그대로, draft 단계 LLM 호출 0
    templates = {
        c["card_id"]: c["report_template"] for c in h.api.session["position"]["scenario"]["cards"]
    }
    assert {c["card_id"]: c["scene"] for c in draft["cards"]} == templates
    assert len(h.llm.calls) == 5
    # 사실 지표는 api 값 그대로, 기여 대조는 get_contributions와 일치
    assert draft["facts"] == record["facts"]
    assert draft["contribution_check"] == [
        {
            "phase": "problem",
            "option_id": "opt-pb-p2",
            "label": "도심 폭우·침수 피해 증가",
            "first_proposer": "p1",
            "credited_in_proposal": ["p1"],
            "credit_quote": "문제 상황: 강한결 님 제안",
        }
    ]
    assert draft["ai_usage"]["used"] is True
    event = draft["ai_usage"]["events"][0]
    assert event["request_quote"] == "도심 침수 사례에서 센서 경보 효과를 알려 줘"
    assert event["response_quote"] == "자료에 센서 경보로 피해가 줄었다는 내용이 있어요."
    assert draft["position"]["name"] == "재난 대응 기획자"
    assert draft["elements"][0]["summary"] == element_outputs()["persuasion"]["summary"]


async def test_redelivery_reuses_checkpoint_without_llm(h):
    await h.generate()
    await h.generate()  # 같은 eval_round 재전달: interrupt 체크포인트에서 draft 저장만
    assert len(h.llm.calls) == 5
    assert h.assessment.calls.count("get_session_record") == 1
    assert content_hash(h.api.drafts[0][0]) == content_hash(h.api.drafts[1][0])


async def test_rerun_reuses_saved_rewritten_summary_without_llm(h):
    h.assessment.record["observations"] = [
        o for o in h.assessment.record["observations"] if o["card_id"] != "listening_pressure"
    ]
    h.api.down = True
    await h.generate()
    assert len(h.llm.calls) == 6  # 5요소 + 경청 요약 재작성 1회
    h.api.down = False
    h.new_graph()
    await h.generate(attempt=2)
    assert len(h.llm.calls) == 6  # 저장된 평가 재사용
    saved = h.store.evaluations[evaluation_run_id("sess-1", 1)]
    listening = next(e for e in h.api.drafts[-1][0]["elements"] if e["element"] == "listening")
    assert listening["summary"] == next(
        e["summary"] for e in saved["elements"] if e["element"] == "listening"
    )


async def test_crash_after_save_recovers_elements_without_llm(h):
    h.api.down = True  # draft 저장 실패 = save_evaluation 직후 장애
    await h.generate()
    assert h.assessment.calls.count("save_evaluation") == 1
    h.api.down = False
    h.new_graph()  # 체크포인트 유실(강제 종료 흉내)
    await h.generate(attempt=2)
    assert len(h.llm.calls) == 5  # 재호출 없음
    assert h.assessment.calls.count("save_evaluation") == 1
    draft, usage = h.api.drafts[-1]
    assert usage["reused"] is True
    saved = h.store.evaluations[evaluation_run_id("sess-1", 1)]
    assert [(e["element"], e["level"], e["summary"]) for e in draft["elements"]] == [
        (e["element"], e["level"], e["summary"]) for e in saved["elements"]
    ]


async def test_new_eval_round_starts_new_thread_from_collect(h):
    await h.generate(eval_round=1)
    await h.generate(eval_round=2)  # 1회차가 interrupt에 멈춰 있어도 collect부터
    assert h.assessment.calls.count("get_session_record") == 2
    assert len(h.llm.calls) == 10
    runs = [d["evaluation"]["run_id"] for d, _ in h.api.drafts]
    assert runs == [evaluation_run_id("sess-1", 1), evaluation_run_id("sess-1", 2)]
    first = await h.graph.aget_state(thread_config("sess-1", 1))
    assert first.next == ("approval",)  # 1회차 thread는 그대로


async def test_approve_resumes_and_final_equals_draft(h):
    await h.generate()
    await h.approve()
    assert len(h.api.finals) == 1
    assert content_hash(h.api.finals[0]) == content_hash(h.api.drafts[-1][0])
    await h.approve()  # 중복 approve 멱등
    assert len(h.api.finals) == 1 and h.published == []


async def test_approve_before_draft_republishes(h):
    await h.approve()
    assert h.published == [
        ("report.approve", {"session_id": "sess-1", "attempt": 1, "eval_round": 1})
    ]
    assert h.sleeps == [15]


async def test_llm_timeout_saves_nothing_and_requeues(h):
    h.llm.fail_next = [LLMUnavailable("timeout")]
    await h.generate()
    assert h.assessment.calls.count("save_evaluation") == 0
    assert h.api.drafts == []
    assert h.published == [
        ("report.generate", {"session_id": "sess-1", "attempt": 2, "eval_round": 1})
    ]
    await h.generate(attempt=2)  # 재시도는 체크포인트(aggregate 뒤)에서 이어서
    assert h.assessment.calls.count("get_session_record") == 1
    assert h.assessment.calls.count("save_evaluation") == 1
    assert len(h.api.drafts) == 1


async def test_three_failures_go_to_dlq_and_dlq_marks_failed(h):
    h.api.down = True
    for attempt in (1, 2, 3):
        await h.generate(attempt=attempt)
    queues = [q for q, _ in h.published]
    assert queues == ["report.generate", "report.generate", "report.dlq"]
    dlq_body = h.published[-1][1]
    assert dlq_body["attempt"] == 3 and "ConnectError" in dlq_body["error"]
    assert h.sleeps == [5, 15, 45]

    calls = 0
    original = h.api.report_failed

    async def flaky(session_id, error):
        nonlocal calls
        calls += 1
        if calls == 1:
            h.api.down = True
        else:
            h.api.down = False
        return await original(session_id, error)

    h.api.report_failed = flaky
    await h.worker.dead_letter(dlq_body)
    assert h.api.failed == [dlq_body["error"]]
    assert h.sleeps[-1] == 60


async def test_c7_honesty_credit_contrast(h):
    """C7: 비판형(p3)이 처음 낸 해결책이 채택되고 지원자가 기여 칸에 '해결책: 본인 제안'."""
    contributions = h.assessment.contributions
    for option in contributions["options"]:
        if option["phase"] == "solution":
            option["adopted"] = option["option_id"] == "opt-sl-s2"
    solution_slot = next(s for s in contributions["slots"] if s["phase"] == "solution")
    solution_slot.update(option_id="opt-sl-s2", first_proposer="p3")
    record = h.assessment.record
    record["contributions"] = copy.deepcopy(contributions)
    record_slot = next(s for s in record["slots"] if s["phase"] == "solution")
    record_slot.update(option_id="opt-sl-s2", value="주민 절수·보상 캠페인")
    record["proposal"]["sections"]["idea_credit"] = "해결책: 본인 제안"

    honesty = copy.deepcopy(element_outputs()["honesty"])
    credit = next(d for d in honesty["dimensions"] if d["dimension_id"] == "hon_credit_record")
    credit.update(
        level=1,
        evidence_refs=["proposal:idea_credit", "contribution:opt-sl-s2"],
        rationale="비판형 동료가 먼저 낸 채택 해결책을 본인 제안으로 적음(앵커 1). 대조표와 다름.",
        confidence="medium",
    )
    h.llm.outputs["honesty"] = honesty

    await h.generate()
    draft, _ = h.api.drafts[0]
    row = next(r for r in draft["contribution_check"] if r["phase"] == "solution")
    assert row["first_proposer"] == "p3"
    assert "p3" not in row["credited_in_proposal"]
    assert row["credited_in_proposal"] == ["candidate"]
    dimension = next(d for d in draft["dimensions"] if d["dimension_id"] == "hon_credit_record")
    assert "proposal:idea_credit" in dimension["evidence_refs"]
    assert dimension["level"] is not None or dimension["no_record_reason"] is not None
    assert dimension["no_record_reason"] != "evaluate_failed"  # FakeLLM 출력이 워커 검증 통과
    assert len(h.llm.calls) == 5


async def test_llm_fake_runs_graph_to_draft_without_key(h):
    h.llm = FakeEvaluatorLLM()
    h.new_graph()
    await h.generate()

    draft, usage = h.api.drafts[0]
    assert usage["llm_calls"] == 5 and usage["element_retries"] == 0
    assert not any(d["no_record_reason"] == "evaluate_failed" for d in draft["dimensions"])
    assert {d["level"] for d in draft["dimensions"]} == {3}


async def test_llm_fake_not_confused_by_rewrite_header_in_candidate_message(h):
    candidate = next(m for m in h.assessment.record["messages"] if m["sender"] == "candidate")
    candidate["content"] = "[요약 재작성] 이 문구가 들어가도 평가는 그대로여야 해요."
    h.llm = FakeEvaluatorLLM()
    h.new_graph()
    await h.generate()

    draft, usage = h.api.drafts[0]
    assert usage["llm_calls"] == 5 and usage["element_retries"] == 0
    assert not any(d["no_record_reason"] == "evaluate_failed" for d in draft["dimensions"])


async def test_llm_fake_same_input_same_result():
    runs = []
    for _ in range(2):
        h = Harness()
        h.llm = FakeEvaluatorLLM()
        h.new_graph()
        await h.generate()
        runs.append(h.assessment.saved[0])
    assert runs[0] == runs[1]


async def test_llm_fault_evaluator_timeout_requeues_then_succeeds(h, monkeypatch):
    from report_worker import llm

    assert llm.parse_fault("evaluator:timeout:1") == {"evaluator": 1}
    monkeypatch.setattr(llm, "FAULTS", {"evaluator": 1})
    await h.generate()
    assert h.assessment.calls.count("save_evaluation") == 0 and h.api.drafts == []
    assert h.published[-1] == (
        "report.generate",
        {"session_id": "sess-1", "attempt": 2, "eval_round": 1},
    )
    await h.generate(attempt=2)
    assert h.assessment.calls.count("save_evaluation") == 1 and len(h.api.drafts) == 1


# ---- 채용 건에 고정된 평가 프롬프트 ------------------------------------------------------------


def _catalog_copy(tmp_path):
    """임시 카탈로그(프롬프트 폴더만)와, 지금 내용으로 채용 건을 만들 때 복사되는 prompts 맵."""
    src = SCENARIOS / "missions" / "debate" / "prompts"
    folder = tmp_path / "missions" / "debate" / "prompts"
    shutil.copytree(src, folder)
    return folder


def _snapshot(folder):
    """api `scenario.assemble`의 `prompts`와 같은 모양(prompts/ 상대 경로 → 본문, fixtures 제외)."""
    return {
        p.relative_to(folder).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(folder.rglob("*"))
        if p.is_file() and "fixtures" not in p.parts
    }


def _use_position(h, tmp_path, prompts):
    h.api.session["position"]["scenario"]["prompts"] = prompts
    h.scenarios_dir = tmp_path
    h.new_graph()


LACKS = "lacks evaluator prompts"
CHANGED = "\n바뀐 지침"


def _change_catalog(folder):
    """채용 건 생성 뒤 카탈로그 수정: 공통·5요소 지침에 문장 추가, 금지 패턴에 '.' 추가."""
    for name in ("common", *ELEMENTS):
        path = folder / "evaluator" / f"{name}.md"
        path.write_text(path.read_text(encoding="utf-8") + CHANGED, encoding="utf-8")
    guard = folder / "guard_patterns.yaml"
    data = yaml.safe_load(guard.read_text(encoding="utf-8"))
    data["evaluator_forbidden"]["patterns"].append(".")
    guard.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _assert_original_prompts(h):
    original = load_prompts(SCENARIOS, "debate")
    assert all(system == original.common for _, system, _ in h.llm.calls)
    for element, _, user in h.llm.calls:
        assert CHANGED not in user
        if "[요소 지침]" in user:
            assert original.elements[element] in user


async def test_position_keeps_evaluator_prompts_after_catalog_change(h, tmp_path, caplog):
    folder = _catalog_copy(tmp_path)
    _use_position(h, tmp_path, _snapshot(folder))  # 채용 건 생성 시점
    _change_catalog(folder)

    with caplog.at_level(logging.INFO, logger="report_worker.evaluate"):
        await h.generate()

    _assert_original_prompts(h)
    assert h.assessment.saved[0]["prompt_versions"] == load_prompts(SCENARIOS, "debate").versions
    # 파일의 금지 패턴('.')이 쓰였다면 모든 요소가 재요청·evaluate_failed가 된다
    draft, usage = h.api.drafts[0]
    assert usage["llm_calls"] == 5 and usage["element_retries"] == 0
    assert not any(d["no_record_reason"] == "evaluate_failed" for d in draft["dimensions"])
    assert LACKS not in caplog.text


async def test_pinned_prompts_cover_retry_rewrite_and_rerun(h, tmp_path, caplog):
    folder = _catalog_copy(tmp_path)
    _use_position(h, tmp_path, _snapshot(folder))
    _change_catalog(folder)
    h.llm.script["persuasion"] = ["형식 오류", element_outputs()["persuasion"]]  # 요소 재요청
    h.assessment.record["observations"] = [  # 경청 요약 재작성
        o for o in h.assessment.record["observations"] if o["card_id"] != "listening_pressure"
    ]
    h.api.down = True  # draft 저장 실패 → 재실행은 저장된 평가 재사용

    with caplog.at_level(logging.INFO, logger="report_worker.evaluate"):
        await h.generate()
        assert len(h.llm.calls) == 7  # 5요소 + 재요청 1 + 요약 재작성 1
        h.api.down = False
        h.new_graph()
        await h.generate(attempt=2)
        await h.generate(eval_round=2)  # 새 평가 회차도 같은 채용 건 복사본

    _assert_original_prompts(h)
    assert len(h.llm.calls) == 13  # 2회차: 5요소 + 요약 재작성 1(재요청 스크립트는 소진)
    versions = load_prompts(SCENARIOS, "debate").versions
    assert [s["prompt_versions"] for s in h.assessment.saved] == [versions, versions]
    assert LACKS not in caplog.text


async def test_new_position_gets_changed_evaluator_prompts(h, tmp_path):
    folder = _catalog_copy(tmp_path)
    (folder / "evaluator" / "common.md").write_text("바뀐 공통 지침", encoding="utf-8")
    _use_position(h, tmp_path, _snapshot(folder))  # 바뀐 뒤 만든 채용 건

    await h.generate()

    assert all(system == "바뀐 공통 지침" for _, system, _ in h.llm.calls)
    saved = h.assessment.saved[0]["prompt_versions"]
    assert saved["common"] == load_prompts(tmp_path, "debate").versions["common"]
    assert saved["common"] != load_prompts(SCENARIOS, "debate").versions["common"]


async def test_old_position_without_prompts_falls_back_to_files(h, tmp_path, caplog):
    folder = _catalog_copy(tmp_path)
    (folder / "evaluator" / "common.md").write_text("현재 파일 지침", encoding="utf-8")
    _use_position(h, tmp_path, None)  # 프롬프트 복사 전에 만든 채용 건
    h.api.down = True

    with caplog.at_level(logging.INFO, logger="report_worker.evaluate"):
        await h.generate()
        assert caplog.text.count(LACKS) == 2  # evaluate·draft가 각각 읽음
        caplog.clear()
        h.api.down = False
        h.new_graph()
        await h.generate(attempt=2)  # 저장 평가 재사용: draft의 금지어 로드만 폴백
        assert caplog.text.count(LACKS) == 1

    assert all(system == "현재 파일 지침" for _, system, _ in h.llm.calls)
    assert len(h.llm.calls) == 5 and len(h.api.drafts) == 1


async def test_partial_snapshot_falls_back_to_files_entirely(h, tmp_path, caplog):
    folder = _catalog_copy(tmp_path)
    partial = _snapshot(folder)
    del partial["evaluator/honesty.md"]
    (folder / "evaluator" / "common.md").write_text("현재 파일 지침", encoding="utf-8")
    _use_position(h, tmp_path, partial)

    with caplog.at_level(logging.INFO, logger="report_worker.evaluate"):
        await h.generate()

    assert all(system == "현재 파일 지침" for _, system, _ in h.llm.calls)
    assert h.assessment.saved[0]["prompt_versions"] == load_prompts(tmp_path, "debate").versions
    assert LACKS in caplog.text
