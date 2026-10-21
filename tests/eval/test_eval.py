"""eval 픽스처 형태 검사(mock, 기본)와 live 실행기(`-m live`).

형태 검사: 계약 스키마·기대값 집합·사람 라벨의 근거 규칙. live: 실제 모델로 한 번 돌려 채점 결과를
`records/eval-live-<일시>.md`에 남긴다(Agent 구현 증거, 기준선은 harness.md "실측 기준선").
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

from eval import evaluate

ROOT = Path(__file__).resolve().parents[2]
MISSION = ROOT / "scenarios" / "missions" / "debate"
CONTRACTS = ROOT / "tests" / "fixtures" / "contracts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dimension_ids() -> set[str]:
    rubric = yaml.safe_load((MISSION / "rubric.yaml").read_text("utf-8"))
    return {d["dimension_id"] for e in rubric["elements"] for d in e["dimensions"]}


# ---- 의도 분류 20문장 -------------------------------------------------------------------------


def test_intent_cases_cover_the_contract():
    data = evaluate.load_intent()
    cases = data["cases"]
    assert len(cases) == 20
    assert {c["expected"]["intent"] for c in cases} == set(evaluate.INTENTS)
    assert sum(1 for c in cases if c["expected"]["addressed_to"]) >= 3  # 이름 부르기
    keys = {p: {o["scenario_option_key"] for o in opts} for p, opts in data["catalog"].items()}
    first = [
        c
        for c in cases
        if c["expected"].get("target") and c["expected"]["target"] not in c["existing"]
    ]
    assert len(first) >= 3  # 아직 말하지 않은 카탈로그 안을 먼저 말하기
    for case in cases:
        want = case["expected"]
        assert want["confidence"] in ("high", "low")
        assert set(want["addressed_to"]) <= set(data["seats"])
        assert set(case["existing"]) <= keys[case["phase"]]
        if want["intent"] in evaluate.STANCE_INTENTS:
            assert want.get("new_label") or want["target"] in keys[case["phase"]]


def test_intent_catalog_matches_scenario_data():
    data = evaluate.load_intent()
    words = yaml.safe_load((MISSION / "keywords.yaml").read_text("utf-8"))["keywords"]
    water = next(k for k in words if k["key"] == "water")
    assert [o["scenario_option_key"] for o in data["catalog"]["problem"]] == [
        p["key"] for p in water["problems"]
    ]
    assert [o["scenario_option_key"] for o in data["catalog"]["solution"]] == [
        s["key"] for s in water["solutions"]
    ]
    assert [o["label"] for o in data["catalog"]["keyword"]] == [k["label"] for k in words]


def test_perfect_intent_output_scores_one():
    cases = evaluate.load_intent()["cases"]
    outputs = []
    for case in cases:
        want = case["expected"]
        out = {
            "intent": want["intent"],
            "target_option_id": None,
            "scenario_option_key": None,
            "new_option_label": "하수관 점검 앱" if want.get("new_label") else None,
            "confidence": want["confidence"],
            "addressed_to": want["addressed_to"],
        }
        if want["intent"] in evaluate.STANCE_INTENTS and want.get("target"):
            if want["target"] in case["existing"]:
                out["target_option_id"] = evaluate.option_id(want["target"])
            else:
                out["scenario_option_key"] = want["target"]
        assert evaluate.intent_violations(out) == []
        outputs.append(out)
    score = evaluate.score_intent(cases, outputs)
    assert score["violations"] == 0 and score["all"] == 1.0


def test_intent_schema_violations_are_counted():
    fallback = {
        "intent": "other",
        "target_option_id": None,
        "scenario_option_key": None,
        "new_option_label": None,
        "confidence": "low",
        "addressed_to": [],
    }
    assert evaluate.intent_violations(fallback) == []
    assert evaluate.intent_violations({**fallback, "intent": "maybe"})
    assert evaluate.intent_violations({**fallback, "addressed_to": ["p9"]})


# ---- 평가 에이전트 BARS -----------------------------------------------------------------------


def test_bars_sessions_have_session_record_shape():
    shape = set(json.loads((CONTRACTS / "session_record.json").read_text("utf-8")))
    message_keys = set(
        json.loads((CONTRACTS / "session_record.json").read_text("utf-8"))["messages"][0]
    )
    sessions = evaluate.load_bars()["sessions"]
    assert {s["element"] for s in sessions} == {
        "persuasion",
        "listening",
        "inclusion",
        "flexibility",
        "honesty",
    }
    for session in sessions:
        record = session["record"]
        assert set(record) == shape - {"seats"}, session["id"]  # seats는 common으로 공유
        for message in record["messages"]:
            assert set(message) == message_keys
        assert {s["phase"] for s in record["slots"]} == {"keyword", "problem", "solution"}


def test_bars_expected_levels_follow_evidence_rules():
    rubric = yaml.safe_load((MISSION / "rubric.yaml").read_text("utf-8"))
    by_element = {
        e["element"]: {d["dimension_id"] for d in e["dimensions"]} for e in rubric["elements"]
    }
    sessions = evaluate.load_bars()["sessions"]
    labeled = set()
    for session in sessions:
        assert set(session["expected"]) <= by_element[session["element"]]
        assert evaluate.expected_problems(session) == [], session["id"]
        for want in session["expected"].values():
            assert want["level"] is None or 1 <= want["level"] <= 5
        labeled |= set(session["expected"])
    assert labeled <= dimension_ids()
    assert len(labeled) >= 18  # 19개 차원 중 거의 전부에 사람 라벨


def test_bars_scoring_reports_exact_within1_and_distribution():
    sessions = evaluate.load_bars()["sessions"]
    perfect = {s["id"]: {d: w["level"] for d, w in s["expected"].items()} for s in sessions}
    assert evaluate.score_bars(sessions, perfect)["exact"] == 1.0
    off = {
        sid: {d: min(level + 1, 5) if level < 5 else 4 for d, level in dims.items()}
        for sid, dims in perfect.items()
    }
    score = evaluate.score_bars(sessions, off)
    assert score["within1"] == 1.0 and score["exact"] == 0.0
    assert set(score["diff_distribution"]) <= {-1, 1}
    assert evaluate.spread([{"a": 3}, {"a": 4}, {"a": 3}]) == {"a": 1}


# ---- 유출·유도 질문 ---------------------------------------------------------------------------


def test_leak_cases_cover_the_seven_prompts():
    cases = evaluate.load_leak()["cases"]
    assert [c["id"] for c in cases] == [
        "role_impersonation",
        "future_card",
        "scoring",
        "material_before_keyword",
        "proxy_conclusion",
        "credit_preemption",
        "inclusion_preemption",
    ]
    notices = yaml.safe_load((MISSION / "prompts" / "fixed_phrases.yaml").read_text("utf-8"))
    for case in cases:
        assert case["channel"] in ("room", "assistant")
        assert (case["target_seat"] is None) == (case["channel"] == "assistant")
        for pattern in case["must_not_regex"]:
            re.compile(pattern)
        if case["expected_notice"]:
            assert case["expected_notice"] in {**notices["notices"], "assistant_locked": 1}
    safe = "네, 저는 AI 동료예요. 평가 방식은 시작 전 안내 화면에 나온 내용이 전부예요."
    assert all(evaluate.leak_violations(c, safe) == [] for c in cases)
    assert evaluate.leak_violations(cases[2], "지금 3점쯤이고 합격권이에요.")


# ---- 세션 기록 저장 스크립트 ------------------------------------------------------------------


async def test_save_eval_fixture_writes_session_record(tmp_path):
    script = load_script("save_eval_fixture")
    record = json.loads((CONTRACTS / "session_record.json").read_text("utf-8"))

    async def fetch(session_id: str):
        return record

    path = await script.save("sess-1", fetch, tmp_path)
    assert path == tmp_path / "sess-1.json"
    assert set(json.loads(path.read_text("utf-8"))) == set(record)

    async def broken(session_id: str):
        return {"session": {}}

    with pytest.raises(ValueError):
        await script.save("sess-2", broken, tmp_path)


# ---- live (make eval-live) --------------------------------------------------------------------


@pytest.mark.live
async def test_intent_live(live_report):
    from app.agent.intent import classify
    from app.agent.llm import make_llm

    data = evaluate.load_intent()
    llm = make_llm("intent")
    # 운영 메일박스와 같은 입력: 채용 건에 복사된 카탈로그 prompts/intent.md를 지시로 넘긴다
    instructions = (MISSION / "prompts" / "intent.md").read_text("utf-8")
    outputs = []
    for case in data["cases"]:
        existing = [
            {
                "option_id": evaluate.option_id(k),
                "label": next(
                    o["label"]
                    for o in data["catalog"][case["phase"]]
                    if o["scenario_option_key"] == k
                ),
                "scenario_option_key": k,
            }
            for k in case["existing"]
        ]
        result, _ = await classify(
            llm,
            case["text"],
            phase=case["phase"],
            catalog=data["catalog"][case["phase"]],
            options=existing,
            recent=[],
            seats=data["seats"],
            instructions=instructions,
        )
        outputs.append(result)
    score = evaluate.score_intent(data["cases"], outputs)
    live_report.append(
        f"## 의도 분류 20문장 (기준선 {evaluate.INTENT_BASELINE})\n\n"
        f"```json\n{json.dumps(score, ensure_ascii=False, indent=2)}\n```"
    )
    assert score["violations"] == 0


@pytest.mark.live
async def test_bars_live(live_report):
    """세션마다 그 요소 호출 1회(evaluate_element)로 수준을 내고 사람 라벨과 비교한다."""
    sys.path.insert(0, str(ROOT / "services" / "report-worker"))
    from e2e.client import env
    from report_worker.evaluate import (
        EvalContext,
        RefIndex,
        evaluate_element,
        load_forbidden,
        load_prompts,
    )
    from report_worker.llm import OpenAILLM, empty_usage

    values = env()
    model = values.get("MODEL_EVALUATOR") or values.get("OPENAI_MODEL", "gpt-4o-mini")
    llm = OpenAILLM(model, values)
    rubric = yaml.safe_load((MISSION / "rubric.yaml").read_text("utf-8"))
    cards = yaml.safe_load((MISSION / "cards.yaml").read_text("utf-8"))["cards"]
    rubric["cards"] = [
        {
            "card_id": c["card_id"],
            "element": c["element"],
            "stage_id": c["stage_id"],
            "window": c["window"],
        }
        for c in cards
    ]
    prompts = load_prompts(ROOT / "scenarios", "debate")
    forbidden = load_forbidden(ROOT / "scenarios", "debate")
    data = evaluate.load_bars()
    sessions, outputs, unsupported = data["sessions"], {}, 0
    for session in sessions:
        record = {**session["record"], "seats": data["common"]["seats"]}
        ctx = EvalContext(
            record, rubric, RefIndex(record, record["contributions"]), prompts, forbidden
        )
        element = next(e for e in rubric["elements"] if e["element"] == session["element"])
        rows, _ = await evaluate_element(llm, ctx, element, empty_usage(model))
        outputs[session["id"]] = {r["dimension_id"]: r["level"] for r in rows}
        unsupported += sum(r["no_record_reason"] == "evaluate_failed" for r in rows)
    score = evaluate.score_bars(sessions, outputs) | {
        "evaluate_failed": unsupported,
        "pilot_target_within1": evaluate.BARS_PILOT_TARGET,
    }
    live_report.append(
        f"## 평가 에이전트 BARS\n\n```json\n{json.dumps(score, ensure_ascii=False, indent=2)}\n```"
    )
    assert score["n"] > 0


@pytest.mark.live
async def test_leak_live(live_report):
    """실 스택에 세션 하나를 열고(키워드 단계) 유출·유도 질문 7건을 실제 경로로 묻는다."""
    from e2e.client import Target
    from e2e.run import Runner

    data = evaluate.load_leak()
    runner = Runner(
        {"name": "eval_leak", "minutes": 15, "steps": []}, Target.from_env(), clock="real", poll=0.5
    )
    await runner.setup()
    names = {"p1": "강한결", "p2": "윤하람", "p3": "서지안"}
    rows = []
    try:
        for case in data["cases"]:
            if case["channel"] == "assistant":
                reply = await runner.api.json(
                    "POST",
                    f"/sessions/{runner.sid}/assistant",
                    token=runner.jwt,
                    json_body={"prompt": case["text"]},
                )
                text = reply["content"]
            else:
                since = len(runner.sock.frames)
                await runner.say(f"{names[case['target_seat']]}님, {case['text']}")
                seat = case["target_seat"]
                frame = await runner.sock.wait_for(
                    lambda f, seat=seat: (
                        f["type"] == "message.new" and f["payload"]["sender"] == seat
                    ),
                    40,
                    since,
                )
                text = frame["payload"]["content"] if frame else ""
            rows.append((case["id"], evaluate.leak_violations(case, text), text))
    finally:
        await runner.sock.close()
        await runner.api.aclose()
    lines = ["## 유출·유도 질문", "", "| 케이스 | 위반 | 응답 |", "|---|---|---|"]
    lines += [f"| {cid} | {', '.join(v) or '없음'} | {text[:80]} |" for cid, v, text in rows]
    live_report.append("\n".join(lines))
    assert all(not v for _, v, _ in rows)
