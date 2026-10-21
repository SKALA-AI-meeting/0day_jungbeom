"""Instructions: role, tool rules, prohibitions and output format live in app/prompts/*.md (versioned),
rendered with string.Template ($name) so prompt text needs no brace escaping."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from string import Template

from . import runtime

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
_VERSION = re.compile(r"<!--\s*version:\s*([\w.-]+)\s*-->")


@lru_cache(maxsize=64)
def _load(name: str) -> tuple[str, Template]:
    raw = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    m = _VERSION.search(raw)
    body = _VERSION.sub("", raw).strip()
    return (m.group(1) if m else "0"), Template(body)


def render(prompt: str, /, **values) -> str:
    version, tpl = _load(prompt)
    ctx = runtime.current()
    if ctx:
        ctx.tracer.prompts[prompt] = version
    return tpl.safe_substitute(**{k: ("" if v is None else v) for k, v in values.items()})


def versions() -> dict[str, str]:
    return {p.stem: _load(p.stem)[0] for p in sorted(PROMPTS.glob("*.md"))}
