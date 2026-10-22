"""Analytics bundle (api-contract §5): every number the admin screens and the report show, from one session state.

build(state) is pure and deterministic: it reads nothing, writes nothing (computed_at is its only clock value),
never raises on a partial state (a new session, no condition, no detections, a legacy session without artifacts
or state_rev) and returns plain JSON. analytics-mcp (mcp_servers/analytics/server.py) serves it; Spring stores it
as the session's snapshot and the admin screens render from that snapshot, so nothing is counted in the browser.

Before v4 the same numbers came from views.admin_view / admin_row (moved here) plus the admin browser's own
counting (SessionDetail.vue: msCount, msObs, entered, cell, the heatmap total), ported 1:1 below.
"""
from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path

from . import artifacts, charts, detector
from .criteria import AXES, CRITERIA
from .personas import public_mode
from .scenarios import COMPETENCIES, MILESTONES, get_scenario

log = logging.getLogger("dayzero.analytics")

VERSION = 1
SIGNALS = ("positive", "neutral", "risk")
PAINPOINTS = json.loads((Path(__file__).parent / "data" / "painpoints.json").read_text(encoding="utf-8"))


def _dicts(x) -> list[dict]:
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def _int(x, default: int = 0) -> int:
    return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else default


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


# ---------------- moved from views.admin_view / admin_row ----------------
def choice_detail(doc: dict, scn: dict | None) -> dict | None:
    """The value dilemma: axis statistics, why this axis, the options and the candidate's pick with its rationale."""
    if not scn or scn.get("kind") != "dilemma":
        return None
    ax = AXES[scn["axis"]]
    ch = doc.get("choice")
    out = {"axis": ax, "axis_ranking": scn["axis_ranking"], "options": scn["dilemma"]["options"], "pole_of": scn["dilemma"]["pole_of"],
           "population": CRITERIA["meta"], "choice": None}
    if isinstance(ch, dict) and ch:
        opt = next((o for o in scn["dilemma"]["options"] if o["id"] == ch.get("option")), {})
        rationale = next((m.get("text", "") for m in _dicts(doc.get("messages")) if m.get("idx") == ch.get("msg_idx")), "")
        pole = ch.get("pole")
        pole_label = "통합안" if pole == "both" else next((p["label"] for p in ax["poles"] if p["side"] == pole), None)
        out["choice"] = {**ch, "label": opt.get("label"), "pole_label": pole_label, "rationale": rationale}
    return out


def _mode(mode) -> dict:
    try:
        return public_mode(mode)
    except (KeyError, TypeError):
        return {"id": mode, "label": str(mode), "summary": "", "assertive": None, "cooperative": None}


def condition_detail(doc: dict) -> dict | None:
    """The counterpart condition (lead / peer conflict modes) with their public descriptions."""
    c = doc.get("condition")
    if not isinstance(c, dict) or not c:
        return None
    return {**c, "lead_mode": _mode(c.get("lead")), "peer_mode": _mode(c.get("peer"))}


def _row(scn: dict | None, dl: dict | None, cond: dict | None) -> dict:
    """What a dashboard row needs from the catalog (Spring has the rest: id, alias, status, counts, dates)."""
    return {
        "category": scn["category"] if scn else None,
        "scenario_title": scn.get("title") if scn else None,
        "axis": dl["axis"]["name"] if dl else None,
        "choice": dl["choice"]["pole_label"] if dl and dl["choice"] else None,
        "condition": f"{cond['lead_mode']['label']} 팀장 · {cond['peer_mode']['label']} 동료" if cond else None,
    }


# ---------------- ported from the admin browser (SessionDetail.vue) ----------------
def _js_round(x: float) -> int:
    """JavaScript Math.round: the nearest integer, halves toward +inf (Python's round() is half-to-even)."""
    r = math.floor(x)
    return int(r + 1 if x - r >= 0.5 else r)


def offset_seconds(ts, created_at) -> int | None:
    """entered(): seconds from the session start to entering a milestone, never negative."""
    if not (_is_num(ts) and _is_num(created_at)):
        return None
    return max(0, _js_round(ts - created_at))


def clock(s: int) -> str:
    """entered(): '+MM:SS' (minutes are not wrapped at an hour, as before)."""
    return f"+{s // 60:02d}:{s % 60:02d}"


def timeline(doc: dict) -> list[dict]:
    """One entry per milestone: reached (i <= milestone_idx), when it was entered, messages and evidence in it."""
    msgs, obs, mlog = _dicts(doc.get("messages")), _dicts(doc.get("observations")), _dicts(doc.get("milestone_log"))
    cur = _int(doc.get("milestone_idx"))
    out = []
    for i, m in enumerate(MILESTONES):
        e = next((x for x in mlog if x.get("key") == m["key"]), None)  # the first log entry, like Array.find
        off = offset_seconds(e.get("ts"), doc.get("created_at")) if e else None
        ms_obs = [o for o in obs if o.get("milestone") == m["key"]]
        out.append({
            "key": m["key"], "label": m["label"], "reached": i <= cur,
            "entered_idx": e.get("entered_idx") if e else None, "offset_s": off, "offset_label": clock(off) if off is not None else None,
            "messages": sum(1 for x in msgs if x.get("milestone") == m["key"]), "observations": len(ms_obs),
            "obs": [{"id": o.get("id"), "msg_idx": o.get("msg_idx"), "competency": o.get("competency"), "signal": o.get("signal"),
                     "behavior": o.get("behavior")} for o in ms_obs],
        })
    return out


