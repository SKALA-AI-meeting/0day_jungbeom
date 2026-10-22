"""Analytics bundle, SVG charts and analytics-mcp (api-contract §5).

Equivalence: for the same state, the bundle must say what the admin screens said before v4 — the old
views.admin_view / admin_row (copied below from 2a40dc7 as the reference) and the admin browser's own counting
(SessionDetail.vue msCount / msObs / entered / cell / the heatmap total, ported below line for line).
"""
import asyncio
import copy
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from app import analytics, artifacts, charts, detector
from app.criteria import AXES, CRITERIA
from app.personas import public_mode
from app.scenarios import COMPETENCIES, MILESTONES, get_scenario
from mcp_servers.analytics import server

NOW = 1_730_000_000.0
SVG_NS = "{http://www.w3.org/2000/svg}"


# ---------------- reference: views.py at 2a40dc7 (before v4), verbatim ----------------
PAINPOINTS = json.loads((Path(analytics.__file__).parent / "data" / "painpoints.json").read_text(encoding="utf-8"))


def old_choice_detail(doc: dict, scn: dict) -> dict | None:
    if scn.get("kind") != "dilemma":
        return None
    ax = AXES[scn["axis"]]
    ch = doc.get("choice")
    out = {"axis": ax, "axis_ranking": scn["axis_ranking"], "options": scn["dilemma"]["options"], "pole_of": scn["dilemma"]["pole_of"],
           "population": CRITERIA["meta"], "choice": None}
    if ch:
        opt = next(o for o in scn["dilemma"]["options"] if o["id"] == ch["option"])
        rationale = next((m["text"] for m in doc.get("messages") or [] if m["idx"] == ch.get("msg_idx")), "")
        pole_label = "통합안" if ch["pole"] == "both" else next(p["label"] for p in ax["poles"] if p["side"] == ch["pole"])
        out["choice"] = {**ch, "label": opt["label"], "pole_label": pole_label, "rationale": rationale}
    return out


def old_condition_detail(doc: dict) -> dict | None:
    c = doc.get("condition")
    if not c:
        return None
    return {**c, "lead_mode": public_mode(c["lead"]), "peer_mode": public_mode(c["peer"])}


def old_admin_row(doc: dict) -> dict:
    scn = get_scenario(doc["scenario_id"])
    det = old_choice_detail(doc, scn)
    cond = old_condition_detail(doc)
    return {
        "id": doc["id"],
        "alias": doc["alias"],
        "category": scn["category"],
        "scenario_id": doc["scenario_id"],
        "axis": det["axis"]["name"] if det else None,
        "choice": det["choice"]["pole_label"] if det and det["choice"] else None,
        "condition": f"{cond['lead_mode']['label']} 팀장 · {cond['peer_mode']['label']} 동료" if cond else None,
        "status": doc["status"],
        "milestone_idx": doc["milestone_idx"],
        "messages": doc.get("message_count", len(doc.get("messages") or [])),
        "observations": doc.get("observation_count", len(doc.get("observations") or [])),
        "report_status": doc.get("report_status", "none"),
        "created_at": doc["created_at"],
    }


def old_admin_view(doc: dict) -> dict:
    scn = get_scenario(doc["scenario_id"])
    return {
        **doc,
        "category": scn["category"],
        "scenario": scn,
        "painpoints": PAINPOINTS.get(scn["painpoint_key"]) if scn.get("painpoint_key") else None,
        "dilemma": old_choice_detail(doc, scn),
        "condition": old_condition_detail(doc),
        "detector": detector.summarize(doc),
        "artifact_checks": artifacts.artifact_checks(doc["scenario_id"], doc.get("artifacts") or [], doc.get("annotations") or [], scn=scn),
    }


# ---------------- reference: the admin browser's counting (SessionDetail.vue), line for line ----------------
def js_ms_count(d, mk):  # d.value.messages.filter((m) => m.milestone === mk).length
    return len([m for m in d["messages"] if m["milestone"] == mk])


def js_ms_obs(d, mk):  # d.value.observations.filter((o) => o.milestone === mk)
    return [o for o in d["observations"] if o["milestone"] == mk]


def js_entered(d, mk):
    e = next((x for x in d["milestone_log"] if x["key"] == mk), None)
    if not e:
        return None
    s = max(0, math.floor(e["ts"] - d["created_at"] + 0.5))  # Math.round
    return f"+{str(s // 60).rjust(2, '0')}:{str(s % 60).rjust(2, '0')}"


