"""Shared work items: a catalog for every scenario, seeding without checkpoints, business-mcp round trip, admin checks."""
import asyncio
import uuid

import pytest

from app import artifacts, runner, views
from app.criteria import INDUSTRIES, JOBS
from app.harness import guardrails, tools
from app.scenarios import SCENARIOS, get_scenario
from tests.fake_backend import Rejected

ALL = [s["id"] for s in SCENARIOS] + [f"dl.{j}.{i}" for j in JOBS for i in INDUSTRIES]
LANGS = {"pm": {"yaml", "json"}, "dev": {"kotlin", "python"}, "design": {"typescript", "css"}, "sales": {"sql"}, "data": {"sql"}}


def start_msg(sid):
    tid = str(uuid.uuid4())
    return {"taskId": tid, "type": "START", "sessionId": sid, "threadId": f"start:{tid}", "mode": "RUN", "payload": {}}


async def started(backend, scenario):
    sid = uuid.uuid4().hex[:12]
    backend.create(sid, scenario)
    m = start_msg(sid)
    await runner.execute(m)
    await runner.drain_background()
    return sid, m


def test_catalog_covers_every_scenario():
    assert len(ALL) == 29
    bodies = set()
    for sid in ALL:
        scn = get_scenario(sid)
        arts = artifacts.catalog(scn, sid)
        assert [a["kind"] for a in arts] == ["design", "result", "code"] and [a["id"] for a in arts] == ["a1", "a2", "a3"]
        assert arts == artifacts.catalog(dict(scn), sid), "deterministic per scenario id"
        for a in arts:
            assert not artifacts.problems(a), (sid, a["id"], artifacts.problems(a))
            lines = a["body"].split("\n")
            assert 1 <= len(a["checkpoints"]) <= 2 and all(lines[cp["line"] - 1].strip() for cp in a["checkpoints"])
            assert "«" not in a["title"] + a["summary"] + a["body"] + str(a["checkpoints"]), "unfilled template token"
            assert guardrails.mask(a["body"]) == a["body"], "nothing in a body looks like PII to the tool-output mask"
            bodies.add(a["body"])
        design, result, code = arts
        assert design["body"].startswith("# ") and "\n## " in design["body"] and "\n- " in design["body"]
        rows = [ln for ln in result["body"].split("\n") if ln.startswith("|")]
        assert rows[1].startswith("|---") and 4 <= len(rows) - 2 <= 8, (sid, "metric table rows")
        assert sum(ln.startswith("$$") and ln.endswith("$$") and "\\frac" in ln for ln in result["body"].split("\n")) == 1
        assert 15 <= len(code["body"].split("\n")) <= 40 and "```" not in code["body"]
        if scn.get("kind") == "dilemma":  # tied to the situation: company, metric, the personas' work items
            ind, job = INDUSTRIES[scn["industry"]], JOBS[scn["job"]]
            assert ind["company"] in design["body"] and ind["metric"] in result["body"]
            assert code["lang"] in LANGS[scn["job"]] and code["owner"] == "peer"
            assert job["artifact"] in design["title"] + design["body"] or job["peer_artifact"] in code["title"] + code["body"]
    assert len(bodies) == 29 * 3, "every scenario gets its own material"


def test_checkpoints_stay_in_the_agent():
    sid = "dl.pm.fintech"
    arts = artifacts.catalog(get_scenario(sid), sid)
    public = artifacts.without_checkpoints(arts)
    assert all(set(a) == set(artifacts.FIELDS) for a in public) and "issue" not in str(public)
    cps = artifacts.checkpoints(sid)
    assert set(cps) == {"a1", "a2", "a3"} and cps["a2"] == arts[1]["checkpoints"]
    arts[0]["checkpoints"].clear()  # callers get copies
    assert artifacts.checkpoints(sid)["a1"]
    assert artifacts.checkpoints("dl.pm.mars") == {} and artifacts.catalog({}, "nope") == []


def test_start_seeds_artifacts_without_checkpoints(wired):
    backend, sink = wired["backend"], wired["sink"]
    sid, m = asyncio.run(started(backend, "dl.data.health"))
    stored = backend.sessions[sid]["artifacts"]
    planted = artifacts.catalog(get_scenario("dl.data.health"), "dl.data.health")
    assert [a["body"] for a in stored] == [a["body"] for a in planted]
    assert all(set(a) == set(artifacts.FIELDS) for a in stored)
    seen = " ".join(str(e) for t, e in sink.events if t == m["taskId"])
    assert "checkpoints" not in seen and planted[0]["checkpoints"][0]["issue"] not in seen, "nothing planted leaks into SSE"


