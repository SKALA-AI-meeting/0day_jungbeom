"""Pure view functions over a session state from Spring Boot (scenario catalog lives with the agent).

Spring calls these over internal HTTP (POST /agent/views/*); they read nothing and write nothing.
The planted artifact checkpoints (app/artifacts.py) appear only in the admin view, as artifact_checks.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import artifacts, detector
from .criteria import AXES, CRITERIA
from .dilemmas import persuade_beat
from .personas import public_mode
from .scenarios import MILESTONE_KEYS, MILESTONES, get_scenario, public_scenario

PAINPOINTS = json.loads((Path(__file__).parent / "data" / "painpoints.json").read_text(encoding="utf-8"))


def candidate_view(doc: dict) -> dict:
    """Never leak observations, beats, persona stances, the hidden axis, artifact checkpoints or the dialogue ledger.
    (Spring adds the public artifacts + annotations itself.)"""
    scn = get_scenario(doc["scenario_id"])
    debrief = None
    if doc["status"] == "completed":  # PRD 5.5: situations are explained only afterwards
        beats = dict(scn["beats"])
        if scn.get("kind") == "dilemma":
            beats["persuade"] = persuade_beat(scn, doc.get("choice"))
        debrief = [{"key": m["key"], "label": m["label"], "situation": beats[m["key"]]["must_convey"]} for m in MILESTONES]
        if scn.get("kind") == "dilemma":
            ax = AXES[scn["axis"]]
            debrief.append({
                "key": "axis", "label": "가치 딜레마",
                "situation": f"이 상황은 '{ax['name']}' — {ax['question']} — 처럼 사람마다 우선순위가 다른 가치를 보기 위한 것이었어요. "
                "어느 쪽도 정답이 아니며, 선택보다 선택의 근거와 상대를 대하는 방식이 기록됩니다.",
            })
    dilemma = None
    if scn.get("kind") == "dilemma" and doc["milestone_idx"] >= MILESTONE_KEYS.index("compromise"):
        dilemma = {"prompt": scn["dilemma"]["prompt"], "options": [{"id": o["id"], "label": o["label"]} for o in scn["dilemma"]["options"]]}
    return {
        "id": doc["id"],
        "alias": doc["alias"],
        "company": doc.get("company"),
        "status": doc["status"],
        "scenario": public_scenario(scn),
        "milestone_idx": doc["milestone_idx"],
        "milestone_log": doc.get("milestone_log") or [],
        "messages": doc.get("messages") or [],
        "notes": doc.get("notes") or "",
        "dilemma": dilemma,
        "choice": {"option": doc["choice"]["option"]} if doc.get("choice") else None,
        "debrief": debrief,
    }


def choice_detail(doc: dict, scn: dict) -> dict | None:
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


def condition_detail(doc: dict) -> dict | None:
    c = doc.get("condition")
    if not c:
        return None
    return {**c, "lead_mode": public_mode(c["lead"]), "peer_mode": public_mode(c["peer"])}


def admin_row(doc: dict) -> dict:
    scn = get_scenario(doc["scenario_id"])
    det = choice_detail(doc, scn)
    cond = condition_detail(doc)
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


def admin_view(doc: dict) -> dict:
    scn = get_scenario(doc["scenario_id"])
    return {
        **doc,
        "category": scn["category"],
        "scenario": scn,
        "painpoints": PAINPOINTS.get(scn["painpoint_key"]) if scn.get("painpoint_key") else None,
        "dilemma": choice_detail(doc, scn),
        "condition": condition_detail(doc),
        "detector": detector.summarize(doc),
        "artifact_checks": artifacts.artifact_checks(doc["scenario_id"], doc.get("artifacts") or [], doc.get("annotations") or [], scn=scn),
    }
