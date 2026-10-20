"""Session lifecycle: create, run a turn (streaming events), finish, report."""
import asyncio
import json
import time
from pathlib import Path
from typing import AsyncIterator

from . import detector, store
from .graph import GRAPH
from .llm import BaseLLM, get_llm
from .criteria import AXES, CRITERIA
from .personas import allocate, public_mode
from .scenarios import COMPETENCIES, MILESTONES, MILESTONE_KEYS, get_scenario

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
    sid = store.new_id()
    base = get_scenario(scenario_id)
    # counterpart conflict modes: randomized, balanced within the axis (dilemma) or category (minimization)
    history = [d["condition"] for d in store.list_all() if d.get("condition")]
    condition = allocate(base.get("axis") or scenario_id, history, seed=int(sid, 16))
    scn = {**base, "condition": condition}
    beat = scn["beats"]["communicate"]
    names = {"user": alias, **{pid: p["name"] for pid, p in scn["personas"].items()}}
    directive = f"채널에 처음 말을 건다. 아래 내용을 빠짐없이 전달하되 네 말투로. BEAT: {beat['must_convey']}"
    try:
        text = await llm().speak(scn, beat["speaker"], [], names, directive)
    except Exception:
        text = beat["must_convey"]
    now = time.time()
    doc = {
        "id": sid,
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
        "choice": None,
        "condition": condition,
        "detections": {},
        "report": None,
    }
    store.save(doc)
    return doc


