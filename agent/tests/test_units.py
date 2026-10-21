import asyncio
import json
import re
from collections import Counter

import pytest

from app.criteria import AXES, INDUSTRIES, JOBS, pick_axis
from app.detector import kappa, tki_label
from app.dilemmas import build_cached, persuade_beat
from app.harness import context, guardrails, instructions, recovery
from app.harness.loop import LimitExceeded, Limits
from app.llm import clean_line, persona_system, strip_boilerplate
from app.personas import CONDITIONS, MODES, allocate
from app.scenarios import public_scenario
from mcp_servers.detector.rules import features, rule_estimate


def test_axes_from_data_cover_all_job_industry_combinations():
    assert set(AXES) == {"V1", "V2", "V3", "V4"}
    for ax in AXES.values():
        assert ax["stats"]["r"] < 0 and ax["stats"]["balance"] >= 0.30
    assert {pick_axis(j, i) for j in JOBS for i in INDUSTRIES} == set(AXES)


def test_public_scenario_hides_axis_beats_and_stances():
    dumped = json.dumps(public_scenario(build_cached("dl.pm.fintech")), ensure_ascii=False)
    for secret in ("axis", "pole", "stance", "beats", "must_convey"):
        assert secret not in dumped


def test_persuade_beat_goes_to_opposite_pole():
    scn = build_cached("dl.pm.fintech")  # V2: lead = 원칙(a), peer = 파격(b)
    assert persuade_beat(scn, {"option": "a", "pole": "a"})["speaker"] == "peer"
    assert persuade_beat(scn, {"option": "b", "pole": "b"})["speaker"] == "lead"
    assert "절충안" in persuade_beat(scn, {"option": "both", "pole": "both"})["must_convey"]


def test_minimization_balances_modes():
    hist = []
    for i in range(40):
        hist.append(allocate("V2", hist, seed=i))
    lead, peer = Counter(h["lead"] for h in hist), Counter(h["peer"] for h in hist)
    assert all(h["lead"] != h["peer"] for h in hist) and len(CONDITIONS) == 20
    assert max(lead.values()) - min(lead.values()) <= 2 and max(peer.values()) - min(peer.values()) <= 2


def test_persona_card_from_versioned_prompt(monkeypatch):
    scn = {**build_cached("dl.dev.saas"), "condition": {"lead": "competing", "peer": "avoiding"}}
    for flag in ("0", "1"):
        monkeypatch.setenv("DIALOGUE_HARNESS", flag)
        lead, peer = persona_system(scn, "lead"), persona_system(scn, "peer")
        assert MODES["competing"]["rules"][0] in lead and MODES["avoiding"]["rules"][0] in peer
        assert "search_company_docs" in lead and "[절대 규칙]" in peer
        assert not re.search(r"\$\{?[A-Za-z_]", lead), "no unrendered $placeholder"  # LaTeX like $22\%$ is fine
    assert "$22\\%$" in lead and "$$\\text{재참여율}" in lead, "$$ in the template renders as a literal $"
    assert {"persona", "persona_dialogue", "director", "director_dialogue", "ledger", "observer", "summarize"} <= set(instructions.versions())


def test_detector_rules():
    good = rule_estimate(features("도현님 입장도 이해해요. 다만 제가 오늘 오후 3시까지 필수 항목만 검토 요청할게요."))
    blame = rule_estimate(features("도현님이 늦게 줘서 이렇게 된 거잖아요."))
    avoid = rule_estimate(features("네 알아서 해주세요"))
    assert good["focus"] == "solution" and "C03" in good["competencies"]
    assert blame["focus"] == "blame" and blame["cooperativeness"] < good["cooperativeness"]
    assert avoid["assertiveness"] <= 2 and "hedge_avoid" in avoid["flags"]


def test_kappa_tki_and_boilerplate():
    assert kappa([(True, True), (False, False)] * 5) == 1.0
    assert tki_label(4.5, 1.5) == "competing" and tki_label(3, 3) == "compromising"
    assert strip_boilerplate("좋은 계획이네요. 필요한 부분에서 제가 도와드릴 수 있다면 언제든지 말씀해 주세요.") == "좋은 계획이네요."


def test_clean_line_keeps_markdown_line_breaks():
    md = "두 안을 견줘 보면:\n\n| 안 | 일정 |\n|---|---|\n| 부분 검토 | 금요일 |\n\n- **필수 항목**만 먼저\n- $22\\%$ 기준"
    assert clean_line(md) == md
    assert clean_line(md + "\n필요하시면 언제든지 말씀해 주세요.") == md  # boilerplate on its own last line goes
    assert clean_line("[한서윤] 첫 줄.\n둘째 줄. 필요한 부분이 있으면 언제든 말씀해 주세요.") == "첫 줄.\n둘째 줄."
    assert clean_line("음...") == "음..."


def test_context_budget_folds_old_messages():
    msgs = [{"speaker": "user", "text": "가" * 300, "idx": i} for i in range(40)]
    out = context.transcript(msgs, {"user": "지원자"}, budget=3000)
    assert out.startswith("(앞선 대화") and len(out) < 4500


def test_guardrails_pii_and_output_policy():
    masked = guardrails.mask({"t": "연락처 010-1234-5678, a.b@corp.dev"})
    assert "010" not in masked["t"] and "@" not in masked["t"]
    assert guardrails.violates_output_policy("이번 평가 결과는 좋아요")
    assert not guardrails.violates_output_policy("검토 일정부터 확인할게요")
    with pytest.raises(guardrails.ApprovalRequired):
        guardrails.require_approval("business.save_report", approved=False)


def test_loop_limits():
    lim, counts = Limits(), Counter()
    for _ in range(3):
        lim.check_tool(counts, "rag.search_docs")
    with pytest.raises(LimitExceeded):
        lim.check_tool(counts, "rag.search_docs")


def test_recovery_retries_then_falls_back(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "primary")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "fallback")
    real_sleep = asyncio.sleep
    monkeypatch.setattr(recovery.asyncio, "sleep", lambda s: real_sleep(0))
    calls = []

    class E503(Exception):
        status_code = 503

    async def make(model):
        calls.append(model)
        if model == "primary":
            raise E503()
        return "ok"

    assert asyncio.run(recovery.with_recovery(make)) == "ok"
    assert calls == ["primary"] * 3 + ["fallback"]

    async def bad(model):
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        asyncio.run(recovery.with_recovery(bad))


def test_tool_events_never_carry_evaluation_args():
    from app.harness.tools import _summary
    s = _summary({"session_id": "abc", "observations": [{"quote": "비밀"}], "dialogue": {"summary": "장부"}, "report": {"C01": 1}, "milestone_idx_after": 1})
    assert s["session_id"] == "abc" and s["milestone_idx_after"] == 1
    assert "비밀" not in json.dumps(s, ensure_ascii=False) and "장부" not in json.dumps(s, ensure_ascii=False)