def js_cell(d, cid, mk):
    os_ = [o for o in d["observations"] if o["competency"] == cid and o["milestone"] == mk]
    return {"n": len(os_), "positive": len([o for o in os_ if o["signal"] == "positive"]),
            "neutral": len([o for o in os_ if o["signal"] == "neutral"]), "risk": len([o for o in os_ if o["signal"] == "risk"])}


def js_total(d, cid):  # reportComp(c.id)?.count ?? d.observations.filter((o) => o.competency === c.id).length
    rc = next((c for c in ((d.get("report") or {}).get("competencies") or []) if c["id"] == cid), None)
    if rc is not None and rc.get("count") is not None:
        return rc["count"]
    return len([o for o in d["observations"] if o["competency"] == cid])


# ---------------- representative states ----------------
def _base(sid: str, scenario: str, **kw) -> dict:
    s = {"id": sid, "alias": "지원자", "company": "테스트", "scenario_id": scenario, "status": "active", "milestone_idx": 0,
         "turns_in_milestone": 0, "condition": None, "choice": None, "milestone_log": [], "notes": "", "report_status": "none",
         "created_at": 1000.0, "ended_at": None, "messages": [], "observations": [], "detections": {}, "report": None,
         "artifacts": [], "annotations": [], "dialogue": None, "state_rev": 0}
    s.update(kw)
    return s


def _detection(idx: int, a: int, c: int, comps: list[str], milestone: str, model: bool = False, flags=()) -> dict:
    d = {"final": {"assertiveness": a, "cooperativeness": c, "focus": "solution", "competencies": comps, "commitment_specificity": 1},
         "rules": {"assertiveness": max(1, a - 1), "cooperativeness": c, "flags": list(flags)}, "model": None, "source": "rules",
         "model_id": None, "model_error": None, "counts": {}, "milestone": milestone}
    if model:
        d["model"] = {"assertiveness": a, "cooperativeness": c}
        d["source"] = "rules+model"
    return d


def _conversation(milestones: list[str], comps=("C01", "C02", "C03", "C05"), signals=("positive", "neutral", "risk", "positive")):
    """lead / user turns over the given milestones; each candidate message gets 1-3 observations."""
    msgs, obs = [], []
    for i, m in enumerate(milestones):
        speaker = "user" if i % 2 else ("lead" if i % 4 == 0 else "peer")
        msgs.append({"idx": i, "speaker": speaker, "text": f"{m} 단계 메시지 {i}", "milestone": m, "ts": 1000.0 + 37.5 * i})
        if speaker == "user":
            for k in range(1 + i % 3):
                obs.append({"id": f"o{i}_{k}", "competency": comps[(i + k) % len(comps)], "milestone": m, "behavior": f"행동 {i}-{k}",
                            "quote": "…", "signal": signals[(i + 2 * k) % len(signals)], "msg_idx": i})
    return msgs, obs


def new_state() -> dict:
    """Created, START not done yet: no messages, no condition, nothing to count."""
    return _base("new1", "delay")


def mid_state() -> dict:
    """Category scenario, coordinate milestone, artifacts + markups, no detections yet."""
    sid = "conflict"
    planted = artifacts.catalog(get_scenario(sid), sid)
    cps = artifacts.checkpoints(sid)
    msgs, obs = _conversation(["communicate"] * 4 + ["coordinate"] * 3)
    notes = [{"id": 11, "artifact_id": "a3", "anchor": {"line_start": cps["a3"][0]["line"], "line_end": cps["a3"][0]["line"], "quote": None},
              "kind": "risk", "text": "정렬 방향이 반대예요.", "msg_idx": 3, "created_at": 1100.0},
             {"id": 12, "artifact_id": "a1", "anchor": {"line_start": 1, "line_end": 1, "quote": None}, "kind": "question",
              "text": "제목 확인 부탁해요.", "msg_idx": 5, "created_at": 1200.0}]
    return _base("mid1", sid, milestone_idx=1, state_rev=9, condition={"stratum": "C", "lead": "collaborating", "peer": "avoiding"},
                 messages=msgs, observations=obs, artifacts=artifacts.without_checkpoints(planted), annotations=notes,
                 milestone_log=[{"key": "communicate", "entered_idx": 0, "ts": 1000.4}, {"key": "coordinate", "entered_idx": 4, "ts": 1150.5}])


