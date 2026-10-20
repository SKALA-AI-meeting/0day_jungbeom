"""기록 저장: tests/e2e/records/<YYYYMMDD-HHMM>-<대본>/ (docs/common/testing.md e2e "기록")."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from e2e import asserts
from e2e.client import parse_time
from scripts import make_session

RECORDS = Path(__file__).resolve().parent / "records"


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", "utf-8")


def folder(out: Path, name: str) -> Path:
    path = out / f"{datetime.now():%Y%m%d-%H%M}-{name}"
    suffix = 1
    while path.exists():
        suffix += 1
        path = out / f"{datetime.now():%Y%m%d-%H%M}-{name}-{suffix}"
    path.mkdir(parents=True)
    return path


def card_rows(b: dict[str, Any]) -> list[dict[str, Any]]:
    """카드별 예정(due)·fired·첫 메시지 시각(분)과 오차(초)."""
    session = b.get("session")
    if not session:
        return []
    started = parse_time(session["started_at"])
    first: dict[str, float] = {}
    for m in sorted(b.get("messages") or [], key=lambda m: m["created_at"]):
        if m["event_id"]:
            first.setdefault(m["event_id"], m["t_min"])
    rows = []
    for e in session["events"]:
        due = (parse_time(e["due_at"]) - started).total_seconds() / 60
        fired = (
            (parse_time(e["fired_at"]) - started).total_seconds() / 60 if e["fired_at"] else None
        )
        message = first.get(e["id"])
        rows.append(
            {
                "card_id": e["card_id"],
                "status": e["status"],
                "due": round(due, 3),
                "fired": None if fired is None else round(fired, 3),
                "message": None if message is None else round(message, 3),
                "fired_lag_s": None if fired is None else round((fired - due) * 60, 1),
                "message_lag_s": None
                if message is None or fired is None
                else round((message - fired) * 60, 1),
            }
        )
    return rows


def tool_calls(b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """run_id별 도구 호출(WS agent.progress tool_start)과 agent_runs.usage."""
    runs: dict[str, dict[str, Any]] = {}
    for run in b.get("db", {}).get("agent_runs") or []:
        runs[run["run_id"]] = {
            "stimulus": run["stimulus"],
            "status": run["status"],
            "usage": run["usage"],
            "tools": [],
        }
    for f in b.get("frames") or []:
        p = f["payload"]
        if f["type"] == "agent.progress" and p.get("status") == "tool_start":
            runs.setdefault(p["run_id"], {"tools": []})["tools"].append(p.get("tool"))
    return runs


def langsmith(b: dict[str, Any]) -> str:
    values = make_session.env()
    project = values.get("LANGCHAIN_PROJECT")
    if not project or values.get("LANGCHAIN_TRACING_V2") != "true":
        return "LangSmith 트레이싱 꺼짐(LANGCHAIN_PROJECT 없음)"
    return (
        f"https://smith.langchain.com/ 프로젝트 `{project}`에서 "
        f"metadata session_id = `{b.get('session_id')}` "
        "(run_id별 필터는 아래 표의 run_id)"
    )


def summary(b: dict[str, Any]) -> str:
    cost = b.get("cost") or {
        "tokens": asserts.tokens(b),
        "latency_p95": asserts.p95(asserts.latencies(b)),
    }
    lines = [
        f"# e2e {b['name']}",
        "",
        f"- session_id: `{b.get('session_id')}`",
        f"- 요소: {', '.join(b['elements'])}",
        f"- 종료 상태: {b.get('ended_status')}",
        f"- 토큰 합(agent_runs + reports): {cost['tokens']}",
        "- 접수→응답 지연 p95: "
        + ("없음" if cost["latency_p95"] is None else f"{cost['latency_p95']:.1f}초"),
        f"- LangSmith: {langsmith(b)}",
        "",
        "## 단언",
        "",
        "| 번호 | 함수 | 결과 | 실패 |",
        "|---|---|---|---|",
    ]
    for r in b.get("results") or []:
        failures = "<br>".join(f.replace("|", "\\|") for f in r["failures"][:8])
        lines.append(f"| {r['id']} | {r['name']} | {'통과' if r['ok'] else '실패'} | {failures} |")
    lines += [
        "",
        "## 카드 시각(분, 오차는 초)",
        "",
        "| 카드 | 상태 | 예정 | fired | 첫 메시지 | fired 오차 | 메시지 지연 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in card_rows(b):
        lines.append(
            f"| {row['card_id']} | {row['status']} | {row['due']} | {row['fired']} | "
            f"{row['message']} | "
            f"{row['fired_lag_s']} | {row['message_lag_s']} |"
        )
    lines += [
        "",
        "## run_id별 도구 호출",
        "",
        "| run_id | 자극 | 상태 | 도구 | 토큰(in/out) |",
        "|---|---|---|---|---|",
    ]
    for run_id, run in tool_calls(b).items():
        usage = run.get("usage") or {}
        lines.append(
            f"| `{run_id}` | {run.get('stimulus')} | {run.get('status')} | "
            f"{', '.join(t or '?' for t in run['tools']) or '-'} | "
            f"{usage.get('tokens_in', 0)}/{usage.get('tokens_out', 0)} |"
        )
    if b.get("step_errors"):
        lines += ["", "## 실패한 step", ""] + [f"- {e}" for e in b["step_errors"]]
    return "\n".join(lines) + "\n"


def write(b: dict[str, Any], out: Path = RECORDS) -> Path:
    path = folder(out, b["name"])
    with (path / "transcript.jsonl").open("w", encoding="utf-8") as fh:
        for line in b.get("transcript") or []:
            fh.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
    _dump(path / "observations.json", b.get("observations"))
    _dump(path / "report_draft.json", b.get("report_draft"))
    _dump(path / "report_final.json", b.get("report_final"))
    _dump(path / "record.json", b.get("record"))
    (path / "summary.md").write_text(summary(b), "utf-8")
    b["record_dir"] = str(path)
    return path


def write_concurrent(bundles: list[dict[str, Any]], out: Path = RECORDS) -> Path:
    """단언 7: 대본마다 기록하고 묶음 요약(concurrent.md)에 단언 1·2 결과를 모은다."""
    path = folder(out, "concurrent")
    lines = ["# 동시 실행(단언 7)", "", "| 대본 | 기록 | 단언 1 | 단언 2 |", "|---|---|---|---|"]
    for b in bundles:
        record = write(b, path)
        status = {r["id"]: "통과" if r["ok"] else "실패" for r in b["results"]}
        lines.append(f"| {b['name']} | {record.name} | {status.get('1')} | {status.get('2')} |")
    (path / "concurrent.md").write_text("\n".join(lines) + "\n", "utf-8")
    return path
