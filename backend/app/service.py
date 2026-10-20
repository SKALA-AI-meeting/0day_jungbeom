"""Session lifecycle: create, run a turn (streaming events), finish, report."""
import asyncio
import json
import time
from pathlib import Path
from typing import AsyncIterator

from . import store
from .graph import GRAPH
from .llm import BaseLLM, get_llm
from .scenarios import COMPETENCIES, MILESTONES, MILESTONE_KEYS, SCENARIO_BY_ID

PAINPOINTS = json.loads((Path(__file__).parent / "data" / "painpoints.json").read_text(encoding="utf-8"))
_locks: dict[str, asyncio.Lock] = {}
_llm: BaseLLM | None = None


def llm() -> BaseLLM:
    global _llm
    if _llm is None:
        _llm = get_llm()
    return _llm


def set_llm(value: BaseLLM | None) -> None:
    global _llm
    _llm = value


def _lock(session_id: str) -> asyncio.Lock:
    return _locks.setdefault(session_id, asyncio.Lock())


async def create_session(alias: str, scenario_id: str) -> dict:
    scn = SCENARIO_BY_ID[scenario_id]
    beat = scn["beats"]["communicate"]
    names = {"user": alias, **{pid: p["name"] for pid, p in scn["personas"].items()}}
    directive = f"채널에 처음 말을 건다. 아래 내용을 빠짐없이 전달하되 네 말투로. BEAT: {beat['must_convey']}"
    try:
        text = await llm().speak(scn, beat["speaker"], [], names, directive)
    except Exception:
        text = beat["must_convey"]
    now = time.time()
    doc = {
        "id": store.new_id(),
        "alias": alias,
        "scenario_id": scenario_id,
        "category": scn["category"],
        "status": "active",
        "created_at": now,
        "ended_at": None,
        "milestone_idx": 0,
        "turns_in_milestone": 0,
        "milestone_log": [{"key": MILESTONE_KEYS[0], "entered_idx": 0, "ts": now}],
        "messages": [{"idx": 0, "speaker": beat["speaker"], "text": text, "ts": now, "milestone": MILESTONE_KEYS[0]}],
        "observations": [],
        "notes": "",
        "report": None,
    }
    store.save(doc)
    return doc


def candidate_view(doc: dict) -> dict:
    """Never leak observations, beats or persona stances to the candidate."""
    from .scenarios import public_scenario

    scn = SCENARIO_BY_ID[doc["scenario_id"]]
    # PRD 5.5: situations stay hidden during the session, and are explained afterwards (debriefing).
    debrief = (
        [{"key": m["key"], "label": m["label"], "situation": scn["beats"][m["key"]]["must_convey"]} for m in MILESTONES]
        if doc["status"] == "completed"
        else None
    )
    return {
        "id": doc["id"],
        "alias": doc["alias"],
        "status": doc["status"],
        "debrief": debrief,
        "scenario": public_scenario(scn),
        "milestone_idx": doc["milestone_idx"],
        "milestone_log": doc["milestone_log"],
        "messages": doc["messages"],
        "notes": doc["notes"],
    }


