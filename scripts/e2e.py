"""End-to-end run against the compose stack (browser-facing API only).

  signup (clean) -> agent review auto-approves -> START -> TURN x N -> REPORT -> admin inbox -> approve -> resume
  signup (ambiguous) -> agent review pauses -> admin inbox -> reject -> account REJECTED
  after START: shared artifacts -> a line markup on a planted checkpoint of the code artifact + a quote markup
  -> admin detail has annotations, artifact_checks (spotted) and the dialogue ledger; the candidate view has none of them
  analytics snapshot (api-contract §5): after the first turn the background refresh leaves it fresh -> a markup makes it
  stale -> an ANALYTICS task (analytics-mcp -> business.save_analytics) makes it fresh with the markup in artifact_checks;
  the approved report carries figures + SVG charts (one render_charts call: the same-tool cap holds) and the snapshot is fresh afterwards;
  the admin's task history leaves the ANALYTICS refreshes out and the inbox badge count matches the list

  cd agent && uv run --python 3.12 python ../scripts/e2e.py [BASE_URL]
Uses the seeded demo invite and the documented demo admin account (test credentials only).
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from app import artifacts as catalog  # noqa: E402  (agent-side catalog: where the planted checkpoints are)

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


def no_secrets(view, where):
    dumped = json.dumps(view, ensure_ascii=False)
    for key in ('"dialogue"', '"checkpoints"', '"artifact_checks"', '"observations"', '"analytics"', '"figures"', '"charts"', "<svg"):
        assert key not in dumped, f"{where} leaks {key}"


def admin_detail():
    r = c.get(f"/api/admin/sessions/{sid}", headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def wait_fresh(tries=45):
    """The snapshot the agent stores after START / TURN (quiet background refresh) or an ANALYTICS task."""
    for _ in range(tries):
        d = admin_detail()
        if d["analytics_status"] == "fresh":
            return d
        time.sleep(2)
    return d


def check_of(bundle, artifact_id, line_no):
    return next((ck for ck in bundle.get("artifact_checks") or [] if ck["artifact_id"] == artifact_id and ck["line"] == line_no), None)


# 3b) shared work items: mark a planted problem in the code artifact by line, and quote a line of another item
CT = {"Authorization": f"Bearer {tok}"}
view = c.get(f"/api/sessions/{sid}", headers=CT).json()
no_secrets(view, "candidate view")
assert view["start_status"] == "done", view["start_status"]
arts = {a["id"]: a for a in view["artifacts"]}
print("artifacts", [(a["id"], a["kind"], a["owner"], a["title"]) for a in view["artifacts"]])
code = next(a for a in view["artifacts"] if a["kind"] == "code")
planted = catalog.checkpoints(view["scenario"]["id"])  # {artifact_id: [{line, issue}]}, agent-only
line = planted[code["id"]][0]["line"]
code_line = code["body"].split("\n")[line - 1].strip()


def annotate(artifact_id, anchor, kind, text, expect=201):
    r = c.post(f"/api/sessions/{sid}/annotations", json={"artifactId": artifact_id, "anchor": anchor, "kind": kind, "text": text}, headers=CT)
    assert r.status_code == expect, (r.status_code, r.text)
    return r.json() if expect == 201 else None


a_line = annotate(code["id"], {"lineStart": line, "lineEnd": line}, "risk", "출시 조건에 개인정보·보안 검토가 없어 보여요. 금요일 출시 전에 확인이 필요해요.")
other = next(a for a in view["artifacts"] if a["id"] != code["id"] and a["kind"] == "design") if any(a["kind"] == "design" for a in view["artifacts"]) else view["artifacts"][0]
qline = planted.get(other["id"], [{"line": 1}])[0]["line"]
quote = other["body"].split("\n")[qline - 1].strip()[:200]
a_quote = annotate(other["id"], {"quote": quote}, "question", "이 부분은 누가 언제 정하는지 정해져 있나요?")
annotate(other["id"], {"quote": "본문에 없는 문장이에요"}, "question", "없는 인용", expect=400)  # quote must be a substring
print("markups", (a_line["id"], a_line["anchor"]), (a_quote["id"], a_quote["anchor"]["quote"][:30]), "| code line:", code_line)

lines = [
    (f"[{code['title'][:20]} L{line}] 에 마크업 남겼어요. 출시 조건에 보안 검토가 빠진 것 같은데 도현님 확인 부탁드려요. 기획안은 90% 됐고 고객사 약속은 금요일이에요. 검토가 꼭 필요한 범위가 어디까지인지 서윤님께 먼저 확인하고 싶어요.", None),
    ("검토팀 일정이 왜 밀렸는지, 부분 검토가 가능한지도 오늘 알아볼게요.", None),
    ("도현님 말씀처럼 지난번엔 문제가 없었지만, 이번엔 계좌 정보가 들어가서 조심스러워요. 도현님은 어떻게 보세요?", None),
    ("두 분 의견을 같이 놓고 일정과 위험을 비교해 볼게요.", None),
    ("필수 항목만 먼저 검토받으면 고객 약속도 일부 지키고 위험도 줄일 수 있어요. 검토팀엔 제가 오늘 요청할게요.", "both"),
    ("부분 출시 범위는 오늘 오후까지 정리해서 공유할게요.", None),
    ("요청은 제가 오늘 3시까지 보내고, 통과 범위는 목요일에 확정할게요. 우려하신 지연은 화요일 전체 검토로 보완할게요.", None),
    ("정리하면 오늘 검토 요청, 금요일 부분 출시, 다음 주 나머지 출시예요.", None),
]
say(sid, tok, *lines[0])

# 3c) analytics snapshot (api-contract §5): fresh after the turn's background refresh -> a markup makes it stale ->
#     an ANALYTICS task recomputes it through analytics-mcp and stores it (business.save_analytics) -> fresh again
adm = wait_fresh()
assert adm["analytics_status"] == "fresh", f"background refresh after the turn: {adm['analytics_status']} {adm.get('analytics_task')}"
rev0 = adm["analytics"]["source"]["state_rev"]
marked = {(code["id"], line), (other["id"], qline)}
target = next(((aid, cp["line"]) for aid, cps in planted.items() for cp in cps
               if all(aid != m_aid or abs(cp["line"] - m_line) > 1 for m_aid, m_line in marked)), None)
assert target, planted
before = check_of(adm["analytics"], *target)
assert before and not before["spotted"], before
t_art = arts[target[0]]
a_late = annotate(target[0], {"lineStart": target[1], "lineEnd": target[1]}, "question",
                  "이 줄은 근거가 어디서 왔는지 확인하고 싶어요.")
adm = admin_detail()
print("analytics after markup", adm["analytics_status"], "| snapshot rev", adm["analytics"]["source"]["state_rev"], "(was", rev0, ") < session rev", adm["state_rev"])
assert adm["analytics_status"] == "stale", adm["analytics_status"]
assert not check_of(adm["analytics"], *target)["spotted"], "the stored snapshot is the older one until it is recomputed"
denied = c.post("/api/ai/tasks", json={"type": "ANALYTICS", "sessionId": sid}, headers=CT).status_code
assert denied == 403, f"candidate asked for ANALYTICS: {denied}"
r = c.post("/api/ai/tasks", json={"type": "ANALYTICS", "sessionId": sid}, headers=H)
assert r.status_code == 202, r.text
atask = r.json()
evs = stream(atask["taskId"], admin)
assert [t for t, _ in evs][-1] == "DONE", evs[-1]
tools_used = [d.get("tool") for t, d in evs if t == "TOOL_START"]
assert "analytics.session_analytics" in tools_used and "business.save_analytics" in tools_used, tools_used
adm = admin_detail()
after = check_of(adm["analytics"], *target)
print("ANALYTICS", atask, "->", adm["analytics_status"], "| rev", adm["analytics"]["source"]["state_rev"],
      "| check", t_art["title"][:20], f"L{target[1]}", "spotted", after["spotted"], after["annotation_ids"])
assert adm["analytics_status"] == "fresh", adm["analytics_status"]
assert after["spotted"] and a_late["id"] in after["annotation_ids"], after

for text, choice in lines[1:]:
    done = say(sid, tok, text, choice)
    if done.get("completed"):
        break
view = c.get(f"/api/sessions/{sid}", headers={"Authorization": f"Bearer {tok}"}).json()
print("status", view["status"], "debrief items", len(view.get("debrief") or []))
no_secrets(view, "candidate view (after turns)")
assert sum(len(a["annotations"]) for a in view["artifacts"]) == 3, "candidate sees its own markups"
assert c.get(f"/api/ai/tasks/{atask['taskId']}", headers=CT).status_code == 403, "ANALYTICS tasks are for the company"

adm = admin_detail()
notes = {n["id"] for a in adm["artifacts"] for n in a["annotations"]}
assert {a_line["id"], a_quote["id"], a_late["id"]} <= notes, notes
checks = (adm.get("analytics") or {}).get("artifact_checks") or []
spotted = [ck for ck in checks if ck["spotted"]]
print("artifact_checks", len(checks), "spotted", [(ck["artifact_id"], ck["line"], ck["annotation_ids"]) for ck in spotted])
assert any(ck["artifact_id"] == code["id"] and ck["line"] == line and a_line["id"] in ck["annotation_ids"] for ck in spotted), checks
led = adm.get("dialogue") or {}
print("ledger", {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in led.items() if k in ("version", "issues", "commitments", "positions", "markups_seen", "cited")},
      "| summary:", (led.get("summary") or "")[:80])
assert led.get("version") == 1 and (led.get("issues") or led.get("commitments") or led.get("summary") or led.get("positions")), led
assert {str(a_line["id"]), str(a_quote["id"])} & set(led.get("markups_seen") or []), "the turn after the markups folded them into the ledger"

for _ in range(60):
    adm = c.get(f"/api/admin/sessions/{sid}", headers=H).json()
    if adm.get("pending_approval"):
        break
    time.sleep(2)
pa = adm["pending_approval"]
it = inbox_item(pa["taskId"])  # the same pause is on the admin's issue checklist
print("inbox", it["kind"], it["tool"], "| draft C01:", (it.get("draft") or {}).get("C01", {}).get("summary"))
# the person approves the numbers and charts that will be published (analytics-mcp, drawn in the report graph's analyze)
print("   figures", it.get("figures"), "| charts", [ch["chart_id"] for ch in it.get("charts") or []])
assert it.get("figures") and it.get("charts"), "the approval card carries figures and charts"
assert pa["draft"].get("charts") and all(ch["svg"].lstrip().startswith("<svg") for ch in pa["draft"]["charts"]), "draft charts are SVG"
c.post(f"/api/ai/tasks/{pa['taskId']}/approval", json={"approved": True, "comment": "e2e"}, headers=H).raise_for_status()
stream(pa["taskId"], admin)
adm = admin_detail()
rep, an = adm["report"] or {}, adm["analytics"] or {}
charts = rep.get("charts") or []
print("report figures", rep.get("figures"), "| charts", [(ch["chart_id"], len(ch["svg"])) for ch in charts], "| analytics_rev", rep.get("analytics_rev"))
assert rep.get("figures") and rep["figures"].get("observations") is not None, rep.get("figures")
assert charts and {ch["chart_id"] for ch in charts} <= {"timeline", "heatmap", "tki", "checkpoints"}, charts
for ch in charts:
    svg = ch["svg"]
    assert svg.lstrip().startswith("<svg") and "<script" not in svg and "foreignObject" not in svg, ch["chart_id"]
print("analytics after the report", adm["analytics_status"], "| rev", an.get("source", {}).get("state_rev"), "| figures", an.get("figures"))
assert adm["analytics_status"] == "fresh", (adm["analytics_status"], adm.get("analytics_task"))
det, cond = an["detector"], an["condition"]
print("report_status", adm["report_status"], "| condition", cond["lead_mode"]["label"], "/", cond["peer_mode"]["label"],
      "| detector", det.get("status"), det.get("coverage"), det.get("tki_estimate"), "kappa", (det.get("agreement") or {}).get("pooled_kappa"))
rows = {r["id"]: r for r in c.get("/api/admin/sessions", headers=H).json()}
print("dashboard row", {k: rows[sid].get(k) for k in ("category", "axis", "choice", "condition", "analytics_status")})
assert rows[sid]["category"] == an["row"]["category"] and rows[sid]["analytics_status"] == "fresh", rows[sid]
task = c.get(f"/api/ai/tasks/{pa['taskId']}", headers=H).json()
runs = task.get("trace") or []  # one summary per run: the run that paused for approval, then the resume
runs = runs if isinstance(runs, list) else [runs]
tot = lambda k: sum((r or {}).get(k) or 0 for r in runs)
print("task", task["status"], "attempts", task["attempts"], "| runs", len(runs), "llm", tot("llm_calls"), "tools", tot("tool_calls"), "tokens", tot("tokens_in"), "/", tot("tokens_out"))
per_run = [Counter(s["name"] for s in (r or {}).get("spans") or [] if s.get("kind") == "tool") for r in runs]
print("report tools per run", [dict(x) for x in per_run])
assert any(x["analytics.render_charts"] for x in per_run) and not any(x["analytics.render_chart"] for x in per_run), per_run
assert all(n <= 3 for x in per_run for name, n in x.items() if not name.startswith("business.")), "same-tool cap (3) holds"
mine = c.get("/api/ai/tasks?mine=true", headers=H).json()
print("mine", [(t["type"], t["status"]) for t in mine][:3])
assert not any(t["type"] == "ANALYTICS" for t in mine), "derived ANALYTICS tasks stay out of the admin's task history"
assert c.get("/api/admin/inbox/count", headers=H).json()["count"] == c.get("/api/admin/inbox", headers=H).json()["count"]
