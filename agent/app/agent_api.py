"""FastAPI Agent server (internal tier, :8000). Called only by Spring Boot with X-Internal-Key.

POST /agent/tasks          run a task in the background (HTTP dispatch mode) -> 202
GET  /agent/meta           scenario catalog for the UI (proxied by Spring /api/meta)
GET  /agent/scenarios/{id} public scenario (no beats, stances or hidden axis)
POST /agent/views/candidate the candidate view over a state from Spring (admin screens read the analytics snapshot, api-contract §5)
GET  /agent/handlers       task types this agent runs [{type, resumable, description}] (Spring checks its TaskHandlers)
GET  /agent/health         checkpointer, model mode, prompt versions
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Header, HTTPException

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from . import runner, views  # noqa: E402
from .dilemmas import public_options  # noqa: E402
from .harness import instructions, memory  # noqa: E402
from .llm import MockLLM  # noqa: E402
from .scenarios import COMPETENCIES, MILESTONES, SCENARIOS, get_scenario, public_scenario  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
INTERNAL_KEY = os.getenv("INTERNAL_KEY", "dev-internal-key-change-me")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await runner.graphs()
    stop = asyncio.Event()
    consumer = None
    if os.getenv("RABBIT_URL"):
        from .queue_consumer import consume

        consumer = asyncio.create_task(consume(stop))
    yield
    stop.set()
    if consumer:
        consumer.cancel()
    await runner.drain_background()
    await memory.close_checkpointer()


app = FastAPI(title="Day Zero Agent", lifespan=lifespan)


def internal(x_internal_key: str | None = Header(default=None)) -> None:
    if not x_internal_key or not hmac.compare_digest(x_internal_key, INTERNAL_KEY):
        raise HTTPException(401, "internal key required")


@app.get("/agent/health")
def health():
    return {"ok": True, "checkpointer": memory.kind(), "mock_llm": isinstance(runner.llm(), MockLLM),
            "queue": bool(os.getenv("RABBIT_URL")), "prompts": instructions.versions()}


@app.post("/agent/tasks", status_code=202, dependencies=[Depends(internal)])
async def submit(msg: dict):
    for k in ("taskId", "type", "threadId"):
        if not msg.get(k):
            raise HTTPException(400, f"{k} is required")
    runner._spawn(runner.run_with_retries(msg))
    return {"accepted": msg["taskId"]}


@app.get("/agent/handlers", dependencies=[Depends(internal)])
def handlers():
    return runner.HANDLERS.describe()


@app.get("/agent/meta", dependencies=[Depends(internal)])
def meta():
    return {"competencies": COMPETENCIES, "milestones": MILESTONES, "scenarios": [public_scenario(s) for s in SCENARIOS], "dilemma": public_options()}


@app.get("/agent/scenarios/{scenario_id}", dependencies=[Depends(internal)])
def scenario(scenario_id: str):
    try:
        return public_scenario(get_scenario(scenario_id))
    except KeyError:
        raise HTTPException(404, "unknown scenario")


@app.post("/agent/views/{kind}", dependencies=[Depends(internal)])
def view(kind: str, state: Any = Body(default=None)):
    # admin / admin-rows are gone: the admin screens render Spring's analytics snapshot (analytics-mcp, api-contract §5)
    if kind != "candidate":
        raise HTTPException(404, "unknown view")
    if not isinstance(state, dict):
        raise HTTPException(400, "state object is required")
    return views.candidate_view(state)
