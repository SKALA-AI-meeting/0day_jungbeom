import json
import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv()

from . import service, store  # noqa: E402
from .criteria import CRITERIA  # noqa: E402
from .dilemmas import public_options  # noqa: E402
from .scenarios import COMPETENCIES, MILESTONES, SCENARIOS, get_scenario, public_scenario  # noqa: E402

app = FastAPI(title="Day Zero - 협업 인성 관찰 (PR1)")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


def admin_guard(x_admin_token: str | None = Header(default=None)) -> None:
    """PR1: optional shared token. Real user auth (평가표 '인증') arrives in a later PR."""
    expected = os.getenv("ADMIN_TOKEN")
    if expected and x_admin_token != expected:
        raise HTTPException(401, "관리자 토큰이 필요해요.")


class NewSession(BaseModel):
    alias: str = Field(min_length=1, max_length=20)
    scenario_id: str


class Msg(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    choice_id: str | None = Field(default=None, max_length=10)


class Notes(BaseModel):
    text: str = Field(max_length=10000)


def _get(session_id: str) -> dict:
    doc = store.load(session_id)
    if doc is None:
        raise HTTPException(404, "세션을 찾을 수 없어요.")
    return doc


@app.get("/api/health")
def health():
    return {"ok": True, "mock_llm": type(service.llm()).__name__ == "MockLLM"}


@app.get("/api/meta")
def meta():
    return {
        "competencies": COMPETENCIES,
        "milestones": MILESTONES,
        "scenarios": [public_scenario(s) for s in SCENARIOS],
        "dilemma": public_options(),
    }


@app.get("/api/scenarios/{scenario_id}")
def preview_scenario(scenario_id: str):
    try:
        return public_scenario(get_scenario(scenario_id))
    except KeyError:
        raise HTTPException(404, "알 수 없는 시나리오예요.")


@app.post("/api/sessions")
async def create_session(body: NewSession):
    try:
        get_scenario(body.scenario_id)
    except KeyError:
        raise HTTPException(400, "알 수 없는 시나리오예요.")
    doc = await service.create_session(body.alias.strip(), body.scenario_id)
    return service.candidate_view(doc)


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    return service.candidate_view(_get(session_id))


@app.post("/api/sessions/{session_id}/messages")
async def post_message(session_id: str, body: Msg):
    _get(session_id)

    async def gen():
        async for ev in service.run_turn(session_id, body.text.strip(), body.choice_id):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield 'data: {"type":"done"}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.put("/api/sessions/{session_id}/notes")
def put_notes(session_id: str, body: Notes):
    doc = _get(session_id)
    doc["notes"] = body.text
    store.save(doc)
    return {"ok": True}


@app.post("/api/sessions/{session_id}/finish")
async def finish(session_id: str):
    _get(session_id)
    doc = await service.finish_session(session_id)
    return service.candidate_view(doc)


# ---- admin ----
@app.get("/api/admin/sessions", dependencies=[Depends(admin_guard)])
def admin_sessions():
    return [service.admin_row(d) for d in store.list_all()]


@app.get("/api/admin/sessions/{session_id}", dependencies=[Depends(admin_guard)])
def admin_session(session_id: str):
    return service.admin_view(_get(session_id))


@app.post("/api/admin/sessions/{session_id}/report", dependencies=[Depends(admin_guard)])
async def regenerate_report(session_id: str):
    doc = _get(session_id)
    doc["report"] = None
    store.save(doc)
    await service.ensure_report(session_id)
    return service.admin_view(_get(session_id))


@app.get("/api/admin/criteria", dependencies=[Depends(admin_guard)])
def admin_criteria():
    return CRITERIA


@app.get("/api/admin/painpoints", dependencies=[Depends(admin_guard)])
def admin_painpoints():
    return service.PAINPOINTS
