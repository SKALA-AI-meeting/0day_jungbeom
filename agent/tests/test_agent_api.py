from fastapi.testclient import TestClient

from app.agent_api import app

H = {"X-Internal-Key": "test-key"}


def test_internal_key_and_catalog():
    with TestClient(app) as c:
        assert c.get("/agent/meta").status_code == 401
        meta = c.get("/agent/meta", headers=H).json()
        assert [x["id"] for x in meta["competencies"]] == ["C01", "C02", "C03", "C05"]
        assert c.get("/agent/scenarios/dl.pm.fintech", headers=H).status_code == 200
        assert c.get("/agent/scenarios/dl.pm.mars", headers=H).status_code == 404
        assert c.post("/agent/tasks", json={"type": "TURN"}, headers=H).status_code == 400
        h = c.get("/agent/health").json()
        assert h["checkpointer"] == "InMemorySaver" and "persona" in h["prompts"]


def test_views_hide_secrets_from_candidates():
    state = {"id": "s1", "alias": "A", "scenario_id": "dl.pm.fintech", "status": "active", "milestone_idx": 2, "turns_in_milestone": 0,
             "condition": {"stratum": "V2", "lead": "competing", "peer": "avoiding"}, "choice": None, "milestone_log": [], "notes": "",
             "created_at": 0, "messages": [], "observations": [], "detections": {}, "report_status": "none"}
    with TestClient(app) as c:
        cand = c.post("/agent/views/candidate", json=state, headers=H).json()
        assert cand["dilemma"]["options"] and "beats" not in str(cand) and "condition" not in cand
        adm = c.post("/agent/views/admin", json=state, headers=H).json()
        assert adm["condition"]["lead_mode"]["label"] == "경쟁형" and adm["dilemma"]["axis"]["id"] == "V2"
        rows = c.post("/agent/views/admin-rows", json=[{**state, "message_count": 3, "observation_count": 1}], headers=H).json()
        assert rows[0]["axis"] and rows[0]["messages"] == 3


def test_handlers_endpoint_lists_task_types():
    with TestClient(app) as c:
        assert c.get("/agent/handlers").status_code == 401
        rows = c.get("/agent/handlers", headers=H).json()
        assert {r["type"]: r["resumable"] for r in rows} == {"START": False, "TURN": False, "REPORT": True, "ACCOUNT_REVIEW": True}
        assert all(set(r) == {"type", "resumable", "description"} for r in rows)


def test_admin_view_checks_artifacts_and_candidate_view_stays_clean():
    from app import artifacts
    from app.scenarios import get_scenario

    planted = artifacts.catalog(get_scenario("conflict"), "conflict")
    line = planted[2]["checkpoints"][0]["line"]
    note = {"id": 7, "artifact_id": "a3", "anchor": {"line_start": line, "line_end": line, "quote": None}, "kind": "risk",
            "text": "정렬 방향이 반대예요.", "msg_idx": 3, "created_at": 0}
    state = {"id": "s2", "alias": "B", "scenario_id": "conflict", "status": "active", "milestone_idx": 1, "turns_in_milestone": 0,
             "condition": {"stratum": "C", "lead": "competing", "peer": "avoiding"}, "choice": None, "milestone_log": [], "notes": "",
             "created_at": 0, "messages": [], "observations": [], "detections": {}, "report_status": "none",
             "artifacts": artifacts.without_checkpoints(planted), "annotations": [note], "dialogue": None}
    with TestClient(app) as c:
        adm = c.post("/agent/views/admin", json=state, headers=H).json()
        hit = next(x for x in adm["artifact_checks"] if x["artifact_id"] == "a3" and x["line"] == line)
        assert hit["spotted"] and hit["annotation_ids"] == [7] and len(adm["artifact_checks"]) == 5
        cand = c.post("/agent/views/candidate", json=state, headers=H).json()
        assert "artifact_checks" not in cand and "checkpoints" not in str(cand) and hit["issue"] not in str(cand)
