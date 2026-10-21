"""Tools: MCP clients for business-mcp, rag-mcp and detector-mcp (FastMCP, Streamable HTTP /mcp).

- every call is traced, counted against the loop limits and wrapped in TOOL_START / TOOL_END events
- change tools that need approval are refused here unless the caller passes approved=True (defense in depth)
- results shown to the model are masked and truncated; tool errors go back to the model as text (like a ToolMessage)
"""
from __future__ import annotations

import json
import os

from fastmcp import Client

from . import guardrails, runtime

MAX_CHARS = 4000
URLS = {
    "business": os.getenv("BUSINESS_MCP_URL", "http://127.0.0.1:9101/mcp"),
    "rag": os.getenv("RAG_MCP_URL", "http://127.0.0.1:9102/mcp"),
    "detector": os.getenv("DETECTOR_MCP_URL", "http://127.0.0.1:9103/mcp"),
}
_override: dict[str, object] = {}  # tests: in-process FastMCP servers


class ToolFailure(RuntimeError):
    pass


def use_in_process(server: str, mcp) -> None:
    _override[server] = mcp


def _target(server: str):
    return _override.get(server) or URLS[server]


def enabled(server: str) -> bool:
    return server in _override or bool(URLS.get(server))


async def call(server: str, tool: str, args: dict, *, approved: bool = False, quiet: bool = False):
    name = f"{server}.{tool}"
    guardrails.require_approval(name, approved, args)
    ctx = runtime.current()
    if ctx:
        ctx.limits.check_tool(ctx.tool_counts, name)
    if not quiet:
        await runtime.emit("TOOL_START", {"tool": name, "args": _summary(args)})
    try:
        if ctx:
            async with ctx.tracer.span("tool", name):
                data = await _invoke(server, tool, args)
        else:
            data = await _invoke(server, tool, args)
    except Exception as e:
        if not quiet:
            await runtime.emit("TOOL_END", {"tool": name, "ok": False, "error": str(e)[:200]})
        raise ToolFailure(f"{name}: {e}") from e
    if not quiet:
        await runtime.emit("TOOL_END", {"tool": name, "ok": True})
    return data


async def call_for_model(server: str, tool: str, args: dict) -> tuple[str, object]:
    """Same as call(), but never raises: returns (text for a ToolMessage, raw data or None)."""
    try:
        data = guardrails.mask(await call(server, tool, args))
    except guardrails.ApprovalRequired:
        raise
    except Exception as e:
        return f"도구 오류: {e}", None
    text = json.dumps(data, ensure_ascii=False, default=str)
    return (text[:MAX_CHARS] + "…(잘림)" if len(text) > MAX_CHARS else text), data


async def _invoke(server: str, tool: str, args: dict):
    async with Client(_target(server), timeout=60) as c:
        res = await c.call_tool(tool, args)
    return res.data if res.data is not None else (res.structured_content or {})


# Arguments that carry evaluation data (observer evidence, ledger, report, review, detections): TOOL_START events can reach
# the candidate's stream, so these are summarized by size only. The full call is still in the trace span.
REDACTED_ARGS = {"observations", "dialogue", "report", "review", "detection", "artifacts"}


def _summary(args: dict) -> dict:
    out = {}
    for k, v in args.items():
        if k in REDACTED_ARGS:
            out[k] = f"[{len(v)}개]" if isinstance(v, (list, dict)) else "[생략]"
            continue
        s = v if isinstance(v, (int, float, bool)) or v is None else str(v)
        out[k] = s[:80] if isinstance(s, str) else s
    return out
