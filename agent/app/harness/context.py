"""Context: token budget for the transcript. Recent messages stay verbatim; older ones are folded into a short digest.

With the dialogue harness (dialogue.py) the older part is the ledger's rolling summary instead of the digest,
and prompts carry only a fixed recent window (window()).
"""
from __future__ import annotations

BUDGET_CHARS = 6000  # ~2k tokens of Korean chat for the transcript part of a prompt
WINDOW_BUDGET = 3000  # recent window next to the ledger summary


def _lines(messages: list[dict], names: dict[str, str]) -> list[str]:
    return [f"[{names.get(m['speaker'], m['speaker'])}] {m['text']}" for m in messages if m.get("speaker") != "system"]


def digest(messages: list[dict], names: dict[str, str], k: int = 12, width: int = 40) -> str:
    """Rule-based fold of older lines (first `width` chars of the last `k`)."""
    lines = messages if messages and isinstance(messages[0], str) else _lines(messages, names)
    return " / ".join(o[:width] + ("…" if len(o) > width else "") for o in lines[-k:])


def transcript(messages: list[dict], names: dict[str, str], budget: int = BUDGET_CHARS) -> str:
    lines = _lines(messages, names)
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
    return f"(앞선 대화 {len(older)}개 요약: {digest(older, names)})\n" + "\n".join(kept)


def window(messages: list[dict], names: dict[str, str], n: int = 8, budget: int = WINDOW_BUDGET) -> str:
    """The last n messages verbatim (within budget); everything older is covered by the ledger summary."""
    lines = _lines(messages, names)[-n:]
    if not lines:
        return "(대화 없음)"
    kept, used = [], 0
    for line in reversed(lines):
        if used + len(line) > budget and kept:
            break
        kept.append(line)
        used += len(line)
    return "\n".join(reversed(kept))


def numbered(messages: list[dict], names: dict[str, str]) -> str:
    """Messages with their idx, for the ledger model (commitments point back at #idx)."""
    rows = [f"#{m['idx']} [{names.get(m['speaker'], m['speaker'])}] {m['text']}" for m in messages if m.get("speaker") != "system"]
    return "\n".join(rows) or "(없음)"
