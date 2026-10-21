"""기록 저장: tests/e2e/records/<YYYYMMDD-HHMM>-<대본>/ (docs/common/testing.md e2e "기록")."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from e2e import asserts

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


def _fmt(value: Any, digits: int = 2) -> str:
    return (
        "-" if value is None else f"{value:.{digits}f}" if isinstance(value, float) else str(value)
    )


def summary(b: dict[str, Any]) -> str:
    mode = "결정적(LLM_FAKE=1)" if b.get("llm_fake") else "실제 LLM(수준 값 기대 건너뜀)"
    lines = [
        f"# {b['name']} ({b['clock']} 시계, 세션 {b['session_id']})",
        "",
        f"- LLM 모드: {mode}, 판별: {b.get('llm_mode_source', '러너 인자')}",
        "",
    ]
    starts = asserts.phase_starts(b)
    slots = asserts.slots_by_phase(b)
    lines += [
        "## 단계",
        "",
        "| 단계 | 시작 t_min | 확정 값 | resolution | filled_by | 확정 t_min |",
        "|---|---|---|---|---|---|",
    ]
    for phase in ("keyword", "problem", "solution", "proposal"):
        slot = slots.get(phase, {})
        lines.append(
            f"| {phase} | {_fmt(starts.get(phase))} | {slot.get('value') or '-'} "
            f"| {slot.get('resolution') or '-'} | {slot.get('filled_by') or '-'} "
            f"| {_fmt(slot.get('t_min'))} |"
        )
    lines += ["", "## 카드", "", "| 카드 | 발생 t_min | 전달 |", "|---|---|---|"]
    seen = {o["card_id"]: o for o in b.get("observations") or []}
    for card_id in sorted(seen):
        row = seen[card_id]
        lines.append(
            f"| {card_id} | {_fmt(row['t_min'])} | {'전달' if row['delivered'] else '일부'} |"
        )
    for card_id in b.get("unfired_cards") or []:
        lines.append(f"| {card_id} | 미발생 | - |")
    lines += ["", "## 단언", "", "| # | 이름 | 결과 |", "|---|---|---|"]
    for r in b["results"]:
        lines.append(f"| {r['id']} | {r['name']} | {'통과' if r['ok'] else '실패'} |")
    failed = [r for r in b["results"] if not r["ok"]]
    if failed:
        lines += ["", "### 실패", ""]
        for r in failed:
            lines += [f"- {r['id']} {r['name']}: {f}" for f in r["failures"]]
    runs = b.get("runs") or []
    if runs:
        lines += [
            "",
            "## run별 실행",
            "",
            "| run_id | 자극 | 상태 | 도구 호출 | LLM 호출 |",
            "|---|---|---|---|---|",
        ]
        for run in runs:
            usage = run.get("usage") or {}
            lines.append(
                f"| {run['run_id'][:8]} | {run['stimulus']} | {run['status']} "
                f"| {usage.get('tool_calls', '-')} | {usage.get('llm_calls', '-')} |"
            )
    m = b.get("measure") or {}
    project = b.get("langsmith_project")
    trace = f"프로젝트 {project}" if project else "추적 꺼짐(trace URL 없음)"
    lines += [
        "",
        "## 비용·지연 (목표와 비교)",
        "",
        f"- 세션 비용 `sessions.cost_usd`: {_fmt(m.get('cost_usd'), 4)} "
        f"(목표 ${m.get('cost_target')})",
        f"- 지원자 메시지 → 첫 페르소나 게시 p95: {_fmt(m.get('first_persona_p95_sec'), 1)}초 "
        f"(목표 {m.get('first_persona_target')}초)",
        f"- 의도 분류 p95: {_fmt(m.get('intent_p95_sec'), 1)}초 (목표 {m.get('intent_target')}초)",
        f"- LangSmith trace: {trace}",
    ]
    if b.get("step_errors"):
        lines += ["", "## step 오류", ""] + [f"- {e}" for e in b["step_errors"]]
    return "\n".join(lines) + "\n"


def write(b: dict[str, Any], out: Path = RECORDS) -> Path:
    path = folder(out, b["name"])
    (path / "transcript.jsonl").write_text(
        "".join(
            json.dumps(line, ensure_ascii=False, default=str) + "\n" for line in b["transcript"]
        ),
        "utf-8",
    )
    _dump(
        path / "turn_decisions.json",
        [
            {
                "run_id": r["run_id"],
                "stimulus": r["stimulus"],
                "status": r["status"],
                "decision": r["decision"],
            }
            for r in b.get("runs") or []
        ],
    )
    _dump(path / "evaluations.json", b.get("evaluations"))
    _dump(path / "report_draft.json", b.get("draft"))
    _dump(path / "report_final.json", b.get("final"))
    _dump(path / "record.json", b.get("record"))
    (path / "summary.md").write_text(summary(b), "utf-8")
    return path
