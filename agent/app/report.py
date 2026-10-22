"""Report building (no scoring): competency summaries + evidence counts by milestone, plus the analytics figures and
charts (analytics-mcp) the summaries were grounded in, so the published report shows the same numbers the person approved."""
import time

from .scenarios import COMPETENCIES, MILESTONES


def build_report(sess: dict, summaries: dict[str, str], figures: dict | None = None, charts: list[dict] | None = None,
                 analytics_rev: int | None = None) -> dict:
    comps = []
    for c in COMPETENCIES:
        obs = [o for o in sess["observations"] if o["competency"] == c["id"]]
        by_ms = {}
        for m in MILESTONES:
            ms_obs = [o for o in obs if o["milestone"] == m["key"]]
            by_ms[m["key"]] = {"count": len(ms_obs), "signals": {s: sum(1 for o in ms_obs if o["signal"] == s) for s in ("positive", "neutral", "risk")}}
        comps.append({
            "id": c["id"], "name": c["name"], "desc": c["desc"],
            "summary": summaries.get(c["id"]) if obs else "해당 상황에서 관련 행동이 기록되지 않음",
            "count": len(obs), "empty": not obs, "by_milestone": by_ms, "evidence_ids": [o["id"] for o in obs],
        })
    return {
        "status": "ready",
        "generated_at": time.time(),
        "competencies": comps,
        "figures": figures,  # analytics bundle `figures` (None if the report was drafted without a bundle)
        "charts": [{"chart_id": c["chart_id"], "title": c["title"], "svg": c["svg"]} for c in charts or []],  # SVG, shown as <img> only
        "analytics_rev": analytics_rev,  # source.state_rev of the bundle behind figures/charts (provenance)
        "disclaimer": "AI는 관찰·기록만 하며 점수나 합격 여부를 판단하지 않습니다. 최종 판단은 채용 담당자가 합니다.",
    }