def done_state() -> dict:
    """Value dilemma, completed with a choice, detections (rules and rules+model), a report, artifacts with one checkpoint spotted."""
    sid = "dl.pm.fintech"
    planted = artifacts.catalog(get_scenario(sid), sid)
    cps = artifacts.checkpoints(sid)
    ms = ["communicate"] * 3 + ["coordinate"] * 3 + ["compromise"] * 3 + ["persuade"] * 3
    msgs, obs = _conversation(ms)
    msgs[7]["choice"] = "both"
    dets = {str(m["idx"]): _detection(m["idx"], 2 + m["idx"] % 3, 3 + m["idx"] % 2, [["C01"], ["C02", "C03"], []][m["idx"] % 3], m["milestone"],
                                      model=m["idx"] % 4 == 1, flags=["vague"] if m["idx"] % 3 == 0 else [])
            for m in msgs if m["speaker"] == "user"}
    report = {"status": "ready", "competencies": [{"id": c["id"], "count": sum(1 for o in obs if o["competency"] == c["id"])} for c in COMPETENCIES]}
    notes = [{"id": 21, "artifact_id": "a2", "anchor": {"line_start": cps["a2"][0]["line"], "line_end": cps["a2"][0]["line"] + 1, "quote": None},
              "kind": "risk", "text": "숫자가 이상해요.", "msg_idx": 4, "created_at": 1200.0}]
    return _base("done1", sid, status="completed", milestone_idx=3, state_rev=42, report_status="ready", report=report,
                 condition={"stratum": "V2", "lead": "competing", "peer": "accommodating"},
                 choice={"option": "both", "pole": "both", "msg_idx": 7, "ts": 1262.5}, messages=msgs, observations=obs, detections=dets,
                 artifacts=artifacts.without_checkpoints(planted), annotations=notes,
                 milestone_log=[{"key": m["key"], "entered_idx": i * 3, "ts": 1000.0 + 112.5 * i} for i, m in enumerate(MILESTONES)])


def legacy_state() -> dict:
    """Seeded before artifacts and state_rev existed: no artifacts/annotations/dialogue/state_rev keys at all."""
    msgs, obs = _conversation(["communicate", "communicate", "coordinate"])
    s = _base("old1", "scope", milestone_idx=1, condition={"stratum": "C", "lead": "competing", "peer": "compromising"}, messages=msgs,
              observations=obs, milestone_log=[{"key": "communicate", "entered_idx": 0, "ts": 999.0}])
    for k in ("artifacts", "annotations", "dialogue", "state_rev", "report"):
        s.pop(k)
    return s


STATES = {"new": new_state, "mid": mid_state, "done": done_state, "legacy": legacy_state}


def jrt(x):
    """What Spring / the browser received: the JSON form."""
    return json.loads(json.dumps(x, ensure_ascii=False))


# ---------------- bundle ----------------
def test_new_session_bundle_has_the_contract_shape_and_nothing_to_draw():
    b = analytics.build(new_state(), now=NOW)
    assert list(b) == ["version", "session_id", "computed_at", "source", "row", "context", "timeline", "heatmap", "detector",
                       "dilemma", "condition", "artifact_checks", "figures", "charts"]
    assert b["version"] == 1 and b["session_id"] == "new1" and b["computed_at"] == NOW
    assert b["source"] == {"state_rev": 0, "message_count": 0, "observation_count": 0, "detection_count": 0, "annotation_count": 0,
                           "status": "active", "milestone_idx": 0}
    assert b["row"] == {"category": "일정 지연", "scenario_title": get_scenario("delay")["title"], "axis": None, "choice": None, "condition": None}
    assert b["context"]["painpoints"] == PAINPOINTS["delay"] and b["context"]["artifacts"] == []
    assert [t["reached"] for t in b["timeline"]] == [True, False, False, False]
    assert all(t["entered_idx"] is None and t["offset_s"] is None and t["offset_label"] is None and t["obs"] == [] for t in b["timeline"])
    assert b["heatmap"]["max_n"] == 0 and len(b["heatmap"]["cells"]) == 16 and set(b["heatmap"]["totals"].values()) == {0}
    assert b["detector"] == {"status": "unavailable", "messages": 0} and b["dilemma"] is None and b["condition"] is None
    assert b["figures"] == {"messages": 0, "candidate_messages": 0, "observations": 0, "by_signal": {"positive": 0, "neutral": 0, "risk": 0},
                            "pooled_kappa": None, "kappa_n": None, "tki_estimate": None, "checkpoints": None, "milestones_reached": "1/4"}
    assert [(c["id"], c["available"]) for c in b["charts"]] == [(i, False) for i in charts.CHART_IDS]
    assert all(set(c) == {"id", "type", "title", "caption", "available"} and c["caption"] for c in b["charts"])


