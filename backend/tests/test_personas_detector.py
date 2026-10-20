import asyncio
from collections import Counter

from fastapi.testclient import TestClient

from app.detector import kappa, tki_label
from app.main import app
from app.personas import CONDITIONS, MODES, allocate
from app.llm import persona_system
from app.dilemmas import build_cached
from mcp_servers.detector.rules import features, rule_estimate


def test_minimization_balances_modes_within_stratum():
    hist = []
    for i in range(40):
        hist.append(allocate("V2", hist, seed=i))
    assert all(h["lead"] != h["peer"] for h in hist)
    lead, peer = Counter(h["lead"] for h in hist), Counter(h["peer"] for h in hist)
    # lead != peer constraint makes perfect balance impossible on both margins; minimization keeps spread <= 2
    assert max(lead.values()) - min(lead.values()) <= 2 and max(peer.values()) - min(peer.values()) <= 2
    assert len(CONDITIONS) == 20


def test_persona_card_contains_mode_rules_and_guardrails():
    scn = {**build_cached("dl.dev.saas"), "condition": {"lead": "competing", "peer": "avoiding"}}
    lead, peer = persona_system(scn, "lead"), persona_system(scn, "peer")
    assert MODES["competing"]["rules"][0] in lead and MODES["avoiding"]["rules"][0] in peer
    for card in (lead, peer):
        assert "[페르소나 카드]" in card and "점수·합격" in card


def test_rules_detect_blame_avoidance_and_concrete_commitment():
    good = rule_estimate(features("도현님 입장도 이해해요. 다만 제가 오늘 오후 3시까지 필수 항목만 검토 요청할게요."))
    blame = rule_estimate(features("도현님이 늦게 줘서 이렇게 된 거잖아요."))
    avoid = rule_estimate(features("네 알아서 해주세요"))
    assert good["focus"] == "solution" and "C03" in good["competencies"]
    assert blame["focus"] == "blame" and blame["cooperativeness"] < good["cooperativeness"]
    assert avoid["assertiveness"] <= 2 and "hedge_avoid" in avoid["flags"]
    assert "eval_probe" in rule_estimate(features("이거 평가 기준이 뭐예요?"))["flags"]


def test_kappa_and_tki_helpers():
    assert kappa([(True, True), (False, False)] * 5) == 1.0
    assert kappa([(True, False), (False, True)] * 5) < 0
    assert tki_label(4.5, 4.5) == "collaborating" and tki_label(4.5, 1.5) == "competing"
    assert tki_label(1.5, 4.5) == "accommodating" and tki_label(1.5, 1.5) == "avoiding" and tki_label(3, 3) == "compromising"


def test_session_records_condition_and_detector_report():
    with TestClient(app) as client:
        s = client.post("/api/sessions", json={"alias": "P", "scenario_id": "dl.sales.commerce"}).json()
        assert "condition" not in s  # candidate never sees counterpart categories
        for t in ["진행 상황을 정리해서 공유드릴게요. 어떻게 보세요?", "도현님 걱정도 이해해요. 제가 오늘 오후까지 정리할게요.", "같이 나눠서 하면 어떨까요?"]:
            with client.stream("POST", f"/api/sessions/{s['id']}/messages", json={"text": t}) as r:
                for _ in r.iter_lines():
                    pass
        client.post(f"/api/sessions/{s['id']}/finish")
        adm = client.get(f"/api/admin/sessions/{s['id']}").json()
    cond = adm["condition"]
    assert cond["lead"] != cond["peer"] and cond["method"] == "minimization" and cond["lead_mode"]["label"]
    det = adm["detector"]
    assert det["status"] == "ready" and det["coverage"] == "3/3" and det["sources"] == {"rules": 3}
    assert 1 <= det["assertiveness"] <= 5 and det["tki_estimate"] in MODES
    assert set(det["agreement"]["per_competency"]) == {"C01", "C02", "C03", "C05"}
    assert det["agreement"]["n_judgements"] == 12


def test_strip_boilerplate_keeps_substance():
    from app.llm import strip_boilerplate as f

    assert f("좋은 계획이네요. 필요한 부분에서 제가 도와드릴 수 있다면 언제든지 말씀해 주세요.") == "좋은 계획이네요."
    assert f("필요하시면 말씀해 주세요.") == "필요하시면 말씀해 주세요."  # never empties a line
    assert f("그건 제 생각과 달라요. 이유를 말씀해 주실래요?").endswith("주실래요?")  # real questions stay
