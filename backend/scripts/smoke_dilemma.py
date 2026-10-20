"""Real-LLM smoke run for a value-dilemma session against a running server (default :8765)."""
import json
import sys

import httpx

c = httpx.Client(base_url="http://127.0.0.1:8765", timeout=120)
scn = sys.argv[1] if len(sys.argv) > 1 else "dl.pm.fintech"
choice = sys.argv[2] if len(sys.argv) > 2 else "both"
lines = [
    "현재 기획안은 90% 됐고, 고객사에 약속한 건 금요일이에요. 검토가 꼭 필요한 범위가 어디까지인지 먼저 확인하고 싶어요.",
    "검토팀 일정이 정확히 왜 밀렸는지, 부분 검토가 가능한지도 알아볼게요.",
    "도현님 말씀처럼 지난번엔 문제없었지만, 이번엔 개인정보가 들어가서 조심스러워요. 서윤님, 고객사엔 제가 먼저 상황 공유해도 될까요?",
    "두 분 의견 모두 이해돼요. 일정과 위험을 같이 놓고 정해 보면 좋겠어요.",
    "필수 항목만 먼저 검토받으면 고객 약속도 일부 지키고 위험도 줄일 수 있어서요. 검토팀엔 제가 오늘 바로 요청할게요.",
    "도현님 걱정도 맞아요. 부분 출시 범위를 오늘 오후까지 정리해서 공유하고, 나머지는 화요일 검토 후 바로 낼게요.",
    "정리하면 오늘 검토 요청, 금요일 부분 출시, 다음 주 나머지 출시예요. 일정은 문서에 반영해 둘게요.",
]
s = c.post("/api/sessions", json={"alias": "딜레마테스터", "scenario_id": scn}).json()
print("SCN:", s["scenario"]["category"], "/", s["scenario"]["title"])
who = {"user": "나", "lead": "팀장", "peer": "도현"}
print(f"  [{who[s['messages'][0]['speaker']]}] {s['messages'][0]['text']}")
chosen = False
for t in lines:
    cv = c.get(f"/api/sessions/{s['id']}").json()
    cid = None
    if cv["dilemma"] and not cv["choice"] and not chosen and "필수 항목" in t:
        cid, chosen = choice, True
    with c.stream("POST", f"/api/sessions/{s['id']}/messages", json={"text": t, **({"choice_id": cid} if cid else {})}) as r:
        for ln in r.iter_lines():
            if not ln.startswith("data: "):
                continue
            e = json.loads(ln[6:])
            if e["type"] in ("user_message", "message"):
                m = e["message"]
                print(f"  [{who[m['speaker']]}]{' (선택:' + m['choice'] + ')' if m.get('choice') else ''} {m['text']}")
            elif e["type"] == "milestone":
                print(f"--- {e['key']} ---")
            elif e["type"] == "error":
                print("ERR", e)
c.post(f"/api/sessions/{s['id']}/finish")
adm = c.get(f"/api/admin/sessions/{s['id']}").json()
cond = adm["condition"]
print("CONDITION", cond["lead_mode"]["label"], "팀장 /", cond["peer_mode"]["label"], "동료")
det = adm["detector"]
if det.get("status") == "ready":
    print("DETECTOR", det["coverage"], det["sources"], "A", det["assertiveness"], "C", det["cooperativeness"], det["tki_estimate"], "| kappa", det["agreement"]["pooled_kappa"], {k: v["kappa"] for k, v in det["agreement"]["per_competency"].items()}, "| MAD", det["rules_vs_model_mad"])
else:
    print("DETECTOR", det)
d = adm["dilemma"]
print("AXIS", d["axis"]["name"], "| CHOICE", d["choice"] and d["choice"]["pole_label"], "| status", adm["status"])
for o in adm["observations"]:
    print(f"  {o['competency']} {o['milestone']:11} {o['signal']:8} {o['behavior']}")