def test_completed_session_figures_and_charts():
    st = done_state()
    b = analytics.build(st, now=NOW)
    det = detector.summarize(st)
    users = [m for m in st["messages"] if m["speaker"] == "user"]
    assert b["source"] == {"state_rev": 42, "message_count": 12, "observation_count": len(st["observations"]), "detection_count": len(users),
                           "annotation_count": 1, "status": "completed", "milestone_idx": 3}
    assert b["row"] == {"category": "기획·PM · 핀테크", "scenario_title": get_scenario("dl.pm.fintech")["title"], "axis": AXES["V2"]["name"],
                        "choice": "통합안", "condition": "경쟁형 팀장 · 수용형 동료"}
    f = b["figures"]
    assert f["messages"] == 12 and f["candidate_messages"] == len(users) and f["observations"] == len(st["observations"])
    assert f["by_signal"] == {s: sum(o["signal"] == s for o in st["observations"]) for s in ("positive", "neutral", "risk")}
    assert sum(f["by_signal"].values()) == f["observations"]
    assert f["pooled_kappa"] == det["agreement"]["pooled_kappa"] and f["tki_estimate"] == det["tki_estimate"]
    assert f["kappa_n"] == det["agreement"]["n_judgements"] > 0
    spotted = sum(c["spotted"] for c in b["artifact_checks"])
    assert spotted == 1 and f["checkpoints"] == f"1/{len(b['artifact_checks'])}" and f["milestones_reached"] == "4/4"
    assert all(c["available"] for c in b["charts"]), b["charts"]
    cap = {c["id"]: c["caption"] for c in b["charts"]}
    assert "4/4" in cap["timeline"] and f"κ {det['agreement']['pooled_kappa']}" in cap["agreement"] and "1/" in cap["checkpoints"]
    assert b["dilemma"]["choice"]["pole_label"] == "통합안" and b["dilemma"]["choice"]["rationale"] == st["messages"][7]["text"]
    assert b["context"]["artifacts"] == [{k: a[k] for k in ("id", "kind", "title", "owner")} for a in st["artifacts"]]
    assert "body" not in json.dumps(b["context"]["artifacts"])


def test_mid_session_without_detections():
    b = analytics.build(mid_state(), now=NOW)
    assert b["detector"]["status"] == "unavailable" and b["figures"]["pooled_kappa"] is None and b["figures"]["tki_estimate"] is None
    avail = {c["id"]: c["available"] for c in b["charts"]}
    assert avail == {"timeline": True, "heatmap": True, "tki": False, "agreement": False, "checkpoints": True}
    assert b["dilemma"] is None and b["row"]["condition"] == "협력형 팀장 · 회피형 동료" and b["row"]["axis"] is None
    assert [t["reached"] for t in b["timeline"]] == [True, True, False, False]
    assert b["timeline"][1]["entered_idx"] == 4 and b["timeline"][1]["offset_s"] == 151  # 150.5 s rounds half up, like Math.round
    hit = next(c for c in b["artifact_checks"] if c["artifact_id"] == "a3" and 11 in c["annotation_ids"])
    assert hit["spotted"]


@pytest.mark.parametrize("name", list(STATES))
def test_bundle_equals_the_previous_admin_view(name):
    st = STATES[name]()
    b = analytics.build(st, now=NOW)
    full = {"artifacts": [], "annotations": [], **st}  # the old view was always called with Spring's full state
    old = jrt(old_admin_view(full))
    row = jrt(old_admin_row(full))
    assert b["context"]["scenario"] == old["scenario"]
    assert b["context"]["painpoints"] == old["painpoints"]
    for k in ("dilemma", "condition", "detector", "artifact_checks"):
        assert b[k] == old[k], k
    assert b["row"]["category"] == old["category"] == row["category"]
    for k in ("axis", "choice", "condition"):
        assert b["row"][k] == row[k], k
    assert b["source"]["message_count"] == row["messages"] and b["source"]["observation_count"] == row["observations"]