def heatmap(doc: dict) -> dict:
    """Competency x milestone evidence counts by signal (cell()), the row totals and the largest cell."""
    obs = _dicts(doc.get("observations"))
    cells = []
    for c in COMPETENCIES:
        for m in MILESTONES:
            os_ = [o for o in obs if o.get("competency") == c["id"] and o.get("milestone") == m["key"]]
            cells.append({"cid": c["id"], "mkey": m["key"], "n": len(os_), **{s: sum(1 for o in os_ if o.get("signal") == s) for s in SIGNALS}})
    rep = doc.get("report") if isinstance(doc.get("report"), dict) else {}
    counts = {c.get("id"): c.get("count") for c in _dicts(rep.get("competencies"))}
    # the total column: the report's count when there is one (reportComp(cid)?.count), else the evidence count
    totals = {c["id"]: counts[c["id"]] if counts.get(c["id"]) is not None else sum(1 for o in obs if o.get("competency") == c["id"])
              for c in COMPETENCIES}
    return {"competencies": [{"id": c["id"], "name": c["name"]} for c in COMPETENCIES],
            "milestones": [{"key": m["key"], "label": m["label"]} for m in MILESTONES],
            "cells": cells, "totals": totals, "max_n": max((x["n"] for x in cells), default=0)}


# ---------------- detector, figures, bundle ----------------
def _detector(doc: dict, msgs: list[dict], obs: list[dict]) -> dict:
    """Exactly detector.summarize(state); a malformed detection degrades to 'unavailable' instead of failing the bundle."""
    try:
        d = detector.summarize({**doc, "messages": msgs, "observations": obs})
    except Exception:
        log.exception("detector summary failed for session %s", doc.get("id"))
        return {"status": "unavailable", "messages": sum(1 for m in msgs if m.get("speaker") == "user")}
    if isinstance(d.get("sources"), dict):  # built from a set: fix the key order so the same state gives the same JSON
        d["sources"] = dict(sorted(d["sources"].items()))
    return d


def _figures(msgs: list[dict], obs: list[dict], det: dict, checks: list[dict], tl: list[dict]) -> dict:
    """The compact form for prompts and the inbox."""
    ready = det.get("status") == "ready"
    ag = (det.get("agreement") or {}) if ready else {}
    return {
        "messages": len(msgs),
        "candidate_messages": sum(1 for m in msgs if m.get("speaker") == "user"),
        "observations": len(obs),
        "by_signal": {s: sum(1 for o in obs if o.get("signal") == s) for s in SIGNALS},
        "pooled_kappa": ag.get("pooled_kappa") if ready else None,
        # how many (message x competency) judgements κ compares: shown next to κ, so one message's κ = 1 does not read as agreement
        "kappa_n": ag.get("n_judgements") if ready else None,
        "tki_estimate": det.get("tki_estimate") if ready else None,
        "checkpoints": f"{sum(1 for c in checks if c.get('spotted'))}/{len(checks)}" if checks else None,
        "milestones_reached": f"{sum(1 for t in tl if t['reached'])}/{len(tl)}",
    }


def build(state: dict, *, now: float | None = None) -> dict:
    """The analytics bundle (version 1) for one session state from GET /internal/sessions/{id}/state."""
    doc = state if isinstance(state, dict) else {}
    try:
        scn = get_scenario(doc.get("scenario_id") or "")
    except KeyError:
        scn = None
    msgs, obs, notes = _dicts(doc.get("messages")), _dicts(doc.get("observations")), _dicts(doc.get("annotations"))
    arts = _dicts(doc.get("artifacts"))
    dets = doc.get("detections") if isinstance(doc.get("detections"), dict) else {}
    dl, cond = choice_detail(doc, scn), condition_detail(doc)
    det = _detector(doc, msgs, obs)
    checks = artifacts.artifact_checks(doc.get("scenario_id") or "", arts, notes, scn=scn) if scn else []
    tl = timeline(doc)
    bundle = {
        "version": VERSION,
        "session_id": doc.get("id"),
        "computed_at": time.time() if now is None else now,
        "source": {"state_rev": _int(doc.get("state_rev")), "message_count": len(msgs), "observation_count": len(obs),
                   "detection_count": len(dets), "annotation_count": len(notes), "status": doc.get("status"),
                   "milestone_idx": doc.get("milestone_idx")},
        "row": _row(scn, dl, cond),
        "context": {"scenario": scn,
                    "painpoints": PAINPOINTS.get(scn["painpoint_key"]) if scn and scn.get("painpoint_key") else None,
                    # titles for the checkpoint chart (contract shape fields only; bodies stay in Spring's state)
                    "artifacts": [{k: a.get(k) for k in ("id", "kind", "title", "owner")} for a in arts]},
        "timeline": tl,
        "heatmap": heatmap(doc),
        "detector": det,
        "dilemma": dl,
        "condition": cond,
        "artifact_checks": checks,
        "figures": _figures(msgs, obs, det, checks, tl),
    }
    bundle["charts"] = charts.index(bundle)
    # plain JSON, detached from the cached catalog objects (scenario, axes) so a caller can never mutate them
    return json.loads(json.dumps(bundle, ensure_ascii=False, default=str))
