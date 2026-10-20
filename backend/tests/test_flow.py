import json

from fastapi.testclient import TestClient

from app.main import app
from app.scenarios import MILESTONE_KEYS, MIN_TURNS_PER_MILESTONE, SCENARIOS

client = TestClient(app)


def send(sid, text):
    events = []
    with client.stream("POST", f"/api/sessions/{sid}/messages", json={"text": text}) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_meta_has_four_competencies_and_scenarios():
    meta = client.get("/api/meta").json()
    assert [c["id"] for c in meta["competencies"]] == ["C01", "C02", "C03", "C05"]
    assert len(meta["scenarios"]) == len(SCENARIOS) == 4
    # beats / stances must not be exposed to candidates
    assert "beats" not in json.dumps(meta, ensure_ascii=False)
    assert "stance" not in json.dumps(meta, ensure_ascii=False)


def test_full_session_walks_all_milestones_and_builds_report():
    s = client.post("/api/sessions", json={"alias": "지원자A", "scenario_id": "delay"}).json()
    sid = s["id"]
    assert s["milestone_idx"] == 0 and len(s["messages"]) == 1  # opening beat already delivered
    seen_milestones = []
    total_turns = MIN_TURNS_PER_MILESTONE * len(MILESTONE_KEYS)
    for i in range(total_turns):
        evs = send(sid, f"어디까지 진행됐는지 오늘 일정까지 공유드릴게요. 어떻게 하면 좋을까요? ({i})")
        types = [e["type"] for e in evs]
        assert types[0] == "user_message" and types[-1] == "done"
        assert "message" in types
        seen_milestones += [e["key"] for e in evs if e["type"] == "milestone"]
    assert seen_milestones == MILESTONE_KEYS[1:]  # every candidate meets the same situations in order
    cand = client.get(f"/api/sessions/{sid}").json()
    assert cand["status"] == "completed"
    assert "observations" not in cand and "report" not in cand

    adm = client.get(f"/api/admin/sessions/{sid}").json()
    assert adm["report"]["status"] == "ready"
    comps = {c["id"]: c for c in adm["report"]["competencies"]}
    assert set(comps) == {"C01", "C02", "C03", "C05"}
    assert adm["observations"], "observer collected evidence"
    for o in adm["observations"]:  # evidence must quote real candidate messages
        user_texts = [m["text"] for m in adm["messages"] if m["idx"] == o["msg_idx"]]
        assert user_texts and o["quote"] in user_texts[0]
    assert any(c["empty"] for c in comps.values()) or all(c["count"] for c in comps.values())

    # a finished session rejects further turns
    evs = send(sid, "더 이야기해도 되나요?")
    assert evs[0]["type"] == "error"


def test_admin_list_and_painpoints_and_notes():
    s = client.post("/api/sessions", json={"alias": "지원자B", "scenario_id": "conflict"}).json()
    assert client.put(f"/api/sessions/{s['id']}/notes", json={"text": "쟁점: 추천 vs 채팅"}).json()["ok"]
    rows = client.get("/api/admin/sessions").json()
    assert any(r["id"] == s["id"] for r in rows)
    adm = client.get(f"/api/admin/sessions/{s['id']}").json()
    assert adm["notes"].startswith("쟁점")
    assert adm["painpoints"]["points"], "scenario carries researched pain-point sources"
    fin = client.post(f"/api/sessions/{s['id']}/finish").json()
    assert fin["status"] == "completed"
    rep = client.get(f"/api/admin/sessions/{s['id']}").json()["report"]
    assert all(c["empty"] and "기록되지 않음" in c["summary"] for c in rep["competencies"])


def test_unknown_scenario_rejected():
    assert client.post("/api/sessions", json={"alias": "x", "scenario_id": "nope"}).status_code == 400
