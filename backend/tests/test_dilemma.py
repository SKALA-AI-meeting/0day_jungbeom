import json

from fastapi.testclient import TestClient

from app.criteria import AXES, INDUSTRIES, JOBS, pick_axis
from app.dilemmas import build_cached
from app.main import app

client = TestClient(app)


def send(sid, text, choice_id=None):
    body = {"text": text, **({"choice_id": choice_id} if choice_id else {})}
    with client.stream("POST", f"/api/sessions/{sid}/messages", json=body) as r:
        return [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: ")]


def test_axes_come_from_data_and_cover_all_combinations():
    assert set(AXES) == {"V1", "V2", "V3", "V4"}
    for ax in AXES.values():  # every axis is a data-backed conflict with a non-trivial split
        assert ax["stats"]["r"] < 0 and ax["stats"]["balance"] >= 0.30
    used = {pick_axis(j, i) for j in JOBS for i in INDUSTRIES}
    assert used == set(AXES), "every selected axis is reachable from some job x industry"
    assert pick_axis("pm", "fintech") == pick_axis("pm", "fintech")  # deterministic


def test_candidate_never_sees_axis_and_choice_drives_persuade_beat():
    sid_scn = "dl.pm.fintech"
    scn = build_cached(sid_scn)
    pub = client.get(f"/api/scenarios/{sid_scn}").json()
    dumped = json.dumps(pub, ensure_ascii=False)
    for secret in ("axis", "pole", "원칙 ↔", "stance", "beats"):
        assert secret not in dumped

    s = client.post("/api/sessions", json={"alias": "D", "scenario_id": sid_scn}).json()
    sid = s["id"]
    assert s["dilemma"] is None  # options hidden before the compromise milestone
    # communicate (2) + coordinate (2) -> compromise
    for i in range(4):
        send(sid, f"상황을 공유드릴게요. 어떻게 하면 좋을까요? {i}")
    cv = client.get(f"/api/sessions/{sid}").json()
    assert cv["milestone_idx"] == 2 and cv["dilemma"] and len(cv["dilemma"]["options"]) == 3

    # without a choice the milestone waits (up to MAX_TURNS_WAITING_CHOICE)
    send(sid, "조금 더 생각해 볼게요.")
    send(sid, "고민 중이에요.")
    assert client.get(f"/api/sessions/{sid}").json()["milestone_idx"] == 2

    evs = send(sid, "고객 영향이 커서 일정을 미루고 먼저 알리는 게 맞다고 봐요.", choice_id="a")
    assert evs[0]["type"] == "user_message" and evs[0]["message"]["choice"] == "a"
    beat = [e for e in evs if e["type"] == "message"][-1]["message"]
    # pole a was chosen -> the persona arguing pole b (peer in V2) pushes back
    assert scn["axis"] == "V2"  # pm x fintech -> 원칙 ↔ 파격 (lead=원칙, peer=파격)
    assert beat["speaker"] == "peer"
    assert beat["milestone"] == "persuade"
    assert send(sid, "두 번 고를래요", choice_id="b")[0]["type"] == "error"  # one choice only

    adm = client.get(f"/api/admin/sessions/{sid}").json()
    assert adm["dilemma"]["choice"]["option"] == "a"
    assert adm["dilemma"]["choice"]["rationale"].startswith("고객 영향")
    assert adm["dilemma"]["axis"]["stats"]["prefer_a"] > 0
    row = next(r for r in client.get("/api/admin/sessions").json() if r["id"] == sid)
    assert row["axis"] == AXES[scn["axis"]]["name"]

    for i in range(2):
        send(sid, f"정리해서 공유할게요 {i}")
    done = client.get(f"/api/sessions/{sid}").json()
    assert done["status"] == "completed"
    assert any(d["key"] == "axis" for d in done["debrief"])  # axis revealed only after the session


def test_bad_dilemma_ids_rejected():
    assert client.post("/api/sessions", json={"alias": "x", "scenario_id": "dl.pm.mars"}).status_code == 400
    assert client.get("/api/scenarios/dl.nope").status_code == 404