def test_init_session_strips_and_validates_artifacts(wired):
    backend = wired["backend"]
    cond = {"stratum": "V2", "lead": "competing", "peer": "avoiding"}
    m0 = {"idx": 0, "speaker": "lead", "text": "시작해요.", "milestone": "communicate", "ts": 0}
    planted = artifacts.catalog(get_scenario("delay"), "delay")

    async def main():
        sid = uuid.uuid4().hex[:12]
        backend.create(sid, "delay")
        await tools.call("business", "init_session", {"session_id": sid, "condition": cond, "message": m0, "artifacts": planted})
        bad = uuid.uuid4().hex[:12]
        backend.create(bad, "delay")
        with pytest.raises(tools.ToolFailure, match="400"):
            await tools.call("business", "init_session", {"session_id": bad, "condition": cond, "message": m0,
                                                          "artifacts": [{**planted[0], "kind": "memo"}]})
        with pytest.raises(tools.ToolFailure, match="400"):
            await tools.call("business", "init_session", {"session_id": bad, "condition": cond, "message": m0,
                                                          "artifacts": [planted[0], planted[0]]})
        return sid, bad

    sid, bad = asyncio.run(main())
    assert [set(a) for a in backend.sessions[sid]["artifacts"]] == [set(artifacts.FIELDS)] * 3, "business-mcp drops checkpoints"
    assert backend.sessions[bad]["messages"] == []


def test_artifact_tools_round_trip(wired):
    backend = wired["backend"]

    async def main():
        sid, _ = await started(backend, "dl.dev.fintech")
        n1 = backend.annotate(sid, "a3", line_start=17, kind="risk", text="부분 정산 상태가 이벤트에서 빠져요.")
        backend.user_message(sid, "코드 한번 볼게요.")
        n2 = backend.annotate(sid, "a2", quote="09시까지", kind="question", text="오늘 수치는 부분 집계인가요?")
        listed = await tools.call("business", "list_artifacts", {"session_id": sid})
        one = await tools.call("business", "get_artifact", {"session_id": sid, "artifact_id": "a3"})
        since = await tools.call("business", "list_annotations", {"session_id": sid, "since_idx": 2})
        every = await tools.call("business", "list_annotations", {"session_id": sid})
        text, data = await tools.call_for_model("business", "get_artifact", {"session_id": sid, "artifact_id": "a2"})
        with pytest.raises(tools.ToolFailure, match="404"):
            await tools.call("business", "get_artifact", {"session_id": sid, "artifact_id": "a9"})
        with pytest.raises(tools.ToolFailure, match="400"):
            await tools.call("business", "get_artifact", {"session_id": sid, "artifact_id": "../state"})
        with pytest.raises(tools.ToolFailure, match="400"):
            await tools.call("business", "list_annotations", {"session_id": sid, "since_idx": -1})
        return sid, n1, n2, listed, one, since, every, data

    sid, n1, n2, listed, one, since, every, data = asyncio.run(main())
    body = backend.sessions[sid]["artifacts"][2]["body"]
    assert [a["id"] for a in listed] == ["a1", "a2", "a3"] and listed[2]["line_count"] == len(body.split("\n"))
    assert [a["annotation_count"] for a in listed] == [0, 1, 1] and "body" not in listed[0]
    assert one["body"] == body and [n["id"] for n in one["annotations"]] == [n1["id"]] and "checkpoints" not in one
    assert (n1["msg_idx"], n2["msg_idx"]) == (1, 2) and [n["id"] for n in since] == [n2["id"]] and len(every) == 2
    rendered = artifacts.render_for_model(data)
    assert " 10| | 오늘(09시까지)" in rendered and f"#{n2['id']} “09시까지”" in rendered
    for t in ("list_artifacts", "get_artifact", "list_annotations"):
        assert not guardrails.needs_approval(f"business.{t}"), "read tools never pause for approval"