@pytest.mark.parametrize("name", list(STATES))
def test_timeline_and_heatmap_equal_the_browser_counting(name):
    st = STATES[name]()
    b = analytics.build(st, now=NOW)
    for i, (m, t) in enumerate(zip(MILESTONES, b["timeline"], strict=True)):
        assert (t["key"], t["label"]) == (m["key"], m["label"])
        assert t["messages"] == js_ms_count(st, m["key"])
        assert t["observations"] == len(js_ms_obs(st, m["key"]))
        assert [o["id"] for o in t["obs"]] == [o["id"] for o in js_ms_obs(st, m["key"])]
        assert [(o["competency"], o["signal"], o["behavior"]) for o in t["obs"]] == \
               [(o["competency"], o["signal"], o["behavior"]) for o in js_ms_obs(st, m["key"])]
        assert t["offset_label"] == js_entered(st, m["key"])
        assert t["reached"] == (i <= st["milestone_idx"])
    cells = {(c["cid"], c["mkey"]): c for c in b["heatmap"]["cells"]}
    assert len(cells) == len(COMPETENCIES) * len(MILESTONES)
    for c in COMPETENCIES:
        for m in MILESTONES:
            got = cells[(c["id"], m["key"])]
            assert {k: got[k] for k in ("n", "positive", "neutral", "risk")} == js_cell(st, c["id"], m["key"]), (c["id"], m["key"])
        assert b["heatmap"]["totals"][c["id"]] == js_total(st, c["id"])
    assert b["heatmap"]["max_n"] == max(js_cell(st, c["id"], m["key"])["n"] for c in COMPETENCIES for m in MILESTONES)
    assert b["heatmap"]["competencies"] == [{"id": c["id"], "name": c["name"]} for c in COMPETENCIES]
    assert b["heatmap"]["milestones"] == [{"key": m["key"], "label": m["label"]} for m in MILESTONES]


def test_heatmap_total_follows_the_report_count_like_the_browser():
    st = done_state()
    st["report"]["competencies"][0]["count"] = 99  # the browser showed the report's count when there was one
    st["report"]["competencies"][1]["count"] = None
    b = analytics.build(st, now=NOW)
    assert b["heatmap"]["totals"]["C01"] == 99 == js_total(st, "C01")
    assert b["heatmap"]["totals"]["C02"] == sum(o["competency"] == "C02" for o in st["observations"]) == js_total(st, "C02")


def test_offsets_round_like_javascript():
    assert analytics.offset_seconds(1142.5, 1000.0) == 143  # Python's round(142.5) would give 142
    assert analytics.offset_seconds(1142.49, 1000.0) == 142
    assert analytics.offset_seconds(999.0, 1000.0) == 0  # clock skew never goes negative
    assert analytics.offset_seconds(None, 1000.0) is None and analytics.offset_seconds(1000.0, "x") is None
    assert analytics.clock(0) == "+00:00" and analytics.clock(143) == "+02:23" and analytics.clock(3725) == "+62:05"


@pytest.mark.parametrize("state", [
    {},
    {"id": "x1", "scenario_id": "no.such.scenario", "status": "active", "milestone_idx": 0},
    {"id": "x2", "scenario_id": "delay", "messages": None, "observations": None, "detections": None, "milestone_log": None, "artifacts": None},
    {"id": "x3", "scenario_id": "dl.dev.saas", "condition": {}, "choice": {}, "milestone_idx": None, "created_at": None,
     "milestone_log": [{"key": "communicate", "entered_idx": 0, "ts": 5.0}, "junk"], "messages": [{"idx": 0}], "observations": [{"id": "o"}]},
    {"id": "x4", "scenario_id": "dl.dev.saas", "condition": {"lead": "nobody", "peer": "avoiding"}, "choice": {"option": "zzz", "pole": "q"},
     "detections": {"1": {"final": {"assertiveness": "loud"}}}, "messages": [{"idx": 1, "speaker": "user", "text": "t", "milestone": "communicate"}],
     "observations": [], "report": "not a dict"},
])
def test_partial_states_never_raise(state):
    b = analytics.build(state, now=NOW)
    json.dumps(b, allow_nan=False)
    assert b["version"] == 1 and len(b["timeline"]) == 4 and len(b["charts"]) == len(charts.CHART_IDS)
    for cid in charts.CHART_IDS:
        _assert_safe_svg(charts.render(b, cid))