def candidate_view(doc: dict) -> dict:
    """Never leak observations, beats or persona stances to the candidate."""
    from .scenarios import public_scenario

    scn = get_scenario(doc["scenario_id"])
    # PRD 5.5: situations stay hidden during the session, and are explained afterwards (debriefing).
    debrief = None
    if doc["status"] == "completed":
        beats = dict(scn["beats"])
        if scn.get("kind") == "dilemma":
            from .dilemmas import persuade_beat

            beats["persuade"] = persuade_beat(scn, doc.get("choice"))
        debrief = [{"key": m["key"], "label": m["label"], "situation": beats[m["key"]]["must_convey"]} for m in MILESTONES]
        if scn.get("kind") == "dilemma":
            ax = AXES[scn["axis"]]
            a, b = ax["poles"]
            debrief.append({
                "key": "axis", "label": "가치 딜레마",
                "situation": f"이 상황은 '{ax['name']}' — {ax['question']} — 처럼 사람마다 우선순위가 다른 가치를 보기 위한 것이었어요. "
                f"어느 쪽도 정답이 아니며, 선택보다 선택의 근거와 상대를 대하는 방식이 기록됩니다.",
            })
    dilemma = None
    if scn.get("kind") == "dilemma" and doc["milestone_idx"] >= MILESTONE_KEYS.index("compromise"):
        dilemma = {"prompt": scn["dilemma"]["prompt"], "options": [{"id": o["id"], "label": o["label"]} for o in scn["dilemma"]["options"]]}
    return {
        "dilemma": dilemma,
        "choice": {"option": doc["choice"]["option"]} if doc.get("choice") else None,
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


async def run_turn(session_id: str, text: str, choice_id: str | None = None) -> AsyncIterator[dict]:
    completed = False
    async for ev in _run_turn_locked(session_id, text, choice_id):
        if ev["type"] == "_completed":
            completed = True
            continue
        yield ev
    if completed:  # outside the session lock: report generation waits for background detections
        await ensure_report(session_id)
        yield {"type": "completed"}


async def _run_turn_locked(session_id: str, text: str, choice_id: str | None) -> AsyncIterator[dict]:
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
        if choice_id:
            scn = get_scenario(sess["scenario_id"])
            opt = next((o for o in (scn.get("dilemma") or {}).get("options", []) if o["id"] == choice_id), None)
            if opt is None or sess.get("choice") or MILESTONE_KEYS[sess["milestone_idx"]] != "compromise":
                yield {"type": "error", "message": "지금은 선택을 제출할 수 없어요."}
                return
            sess["choice"] = {"option": opt["id"], "pole": opt["pole"], "msg_idx": user_idx, "ts": user_msg["ts"]}
            user_msg["choice"] = opt["id"]
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
        _spawn_detection(session_id, user_msg, sess["messages"][:user_idx])
        yield {"type": "state", "milestone_idx": after, "status": sess["status"], **({"choice": {"option": sess["choice"]["option"]}} if sess.get("choice") else {})}
        if after >= MILESTONE_KEYS.index("compromise") and get_scenario(sess["scenario_id"]).get("kind") == "dilemma":
            yield {"type": "dilemma", "dilemma": candidate_view(sess)["dilemma"]}
        if completed:
            yield {"type": "_completed"}


_bg: set[asyncio.Task] = set()


def _context(prev: list[dict], names: dict | None = None, n: int = 8) -> str:
    return "\n".join(f"[{m['speaker']}] {m['text']}" for m in prev[-n:])


async def _store_detection(session_id: str, msg: dict, prev: list[dict]) -> None:
    res = await detector.detect(session_id, msg["idx"], msg["text"], _context(prev), msg["milestone"])
    if res is None:
        return
    async with _lock(session_id):  # serialize with turns to avoid lost updates
        sess = store.load(session_id)
        sess.setdefault("detections", {})[str(msg["idx"])] = res
        store.save(sess)


def _spawn_detection(session_id: str, msg: dict, prev: list[dict]) -> None:
    if not detector.enabled():
        return
    t = asyncio.create_task(_store_detection(session_id, msg, prev))
    _bg.add(t)
    t.add_done_callback(_bg.discard)


async def backfill_detections(session_id: str) -> None:
    """Judge any candidate message that has no (successful) detection yet."""
    if not detector.enabled():
        return
    if _bg:
        await asyncio.gather(*list(_bg), return_exceptions=True)
    sess = store.load(session_id)
    done = {k for k, v in (sess.get("detections") or {}).items() if v.get("final")}
    for i, m in enumerate(sess["messages"]):
        if m["speaker"] == "user" and str(m["idx"]) not in done:
            await _store_detection(session_id, m, sess["messages"][:i])


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
    await backfill_detections(session_id)
    sess = store.load(session_id)
    scn = get_scenario(sess["scenario_id"])
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


def _choice_detail(doc: dict, scn: dict) -> dict | None:
    if scn.get("kind") != "dilemma":
        return None
    ax = AXES[scn["axis"]]
    ch = doc.get("choice")
    out = {"axis": ax, "axis_ranking": scn["axis_ranking"], "options": scn["dilemma"]["options"], "pole_of": scn["dilemma"]["pole_of"],
           "population": CRITERIA["meta"], "choice": None}
    if ch:
        opt = next(o for o in scn["dilemma"]["options"] if o["id"] == ch["option"])
        rationale = next((m["text"] for m in doc["messages"] if m["idx"] == ch["msg_idx"]), "")
        pole_label = "통합안" if ch["pole"] == "both" else next(p["label"] for p in ax["poles"] if p["side"] == ch["pole"])
        out["choice"] = {**ch, "label": opt["label"], "pole_label": pole_label, "rationale": rationale}
    return out


def _condition_detail(doc: dict) -> dict | None:
    c = doc.get("condition")
    if not c:
        return None
    return {**c, "lead_mode": public_mode(c["lead"]), "peer_mode": public_mode(c["peer"])}


def admin_row(doc: dict) -> dict:
    scn = get_scenario(doc["scenario_id"])
    det = _choice_detail(doc, scn)
    return {
        "axis": det["axis"]["name"] if det else None,
        "condition": (lambda c: f"{c['lead_mode']['label']} 팀장 · {c['peer_mode']['label']} 동료" if c else None)(_condition_detail(doc)),
        "choice": det["choice"]["pole_label"] if det and det["choice"] else None,
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
    scn = get_scenario(doc["scenario_id"])
    return {
        **doc,
        "scenario": scn,
        "painpoints": PAINPOINTS.get(scn["painpoint_key"]) if scn.get("painpoint_key") else None,
        "dilemma": _choice_detail(doc, scn),
        "condition": _condition_detail(doc),
        "detector": detector.summarize(doc),
    }