def test_annotation_rules_mirror_spring(wired):
    backend = wired["backend"]
    sid, _ = asyncio.run(started(backend, "scope"))
    lines = len(backend.sessions[sid]["artifacts"][0]["body"].split("\n"))
    for kw, code in [({"line_start": 0}, 400), ({"line_start": 3, "line_end": 2}, 400), ({"line_start": lines + 1}, 400),
                     ({"quote": "본문에 없는 문장"}, 400), ({}, 400), ({"line_start": 1, "kind": "praise"}, 400),
                     ({"line_start": 1, "text": "   "}, 400)]:
        with pytest.raises(Rejected) as e:
            backend.annotate(sid, "a1", **kw)
        assert e.value.status == code, kw
    with pytest.raises(Rejected) as e:
        backend.annotate(sid, "a7", line_start=1)
    assert e.value.status == 404


def _state(scenario, notes, arts=None):
    planted = artifacts.catalog(get_scenario(scenario), scenario)
    return {"id": "s1", "alias": "A", "scenario_id": scenario, "status": "active", "milestone_idx": 1, "turns_in_milestone": 0,
            "condition": {"stratum": "V3", "lead": "competing", "peer": "avoiding"}, "choice": None, "milestone_log": [], "notes": "",
            "created_at": 0, "messages": [], "observations": [], "detections": {}, "report_status": "none",
            "artifacts": arts if arts is not None else artifacts.without_checkpoints(planted), "annotations": notes,
            "dialogue": {"version": 1, "summary": "요약", "issues": [], "commitments": [], "positions": {}}}


def _note(nid, aid, kind="risk", line_start=None, line_end=None, quote=None):
    return {"id": nid, "artifact_id": aid, "anchor": {"line_start": line_start, "line_end": line_end, "quote": quote},
            "kind": kind, "text": "확인 부탁해요.", "msg_idx": 1, "created_at": 0}


def test_admin_view_marks_spotted_checkpoints():
    sid = "dl.dev.fintech"
    cps = artifacts.checkpoints(sid)
    (a1,), (a2,), (c1, c2) = cps["a1"], cps["a2"], cps["a3"]
    notes = [_note(1, "a3", line_start=c1["line"] + 1, line_end=c1["line"] + 2),  # range touches the line ±1
             _note(2, "a3", "question", line_start=c2["line"] + 2),  # too far
             _note(3, "a2", "question", quote="09시까지"),  # the quote sits on the checkpoint line
             _note(4, "a1", "ok", line_start=a1["line"], line_end=a1["line"])]  # looked at it and said fine: not spotted
    checks = {(c["artifact_id"], c["line"]): c for c in views.admin_view(_state(sid, notes))["artifact_checks"]}
    assert len(checks) == 4
    assert checks[("a3", c1["line"])]["spotted"] and checks[("a3", c1["line"])]["annotation_ids"] == [1]
    assert not checks[("a3", c2["line"])]["spotted"] and checks[("a3", c2["line"])]["annotation_ids"] == []
    assert checks[("a2", a2["line"])]["spotted"] and checks[("a2", a2["line"])]["annotation_ids"] == [3]
    assert not checks[("a1", a1["line"])]["spotted"] and checks[("a1", a1["line"])]["annotation_ids"] == [4]
    assert checks[("a2", a2["line"])]["issue"] == a2["issue"]

    cand = views.candidate_view(_state(sid, notes))
    assert "checkpoints" not in str(cand) and "artifact_checks" not in cand and "dialogue" not in cand
    assert a2["issue"] not in str(cand)


def test_artifact_checks_follow_the_stored_body():
    sid = "workload"
    planted = artifacts.without_checkpoints(artifacts.catalog(get_scenario(sid), sid))
    cp = artifacts.checkpoints(sid)["a1"][0]
    moved = [dict(a) for a in planted]
    moved[0]["body"] = "> 메모: 오전에 업데이트\n" + moved[0]["body"]  # a line was inserted above
    checks = views.admin_view(_state(sid, [_note(9, "a1", line_start=cp["line"] + 1)], arts=moved))["artifact_checks"]
    assert next(c for c in checks if c["artifact_id"] == "a1")["line"] == cp["line"] + 1
    assert next(c for c in checks if c["artifact_id"] == "a1")["spotted"]
    assert views.admin_view(_state(sid, [], arts=[]))["artifact_checks"] == [], "sessions seeded before artifacts existed"
