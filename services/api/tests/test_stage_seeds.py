"""stage-kit 단계 시드 5개(scenarios/e2e/stages)를 실제 시드로 재생해 그 단계 시작 상태를 확인한다.

격리 DB·가짜 시계·기록 runner를 쓰고 실 스택·LLM은 쓰지 않는다. make_session·stage_advance의
인자 파싱도 같이 본다.
"""

import sys
import uuid

import pytest
from app.config import REPO_ROOT
from app.scheduler import tick
from kit import Sess

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import make_session  # noqa: E402
import stage_advance  # noqa: E402

ORDER = ["keyword", "problem", "solution", "proposal"]


@pytest.mark.parametrize("stage", ORDER)
async def test_seed_state_is_stage_start(api, ctx, stage):
    r = await api.internal.post(
        "/internal/test/sessions", json={"session_minutes": 15, "start_at": stage}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["phase"] == stage
    await ctx.mailboxes.drain()
    sess = Sess(uuid.UUID(body["session_id"]), body["token"], body["session_token"], "", "")
    state = await api.state(sess)
    assert state["session"]["status"] == "in_progress" and state["session"]["phase"] == stage
    confirmed = [s["phase"] for s in state["slots"] if s["status"] == "confirmed"]
    assert confirmed == ORDER[: ORDER.index(stage)]


async def test_ended_seed_is_completed(api):
    r = await api.internal.post("/internal/test/sessions", json={"start_at": "ended"})
    body = r.json()
    assert r.status_code == 200 and body["phase"] == "completed"
    assert body["debrief_token"] and body["admin_report_url"].endswith("/report")


async def test_advance_deadline_fills_slot_by_timeout(api, ctx):
    body = (await api.internal.post("/internal/test/sessions", json={"start_at": "problem"})).json()
    sid = body["session_id"]
    await ctx.mailboxes.drain()
    r = await api.internal.post(f"/internal/test/sessions/{sid}/advance", json={"to": "deadline"})
    assert r.status_code == 200
    await tick(ctx)
    slots = (await api.internal.get(f"/internal/sessions/{sid}/slots")).json()
    assert slots[1]["resolution"] == "timeout"


def test_script_args_parse():
    args = make_session.parse_args(["--start-at", "solution", "--minutes", "60", "--llm", "live"])
    assert make_session.request_body(args) == {"session_minutes": 60, "start_at": "solution"}
    assert make_session.parse_args([]).start_at == "entry"
    assert stage_advance.parse_to("90") == {"seconds": 90}
    assert stage_advance.parse_to("card:listening_pressure") == {"to": "card:listening_pressure"}
