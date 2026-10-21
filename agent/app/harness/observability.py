"""Observability: one trace id (= task id) across nodes, model calls and tools; tokens, latency, retries, fallbacks.

The summary is attached to DONE / FAILED so Spring stores it with the task history (FAILED tasks keep their trace).
If LANGSMITH_API_KEY is set, LangChain also sends the same runs to LangSmith with the trace id as metadata.
"""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager

log = logging.getLogger("dayzero.trace")


class Tracer:
    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        self.spans: list[dict] = []
        self.notes: dict[str, int] = {}
        self.prompts: dict[str, str] = {}
        self.t0 = time.perf_counter()

    @asynccontextmanager
    async def span(self, kind: str, name: str, **attrs):
        s = {"kind": kind, "name": name, **attrs}
        t = time.perf_counter()
        try:
            yield s
            s["ok"] = True
        except Exception as e:
            s["ok"] = False
            s["error"] = f"{type(e).__name__}: {str(e)[:160]}"
            raise
        finally:
            s["ms"] = round((time.perf_counter() - t) * 1000)
            self.spans.append(s)
            log.info(json.dumps({"trace_id": self.trace_id, **s}, ensure_ascii=False, default=str))

    def note(self, key: str) -> None:
        self.notes[key] = self.notes.get(key, 0) + 1

    def summary(self) -> dict:
        llm = [s for s in self.spans if s["kind"] == "llm"]
        return {
            "trace_id": self.trace_id,
            "langsmith": bool(os.getenv("LANGSMITH_API_KEY")),
            "total_ms": round((time.perf_counter() - self.t0) * 1000),
            "llm_calls": len(llm),
            "tool_calls": sum(1 for s in self.spans if s["kind"] == "tool"),
            "tokens_in": sum(s.get("tokens_in", 0) or 0 for s in llm),
            "tokens_out": sum(s.get("tokens_out", 0) or 0 for s in llm),
            "retries": self.notes.get("retry", 0),
            "fallbacks": self.notes.get("fallback", 0),
            "prompt_versions": self.prompts,
            "spans": self.spans[-40:],
        }

    def run_config(self, name: str) -> dict:
        """LangChain run config so LangSmith traces carry the same id."""
        return {"run_name": name, "metadata": {"trace_id": self.trace_id}, "tags": ["dayzero"]}