async def run_turn(session_id: str, text: str) -> AsyncIterator[dict]:
    async with _lock(session_id):
        sess = store.load(session_id)
        if sess is None:
            yield {"type": "error", "message": "세션을 찾을 수 없어요."}
            return
        if sess["status"] != "active":
            yield {"type": "error", "message": "이미 종료된 세션이에요."}
            return

        user_idx = len(sess["messages"])
        user_msg = {
            "idx": user_idx,
            "speaker": "user",
            "text": text,
            "ts": time.time(),
            "milestone": MILESTONE_KEYS[sess["milestone_idx"]],
        }
        yield {"type": "user_message", "message": user_msg}

        state = {
            "session": sess,
            "user_text": text,
            "user_idx": user_idx,
            "milestone_idx": sess["milestone_idx"],
            "observations": [],
            "new_messages": [],
        }
        streamed: list[dict] = []
        final: dict = {}
        try:
            async for mode, chunk in GRAPH.astream(
                state, config={"configurable": {"llm": llm()}}, stream_mode=["custom", "values"]
            ):
                if mode == "custom":
                    if chunk["type"] == "message":
                        streamed.append(chunk["message"])
                    yield chunk
                else:
                    final = chunk
        except Exception as e:  # persist what the candidate already saw, then report
            sess["messages"] += [user_msg, *streamed]
            store.save(sess)
            yield {"type": "error", "message": f"응답 생성 중 문제가 생겼어요: {type(e).__name__}"}
            return

        sess["messages"] += [user_msg, *final.get("new_messages", [])]
        sess["observations"] += final.get("observations", [])
        after = final.get("milestone_idx_after", sess["milestone_idx"])
        if after != sess["milestone_idx"]:
            beat_msg = final["new_messages"][-1]
            sess["milestone_log"].append({"key": MILESTONE_KEYS[after], "entered_idx": beat_msg["idx"], "ts": beat_msg["ts"]})
        sess["milestone_idx"] = after
        sess["turns_in_milestone"] = final.get("turns_after", sess["turns_in_milestone"] + 1)
        completed = bool(final.get("completed"))
        if completed:
            sess["status"] = "completed"
            sess["ended_at"] = time.time()
        store.save(sess)
        yield {"type": "state", "milestone_idx": after, "status": sess["status"]}
        if completed:
            await ensure_report(session_id)
            yield {"type": "completed"}


async def finish_session(session_id: str) -> dict | None:
    async with _lock(session_id):
        sess = store.load(session_id)
        if sess is None:
            return None
        if sess["status"] == "active":
            sess["status"] = "completed"
            sess["ended_at"] = time.time()
            store.save(sess)
    await ensure_report(session_id)
    return store.load(session_id)


async def ensure_report(session_id: str, attempts: int = 3) -> None:
    sess = store.load(session_id)
    if sess is None or (sess.get("report") or {}).get("status") == "ready":
        return
    scn = SCENARIO_BY_ID[sess["scenario_id"]]
    for n in range(attempts):  # F-34: retry automatically, then mark failed
        try:
            summary = await llm().summarize(scn, sess["observations"], sess["notes"])
            sess["report"] = build_report(sess, summary.model_dump())
            store.save(sess)
            return
        except Exception:
            await asyncio.sleep(0.5 * (n + 1))
    sess["report"] = {"status": "failed", "generated_at": time.time()}
    store.save(sess)


def build_report(sess: dict, summaries: dict[str, str]) -> dict:
    comps = []
    for c in COMPETENCIES:
        obs = [o for o in sess["observations"] if o["competency"] == c["id"]]
        by_ms = {}
        for m in MILESTONES:
            ms_obs = [o for o in obs if o["milestone"] == m["key"]]
            by_ms[m["key"]] = {
                "count": len(ms_obs),
                "signals": {s: sum(1 for o in ms_obs if o["signal"] == s) for s in ("positive", "neutral", "risk")},
            }
        comps.append(
            {
                "id": c["id"],
                "name": c["name"],
                "desc": c["desc"],
                "summary": summaries.get(c["id"]) if obs else "해당 상황에서 관련 행동이 기록되지 않음",
                "count": len(obs),
                "empty": not obs,
                "by_milestone": by_ms,
                "evidence_ids": [o["id"] for o in obs],
            }
        )
    return {
        "status": "ready",
        "generated_at": time.time(),
        "competencies": comps,
        "disclaimer": "AI는 관찰·기록만 하며 점수나 합격 여부를 판단하지 않습니다. 최종 판단은 채용 담당자가 합니다.",
    }


def admin_row(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "alias": doc["alias"],
        "category": doc["category"],
        "scenario_id": doc["scenario_id"],
        "status": doc["status"],
        "milestone_idx": doc["milestone_idx"],
        "messages": len(doc["messages"]),
        "observations": len(doc["observations"]),
        "report_status": (doc.get("report") or {}).get("status", "none"),
        "created_at": doc["created_at"],
    }


def admin_view(doc: dict) -> dict:
    scn = SCENARIO_BY_ID[doc["scenario_id"]]
    return {
        **doc,
        "scenario": scn,
        "painpoints": PAINPOINTS.get(scn["painpoint_key"]),
    }