def test_bundle_is_deterministic_and_detached_from_the_catalog():
    st = done_state()
    a, b = analytics.build(st, now=NOW), analytics.build(copy.deepcopy(st), now=NOW)
    assert json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False)
    assert all(charts.render(a, c) == charts.render(b, c) for c in charts.CHART_IDS)
    title = get_scenario("dl.pm.fintech")["title"]
    a["context"]["scenario"]["title"] = "바뀜"
    a["dilemma"]["axis"]["name"] = "바뀜"
    assert get_scenario("dl.pm.fintech")["title"] == title and AXES["V2"]["name"] != "바뀜"
    assert analytics.build(st)["computed_at"] > 0


# ---------------- charts ----------------
def _assert_safe_svg(svg: str) -> ET.Element:
    root = ET.fromstring(svg)
    assert root.tag == f"{SVG_NS}svg" and root.get("role") == "img" and root.get("aria-label")
    assert root[0].tag == f"{SVG_NS}title" and root[0].text
    assert float(root.get("width")) <= 720 and root.get("viewBox").split()[2] == root.get("width")
    for el in root.iter():
        local = el.tag.split("}")[-1].lower()
        assert local not in ("script", "foreignobject", "iframe", "image", "use", "a", "style"), local
        for k, v in el.attrib.items():
            name = k.split("}")[-1].lower()
            assert not name.startswith("on") and not name.endswith("href"), k
            assert "javascript:" not in v.lower() and "url(" not in v.lower(), (k, v)
    low = svg.lower()  # session text may mention these words, but only escaped (as text, never as markup)
    assert "<script" not in low and "<foreignobject" not in low and "<a " not in low
    return root


def _texts(root: ET.Element) -> str:
    return " ".join(t for el in root.iter() for t in (el.text, el.tail) if t)


@pytest.mark.parametrize("name", list(STATES))
def test_every_chart_is_safe_self_contained_svg(name):
    b = analytics.build(STATES[name](), now=NOW)
    for meta in b["charts"]:
        root = _assert_safe_svg(charts.render(b, meta["id"]))
        assert root[0].text == meta["title"]
        if not meta["available"]:
            assert meta["caption"] in _texts(root) and root.get("height") == "96"


def test_charts_show_the_bundle_numbers():
    b = analytics.build(done_state(), now=NOW)
    tl = _texts(_assert_safe_svg(charts.render(b, "timeline")))
    for t in b["timeline"]:
        assert t["offset_label"] in tl and f"메시지 {t['messages']}개 · 근거 {t['observations']}건" in tl
    hm = _assert_safe_svg(charts.render(b, "heatmap"))
    tips = [el.text for el in hm.iter(f"{SVG_NS}title")]
    c = max(b["heatmap"]["cells"], key=lambda x: x["n"])
    assert any(t.startswith(f"{c['cid']} ") and f": 근거 {c['n']}건" in t for t in tips)
    ag = _texts(_assert_safe_svg(charts.render(b, "agreement")))
    assert charts._v(b["detector"]["agreement"]["pooled_kappa"]) in ag and "Cohen" in ag
    tki = _texts(_assert_safe_svg(charts.render(b, "tki")))
    assert f"{charts.MODE_LABEL[b['detector']['tki_estimate']]}에 가까움" in tki and "팀장" in tki and "동료" in tki
    cp = _texts(_assert_safe_svg(charts.render(b, "checkpoints")))
    assert b["figures"]["checkpoints"] + " 발견" in cp and "발견" in cp and "놓침" in cp


def test_hostile_text_is_escaped():
    st = done_state()
    st["observations"][0]["behavior"] = '<script>alert(1)</script> "x" & \x07bell'
    st["artifacts"][1]["title"] = '<foreignObject><a href="javascript:alert(1)">x</a></foreignObject>'
    st["detections"][next(iter(st["detections"]))]["final"]["focus"] = '" onload="alert(1)'
    b = analytics.build(st, now=NOW)
    for cid in charts.CHART_IDS:
        svg = charts.render(b, cid)
        root = _assert_safe_svg(svg)
        assert "\x07" not in svg
        if cid == "timeline":
            assert '<script>alert(1)</script> "x" & bell' in _texts(root)
    assert "<foreignObject>" in _texts(ET.fromstring(charts.render(b, "checkpoints")))


