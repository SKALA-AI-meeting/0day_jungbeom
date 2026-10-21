"""MCP client for detector-mcp + aggregation (tendency estimate, observer-detector agreement).

DETECTOR_MCP_URL: Streamable HTTP address of detector-mcp (python -m mcp_servers.detector.server).
Tests register an in-process server with harness.tools.use_in_process("detector", mcp).
"""
import logging
import os

from .scenarios import COMPETENCY_IDS

log = logging.getLogger("dayzero.detector")


def enabled() -> bool:
    return bool(os.getenv("DETECTOR_MCP_URL")) or tools_mod().enabled("detector")


def tools_mod():
    from .harness import tools

    return tools


async def detect(session_id: str, msg_idx: int, text: str, context: str, milestone: str) -> dict | None:
    """Judge one candidate message with detector-mcp (independent of the in-graph observer)."""
    if not enabled():
        return None
    try:
        d = await tools_mod().call("detector", "detect_message",
                                   {"session_id": session_id, "msg_idx": msg_idx, "text": text, "context": context, "milestone": milestone}, quiet=True)
        return {k: d[k] for k in ("final", "rules", "model", "source", "model_id", "model_error")} | {"counts": d["features"]["counts"], "milestone": milestone}
    except Exception:
        log.exception("detector call failed")
        return {"source": "unavailable"}


# ---------------- aggregation ----------------
def kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    n = len(pairs)
    if n == 0:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a for a, _ in pairs) / n
    pb = sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def tki_label(a: float, c: float) -> str:
    if 2.5 <= a <= 3.5 and 2.5 <= c <= 3.5:
        return "compromising"
    if a > 3:
        return "collaborating" if c > 3 else "competing"
    return "accommodating" if c > 3 else "avoiding"


def summarize(sess: dict) -> dict:
    """Candidate tendency (assertiveness x cooperativeness) and observer vs detector agreement."""
    user_idx = [m["idx"] for m in sess["messages"] if m["speaker"] == "user"]
    det = {int(k): v for k, v in (sess.get("detections") or {}).items() if v.get("final")}
    if not enabled() and not det:
        return {"status": "disabled"}
    if not det:
        return {"status": "unavailable", "messages": len(user_idx)}
    A = [d["final"]["assertiveness"] for d in det.values()]
    C = [d["final"]["cooperativeness"] for d in det.values()]
    a, c = sum(A) / len(A), sum(C) / len(C)
    obs_by = {}
    for o in sess["observations"]:
        obs_by.setdefault(o["msg_idx"], set()).add(o["competency"])
    per_comp, pooled, disagreements = {}, [], []
    for cid in COMPETENCY_IDS:
        pairs = []
        for idx in user_idx:
            if idx not in det:
                continue
            ob, dt = cid in obs_by.get(idx, set()), cid in det[idx]["final"]["competencies"]
            pairs.append((ob, dt))
            if ob != dt:
                disagreements.append({"msg_idx": idx, "competency": cid, "observer": ob, "detector": dt})
        pooled += pairs
        per_comp[cid] = {"kappa": kappa(pairs), "agree": round(sum(x == y for x, y in pairs) / len(pairs), 3) if pairs else None,
                         "observer_yes": sum(x for x, _ in pairs), "detector_yes": sum(y for _, y in pairs)}
    flags = {}
    for d in det.values():
        for f in (d.get("rules") or {}).get("flags", []):
            flags[f] = flags.get(f, 0) + 1
    by_ms = {}
    for d in det.values():
        by_ms.setdefault(d.get("milestone") or "?", []).append((d["final"]["assertiveness"], d["final"]["cooperativeness"]))
    rules_model = [(d["rules"]["assertiveness"], d["model"]["assertiveness"], d["rules"]["cooperativeness"], d["model"]["cooperativeness"]) for d in det.values() if d.get("model")]
    return {
        "status": "ready",
        "coverage": f"{len(det)}/{len(user_idx)}",
        "sources": {s: sum(1 for d in det.values() if d["source"] == s) for s in {d["source"] for d in det.values()}},
        "assertiveness": round(a, 2), "cooperativeness": round(c, 2), "tki_estimate": tki_label(a, c),
        "points": [{"msg_idx": i, "a": d["final"]["assertiveness"], "c": d["final"]["cooperativeness"], "focus": d["final"]["focus"]} for i, d in sorted(det.items())],
        "by_milestone": {k: {"a": round(sum(x for x, _ in v) / len(v), 2), "c": round(sum(y for _, y in v) / len(v), 2), "n": len(v)} for k, v in by_ms.items()},
        "agreement": {"per_competency": per_comp, "pooled_kappa": kappa(pooled),
                      "pooled_agree": round(sum(x == y for x, y in pooled) / len(pooled), 3) if pooled else None, "n_judgements": len(pooled)},
        "rules_vs_model_mad": {"assertiveness": round(sum(abs(r[0] - r[1]) for r in rules_model) / len(rules_model), 2),
                               "cooperativeness": round(sum(abs(r[2] - r[3]) for r in rules_model) / len(rules_model), 2)} if rules_model else None,
        "flags": flags,
        "disagreements": disagreements[:30],
    }
