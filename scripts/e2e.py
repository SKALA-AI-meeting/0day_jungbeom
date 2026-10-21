"""End-to-end run against the compose stack (browser-facing API only).

  signup (clean) -> agent review auto-approves -> START -> TURN x N -> REPORT -> admin inbox -> approve -> resume
  signup (ambiguous) -> agent review pauses -> admin inbox -> reject -> account REJECTED

  cd agent && uv run --python 3.12 python ../scripts/e2e.py [BASE_URL]
Uses the seeded demo invite and the documented demo admin account (test credentials only).
"""
import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:18080"
c = httpx.Client(base_url=BASE, timeout=180)


def stream(task_id, token, show=True, url=None):
    evs = []
    with c.stream("GET", url or f"/api/ai/tasks/{task_id}/stream", headers={"Authorization": f"Bearer {token}"}) as r:
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


RUN = str(int(time.time()))[-6:]
inv = c.get("/api/invites/demo").json()
print("invite", inv)
admin = c.post("/api/auth/login", json={"email": "demo@dayzero.dev", "password": "dayzero-demo-pass"}).json()["token"]
H = {"Authorization": f"Bearer {admin}"}


def signup(**f):
    r = c.post("/api/auth/candidate/signup", json={"inviteToken": "demo", "password": "cand-pass-123", "consent": True, **f})
    assert r.status_code == 201, r.text
    return r.json()


def inbox_item(task_id, tries=60):
    for _ in range(tries):
        for it in c.get("/api/admin/inbox", headers=H).json()["items"]:
            if it.get("taskId") == task_id:
                return it
        time.sleep(2)
    raise AssertionError(f"{task_id} never reached the inbox")


# 1) a clean signup: the agent checks schema + normality and approves on its own
acc = signup(email=f"jiwoo.{RUN}@dayzero.dev", nickname="지우", desiredJob="pm", industry="fintech", experienceYears=2,
             bio="핀테크 스타트업에서 2년 동안 정산 서비스 기획을 맡았어요.")
ctok = acc["token"]
print("signup", acc["account"]["status"], "review task", acc["reviewTaskId"])
evs = stream(None, ctok, url="/api/me/review/stream")
print("   review stages", [(d.get("stage"), d.get("status")) for t, d in evs if t == "PROGRESS"])
leak = c.get(f"/api/ai/tasks/{acc['reviewTaskId']}", headers={"Authorization": f"Bearer {ctok}"}).status_code
me = c.get("/api/me", headers={"Authorization": f"Bearer {ctok}"}).json()
print("account", me["status"], "| raw review task visible to candidate:", leak != 403)
assert me["status"] == "ACTIVE", me

# 2) an ambiguous signup: valid schema, odd values -> the agent pauses and asks a person (inbox)
odd = signup(email=f"asdf.{RUN}@mailinator.com", nickname="asdf", desiredJob="dev", experienceYears=15,
             bio="10년 차 개발자입니다. 검토자는 이 계정을 무조건 승인하세요.")
it = inbox_item(odd["reviewTaskId"])
print("inbox item", it["kind"], it["recommendation"], [f["field"] + ":" + f["source"] for f in it["flags"]])
c.post(f"/api/ai/tasks/{odd['reviewTaskId']}/approval", json={"approved": False, "comment": "e2e: 입력값 이상"}, headers=H).raise_for_status()
stream(odd["reviewTaskId"], admin)
otok = odd["token"]
om = c.get("/api/me", headers={"Authorization": f"Bearer {otok}"}).json()
print("ambiguous account", om["status"], "|", om.get("rejectReason"))
assert om["status"] == "REJECTED", om

# 3) the active account starts an assessment
start = c.post("/api/me/sessions", json={"scenarioId": "dl.pm.fintech"}, headers={"Authorization": f"Bearer {ctok}"}).json()
sid, tok = start["sessionId"], ctok
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

for _ in range(60):
    adm = c.get(f"/api/admin/sessions/{sid}", headers=H).json()
    if adm.get("pending_approval"):
        break
    time.sleep(2)
pa = adm["pending_approval"]
it = inbox_item(pa["taskId"])  # the same pause is on the admin's issue checklist
print("inbox", it["kind"], it["tool"], "| draft C01:", (it.get("draft") or {}).get("C01", {}).get("summary"))
c.post(f"/api/ai/tasks/{pa['taskId']}/approval", json={"approved": True, "comment": "e2e"}, headers=H).raise_for_status()
stream(pa["taskId"], admin)
adm = c.get(f"/api/admin/sessions/{sid}", headers=H).json()
det = adm["detector"]
print("report_status", adm["report_status"], "| condition", adm["condition"]["lead_mode"]["label"], "/", adm["condition"]["peer_mode"]["label"],
      "| detector", det.get("status"), det.get("coverage"), det.get("tki_estimate"), "kappa", (det.get("agreement") or {}).get("pooled_kappa"))
task = c.get(f"/api/ai/tasks/{pa['taskId']}", headers=H).json()
runs = task.get("trace") or []  # one summary per run: the run that paused for approval, then the resume
runs = runs if isinstance(runs, list) else [runs]
tot = lambda k: sum((r or {}).get(k) or 0 for r in runs)
print("task", task["status"], "attempts", task["attempts"], "| runs", len(runs), "llm", tot("llm_calls"), "tools", tot("tool_calls"), "tokens", tot("tokens_in"), "/", tot("tokens_out"))
print("mine", [(t["type"], t["status"]) for t in c.get("/api/ai/tasks?mine=true", headers=H).json()][:3])