def test_unknown_chart_and_broken_bundle():
    with pytest.raises(ValueError):
        charts.render({}, "pie")
    broken = analytics.build(done_state(), now=NOW)
    broken["heatmap"]["cells"] = "garbage"
    broken["timeline"][0]["obs"] = [{"signal": "positive"}] * 60  # more dots than fit in four rows: 39 dots and "+21"
    broken["detector"]["points"] = [{"a": "x", "c": None}, {"a": 9, "c": -3, "msg_idx": 1}] + [{"a": 3, "c": 3, "msg_idx": i} for i in range(20)]
    for cid in charts.CHART_IDS:
        _assert_safe_svg(charts.render(broken, cid))
    assert "+21" in charts.render(broken, "timeline")


def test_signal_colours_match_the_ui():
    src = Path(__file__).resolve().parents[2] / "frontend" / "src" / "constants.js"
    if not src.exists():
        pytest.skip("frontend not checked out")
    block = re.search(r"export const SIGNAL = \{(.*?)\n\}", src.read_text(encoding="utf-8"), re.S).group(1)
    ui = {k: (label, color) for k, label, color in re.findall(r"(\w+): \{ label: '([^']+)', color: '(#[0-9a-f]{6})' \}", block)}
    assert ui == charts.SIGNAL


def test_describe_specs():
    assert charts.CHART_IDS == ("timeline", "heatmap", "tki", "agreement", "checkpoints")
    assert all(s["description"] and s["fields"] and s["title"] for s in charts.SPECS)


def test_describe_fields_cover_what_the_charts_read():
    """`fields` (describe_charts) names every bundle key a chart depends on, its availability caption included:
    removing any key a chart does not list (top level, or one level down) never changes its SVG."""
    b = analytics.build(done_state(), now=NOW)
    for spec in charts.SPECS:
        cid, listed = spec["id"], set(spec["fields"])
        base = charts.render(b, cid)
        for top, val in b.items():
            partly = any(f.startswith(top + ".") for f in listed)
            paths = [(top,)] if top not in listed and not partly else []
            if isinstance(val, dict) and top not in listed:
                paths += [(top, k) for k in val if f"{top}.{k}" not in listed]
            for path in paths:
                bb = copy.deepcopy(b)
                (bb if len(path) == 1 else bb[path[0]]).pop(path[-1])
                assert charts.render(bb, cid) == base, f"{cid} reads {'.'.join(path)}, which its fields do not list"


def test_heatmap_shading_is_relative_to_the_busiest_cell_like_the_admin_screen():
    """SessionDetail.vue heat(): 0.15 + n / max_n * 0.7, so the report image and the screen shade the same data alike."""
    b = analytics.build(done_state(), now=NOW)
    mx = b["heatmap"]["max_n"]
    assert mx > 1
    svg = charts.render(b, "heatmap")
    assert charts._heat_fill(mx, mx) == charts._mix(charts.BRAND, 0.85) and f'fill="{charts._heat_fill(mx, mx)}"' in svg
    assert charts._heat_fill(1, 4) == charts._mix(charts.BRAND, 0.15 + 0.7 / 4) and charts._heat_fill(2, 0) == charts._mix(charts.BRAND, 0.85)
    assert charts._heat_steps(0) == [1] and charts._heat_steps(3) == [1, 2, 3] and charts._heat_steps(10) == [1, 4, 7, 10]


# ---------------- analytics-mcp ----------------
def _call(tool: str, args: dict | None = None, *, raise_on_error: bool = True):
    async def go():
        async with Client(server.mcp) as c:
            return await c.call_tool(tool, args or {}, raise_on_error=raise_on_error)
    return asyncio.run(go())


@pytest.fixture
def served(wired):
    """A session in the fake Spring backend that analytics-mcp reads through its MockTransport (restored afterwards)."""
    backend = wired["backend"]
    prev = server._transport
    server.use_transport(httpx.MockTransport(backend.handle))
    st = done_state()
    st["id"] = "mcpdone1"
    backend.sessions[st["id"]] = st
    yield backend, st
    backend.sessions.pop(st["id"], None)
    server.use_transport(prev)


