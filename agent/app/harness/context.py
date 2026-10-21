"""Context: token budget for the transcript. Recent messages stay verbatim; older ones are folded into a short digest."""
from __future__ import annotations

BUDGET_CHARS = 6000  # ~2k tokens of Korean chat for the transcript part of a prompt


def transcript(messages: list[dict], names: dict[str, str], budget: int = BUDGET_CHARS) -> str:
    lines = [f"[{names.get(m['speaker'], m['speaker'])}] {m['text']}" for m in messages if m.get("speaker") != "system"]
    if not lines:
        return "(대화 없음)"
    kept, used = [], 0
    for line in reversed(lines):
        if used + len(line) > budget and kept:
            break
        kept.append(line)
        used += len(line)
    kept.reverse()
    older = lines[: len(lines) - len(kept)]
    if not older:
        return "\n".join(kept)
    digest = " / ".join(o[:40] + ("…" if len(o) > 40 else "") for o in older[-12:])
    return f"(앞선 대화 {len(older)}개 요약: {digest})\n" + "\n".join(kept)
