"""The candidate's view over a session state from Spring Boot (scenario catalog lives with the agent).

Spring calls it over internal HTTP (POST /agent/views/candidate); it reads nothing and writes nothing.
The admin side (dilemma, condition, detector, planted artifact checks, timeline, heatmap) is the analytics
bundle (app/analytics.py), served by analytics-mcp and stored by Spring as a snapshot (api-contract §5).
"""
from __future__ import annotations

from .criteria import AXES
from .dilemmas import persuade_beat
from .scenarios import MILESTONE_KEYS, MILESTONES, get_scenario, public_scenario


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