def test_mcp_session_analytics_is_the_bundle(served):
    _, st = served
    got = _call("session_analytics", {"session_id": st["id"]}).data
    want = analytics.build(st, now=NOW)
    assert got.pop("computed_at") > 0 and want.pop("computed_at") == NOW
    assert got == want and got["source"]["state_rev"] == 42


def test_mcp_render_chart(served):
    _, st = served
    for cid in charts.CHART_IDS:
        r = _call("render_chart", {"session_id": st["id"], "chart_id": cid}).data
        assert r["chart_id"] == cid and r["mime"] == "image/svg+xml" and r["available"] is True
        assert r["title"] == charts.SPEC_BY_ID[cid]["title"] and r["caption"]
        _assert_safe_svg(r["svg"])
    st["detections"] = {}
    r = _call("render_chart", {"session_id": st["id"], "chart_id": "tki"}).data
    assert r["available"] is False and "디텍터 판정이 아직 없어요." in r["svg"]


def test_mcp_render_charts_draws_from_one_state_read(served):
    backend, st = served
    seen = []

    def spy(req):
        seen.append(req.url.path)
        return backend.handle(req)
    server.use_transport(httpx.MockTransport(spy))
    r = _call("render_charts", {"session_id": st["id"], "chart_ids": ["tki", "timeline", "tki"]}).data
    assert seen == [f"/internal/sessions/{st['id']}/state"] and r["state_rev"] == 42
    assert [c["chart_id"] for c in r["charts"]] == ["tki", "timeline"], "asked order, once each"
    one = _call("render_chart", {"session_id": st["id"], "chart_id": "timeline"}).data
    assert one.pop("state_rev") == 42 and r["charts"][1] == one
    for c in r["charts"]:
        _assert_safe_svg(c["svg"])
    for bad in ([], ["pie"], list(charts.CHART_IDS) + ["timeline"]):
        with pytest.raises(ToolError, match=r"^400 "):
            _call("render_charts", {"session_id": st["id"], "chart_ids": bad})
    with pytest.raises(ToolError, match=r"^404 "):
        _call("render_charts", {"session_id": "nosuchsession", "chart_ids": ["timeline"]})


def test_mcp_describe_and_tool_listing(served):
    rows = _call("describe_charts").data
    assert [r["id"] for r in rows] == list(charts.CHART_IDS)
    assert all(set(r) == {"id", "type", "title", "description", "fields"} for r in rows)

    async def listing():
        async with Client(server.mcp) as c:
            return await c.list_tools()
    tools_ = {t.name: t for t in asyncio.run(listing())}
    assert set(tools_) == {"session_analytics", "render_chart", "render_charts", "describe_charts"}
    assert all(t.annotations and t.annotations.model_dump(by_alias=True)["readOnlyHint"] and t.description for t in tools_.values())


def test_mcp_errors(served):
    backend, st = served
    with pytest.raises(ToolError, match=r"^404 "):
        _call("session_analytics", {"session_id": "nosuchsession"})
    with pytest.raises(ToolError, match=r"^404 "):
        _call("render_chart", {"session_id": "nosuchsession", "chart_id": "timeline"})
    with pytest.raises(ToolError, match=r"^400 "):
        _call("render_chart", {"session_id": st["id"], "chart_id": "pie"})
    with pytest.raises(ToolError, match=r"^400 "):
        _call("session_analytics", {"session_id": "../internal/x"})

    def down(req):
        raise httpx.ConnectError("refused", request=req)
    server.use_transport(httpx.MockTransport(down))
    with pytest.raises(ToolError, match=r"^503 "):
        _call("session_analytics", {"session_id": st["id"]})
    server.use_transport(httpx.MockTransport(lambda req: httpx.Response(200, json=[1, 2])))
    with pytest.raises(ToolError, match=r"^502 "):
        _call("session_analytics", {"session_id": st["id"]})
    server.use_transport(httpx.MockTransport(backend.handle))
    assert _call("session_analytics", {"session_id": st["id"]}).data["session_id"] == st["id"]


def test_mcp_sends_the_internal_key(served):
    _, st = served
    seen = []

    def spy(req):
        seen.append((req.method, req.url.path, req.headers.get("X-Internal-Key")))
        return httpx.Response(200, json=st)
    server.use_transport(httpx.MockTransport(spy))
    _call("render_chart", {"session_id": st["id"], "chart_id": "heatmap"})
    assert seen == [("GET", f"/internal/sessions/{st['id']}/state", server.KEY)] and server.KEY
