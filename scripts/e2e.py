"""End-to-end run against the compose stack (browser-facing API only): invite -> START -> TURN x N -> REPORT approval.

  cd agent && uv run --python 3.12 python ../scripts/e2e.py [BASE_URL]
Uses the seeded demo invite and the documented demo admin account (test credentials only).
"""
import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:18080"
c = httpx.Client(base_url=BASE, timeout=180)


def stream(task_id, token, show=True):
    evs = []
    with c.stream("GET", f"/api/ai/tasks/{task_id}/stream", headers={"Authorization": f"Bearer {token}"}) as r:
        r.raise_for_status()
        block = {"type": None, "data": ""}
        for line in r.iter_lines():
            if line.startswith("event:"):
                block["type"] = line[6:].strip()
            elif line.startswith("data:"):
                block["data"] += line[5:]
            elif line == "" and block["type"]:
                evs.append((block["type"], json.loads(block["data"] or "{}")))
                block = {"type": None, "data": ""}
    if show:
        kinds = {}
        for t, _ in evs:
            kinds[t] = kinds.get(t, 0) + 1
        tools = [d.get("tool") for t, d in evs if t == "TOOL_START"]
        print(f"   events {kinds} tools {tools}")
    return evs


def say(sid, tok, text, choice=None):
    r = c.post("/api/ai/tasks", json={"type": "TURN", "sessionId": sid, "text": text, "choiceId": choice}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 202, r.text
    print(f"[나]{' (선택 ' + choice + ')' if choice else ''} {text}")
    evs = stream(r.json()["taskId"], tok)
    done = [d for t, d in evs if t in ("DONE", "FAILED")][-1]
    for m in done.get("new_messages", []):
        src = f"  ⟨근거: {', '.join(s['doc'] + ' ' + s['section'] for s in m['sources'])}⟩" if m.get("sources") else ""
        print(f"   [{m['speaker']}·{m['milestone']}] {m['text']}{src}")
    return done


inv = c.get("/api/invites/demo").json()
print("invite", inv)
start = c.post("/api/invites/demo/sessions", json={"alias": "E2E", "scenarioId": "dl.pm.fintech"}).json()
sid, tok = start["sessionId"], start["token"]
print("session", sid)
evs = stream(start["startTaskId"], tok)
m0 = [d for t, d in evs if t == "DONE"][-1]["messages"][0]
print(f"   [{m0['speaker']}] {m0['text']}  ⟨근거: {m0.get('sources')}⟩")

lines = [
    ("기획안은 90% 됐고 고객사 약속은 금요일이에요. 검토가 꼭 필요한 범위가 어디까지인지 서윤님께 먼저 확인하고 싶어요.", None),
    ("검토팀 일정이 왜 밀렸는지, 부분 검토가 가능한지도 오늘 알아볼게요.", None),
    ("도현님 말씀처럼 지난번엔 문제가 없었지만, 이번엔 계좌 정보가 들어가서 조심스러워요. 도현님은 어떻게 보세요?", None),
    ("두 분 의견을 같이 놓고 일정과 위험을 비교해 볼게요.", None),
    ("필수 항목만 먼저 검토받으면 고객 약속도 일부 지키고 위험도 줄일 수 있어요. 검토팀엔 제가 오늘 요청할게요.", "both"),
    ("부분 출시 범위는 오늘 오후까지 정리해서 공유할게요.", None),
    ("요청은 제가 오늘 3시까지 보내고, 통과 범위는 목요일에 확정할게요. 우려하신 지연은 화요일 전체 검토로 보완할게요.", None),
    ("정리하면 오늘 검토 요청, 금요일 부분 출시, 다음 주 나머지 출시예요.", None),
]
for text, choice in lines:
    done = say(sid, tok, text, choice)
    if done.get("completed"):
        break
view = c.get(f"/api/sessions/{sid}", headers={"Authorization": f"Bearer {tok}"}).json()
print("status", view["status"], "debrief items", len(view.get("debrief") or []))

admin = c.post("/api/auth/login", json={"email": "demo@dayzero.dev", "password": "dayzero-demo-pass"}).json()["token"]
H = {"Authorization": f"Bearer {admin}"}
for _ in range(60):
    adm = c.get(f"/api/admin/sessions/{sid}", headers=H).json()
    if adm.get("pending_approval"):
        break
    time.sleep(2)
pa = adm["pending_approval"]
print("approval required for", pa["draft"].get("tool"), "| draft C01:", (pa["draft"].get("draft") or {}).get("C01", {}).get("summary"))
c.post(f"/api/ai/tasks/{pa['taskId']}/approval", json={"approved": True, "comment": "e2e"}, headers=H).raise_for_status()
stream(pa["taskId"], admin)
adm = c.get(f"/api/admin/sessions/{sid}", headers=H).json()
det = adm["detector"]
print("report_status", adm["report_status"], "| condition", adm["condition"]["lead_mode"]["label"], "/", adm["condition"]["peer_mode"]["label"],
      "| detector", det.get("status"), det.get("coverage"), det.get("tki_estimate"), "kappa", (det.get("agreement") or {}).get("pooled_kappa"))
task = c.get(f"/api/ai/tasks/{pa['taskId']}", headers=H).json()
tr = task.get("trace") or {}
print("task", task["status"], "attempts", task["attempts"], "| trace llm", tr.get("llm_calls"), "tools", tr.get("tool_calls"), "tokens", tr.get("tokens_in"), "/", tr.get("tokens_out"))
print("mine", [(t["type"], t["status"]) for t in c.get("/api/ai/tasks?mine=true", headers=H).json()][:3])
