"""business-mcp (FastMCP, :9101/mcp): business data as tools for the agent.

It never touches a database: every tool calls Spring Boot's internal API (/internal/**, internal connector
+ X-Internal-Key), so business rules stay in one place (Spring). HTTP errors become ToolError with the
Spring message, which the agent's harness treats as non-retryable for 4xx.

  조회  get_session_state, list_conditions, get_account, list_artifacts, get_artifact, list_annotations
  변경  init_session, append_turn, save_detection, save_report, decide_account, save_analytics
        (save_report, and decide_account except auto_clean / auto_schema, need human approval in the agent;
         save_analytics stores derived data from analytics-mcp and needs none)

Shared artifacts are seeded once at START (init_session, replace-all) in the contract shape only: anything else on an
item (the agent's planted checkpoints) is dropped here before it can reach Spring or the browser.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
BASE = os.getenv("BACKEND_INTERNAL_URL", "http://127.0.0.1:8081")
KEY = os.getenv("INTERNAL_KEY", "dev-internal-key-change-me")
_transport: httpx.AsyncBaseTransport | None = None  # tests: route to an in-process fake backend

mcp = FastMCP("business-mcp", instructions="Day Zero 업무 데이터(세션 상태·대화 기록·판정·리포트)를 Spring Boot 내부 API로 조회·변경한다.")


def use_transport(t: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = t


async def _req(method: str, path: str, json: Any = None, params: dict | None = None):
    async with httpx.AsyncClient(base_url=BASE, headers={"X-Internal-Key": KEY}, timeout=20, transport=_transport) as c:
        try:
            r = await c.request(method, path, json=json, params=params)
        except httpx.HTTPError as e:
            raise ToolError(f"503 backend unreachable: {e}") from e
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise ToolError(f"{r.status_code} {detail}")
    return r.json() if r.content else {}


def _sid(session_id: str) -> str:
    if not session_id or not session_id.isalnum() or len(session_id) > 32:
        raise ToolError("400 session_id 형식이 올바르지 않아요.")
    return session_id


_AID = re.compile(r"^[A-Za-z0-9_-]{1,16}$")
ARTIFACT_FIELDS = ("id", "kind", "title", "owner", "status", "summary", "lang", "body")
_ARTIFACT_MAX = {"title": 80, "status": 20, "summary": 160, "body": 6000}


def _aid(artifact_id: str) -> str:
    if not isinstance(artifact_id, str) or not _AID.match(artifact_id):
        raise ToolError("400 artifact_id 형식이 올바르지 않아요.")
    return artifact_id


def _artifacts(items: list[dict]) -> list[dict]:
    """Contract shape only (docs/architecture/api-contract.md §1); Spring validates again."""
    out, seen = [], set()
    for a in items:
        if not isinstance(a, dict):
            raise ToolError("400 과제 형식이 올바르지 않아요.")
        x = {k: a.get(k) for k in ARTIFACT_FIELDS}
        if _aid(x["id"]) in seen:
            raise ToolError(f"400 과제 id가 겹쳐요: {x['id']}")
        seen.add(x["id"])
        if x["kind"] not in ("design", "result", "code") or x["owner"] not in ("lead", "peer", "team"):
            raise ToolError(f"400 과제 {x['id']}의 kind 또는 owner가 올바르지 않아요.")
        for k, n in _ARTIFACT_MAX.items():
            if not isinstance(x[k], str) or len(x[k]) > n or (k in ("title", "body") and not x[k].strip()):
                raise ToolError(f"400 과제 {x['id']}의 {k}는 {n}자 이하 문자열이어야 해요.")
        out.append(x)
    return out


@mcp.tool
async def get_session_state(session_id: str) -> dict:
    """[조회] 세션 상태(별칭, 시나리오, 단계, 상대 조건, 선택, 메시지, 관찰 근거, 판정, 노트)를 돌려준다."""
    return await _req("GET", f"/internal/sessions/{_sid(session_id)}/state")


@mcp.tool
async def list_conditions() -> list[dict]:
    """[조회] 지금까지 배정된 상대 페르소나 조건(층, 팀장 유형, 동료 유형) 목록. 균형 배정(최소화법)에 쓴다."""
    return await _req("GET", "/internal/conditions")


@mcp.tool
async def init_session(session_id: str, condition: dict, message: dict, artifacts: list[dict] | None = None) -> dict:
    """[변경] 세션 시작: 배정된 상대 조건과 첫 메시지(소통 단계 안건), 같이 볼 과제(있으면 전부 교체)를 저장한다."""
    if condition.get("lead") == condition.get("peer"):
        raise ToolError("400 팀장과 동료의 유형은 달라야 해요.")
    body: dict[str, Any] = {"condition": condition, "message": message}
    if artifacts is not None:
        body["artifacts"] = _artifacts(artifacts)
    return await _req("POST", f"/internal/sessions/{_sid(session_id)}/init", body)


@mcp.tool
async def append_turn(session_id: str, new_messages: list[dict], observations: list[dict], milestone_idx_after: int,
                      turns_after: int, milestone_log_entry: dict | None = None, completed: bool = False,
                      dialogue: dict | None = None) -> dict:
    """[변경] 한 턴의 결과(팀원 메시지, 관찰 근거, 단계 전환, 종료 여부, 대화 장부)를 저장한다. 단계 규칙은 Spring이 다시 검증한다."""
    body: dict[str, Any] = {
        "new_messages": new_messages, "observations": observations, "milestone_idx_after": milestone_idx_after,
        "turns_after": turns_after, "milestone_log_entry": milestone_log_entry, "completed": completed,
    }
    if dialogue is not None:  # absent = keep the stored ledger
        body["dialogue"] = dialogue
    return await _req("POST", f"/internal/sessions/{_sid(session_id)}/turn", body)


@mcp.tool
async def list_artifacts(session_id: str) -> list[dict]:
    """[조회] 같이 보는 과제 목록(id, 종류, 제목, 담당, 상태, 요약, 언어, 줄 수, 마크업 수)."""
    return await _req("GET", f"/internal/sessions/{_sid(session_id)}/artifacts")


@mcp.tool
async def get_artifact(session_id: str, artifact_id: str) -> dict:
    """[조회] 과제 하나의 본문과 지원자가 남긴 마크업."""
    return await _req("GET", f"/internal/sessions/{_sid(session_id)}/artifacts/{_aid(artifact_id)}")


@mcp.tool
async def list_annotations(session_id: str, since_idx: int = 0) -> list[dict]:
    """[조회] 지원자 마크업 중 msg_idx가 since_idx 이상인 것(id 순). 마지막으로 본 뒤 새로 남긴 마크업을 찾을 때 쓴다."""
    if int(since_idx) < 0:
        raise ToolError("400 since_idx는 0 이상이어야 해요.")
    return await _req("GET", f"/internal/sessions/{_sid(session_id)}/annotations", params={"since_idx": int(since_idx)})


@mcp.tool
async def save_detection(session_id: str, msg_idx: int, detection: dict) -> dict:
    """[변경] 외부 디텍터의 발화 판정 결과를 저장한다."""
    return await _req("POST", f"/internal/sessions/{_sid(session_id)}/detections", {"msg_idx": msg_idx, "detection": detection})


@mcp.tool
async def save_report(session_id: str, report: dict) -> dict:
    """[변경·승인 필요] 리포트를 저장해 기업 관리자에게 공개한다. Agent는 사람이 승인한 뒤에만 호출한다."""
    return await _req("PUT", f"/internal/sessions/{_sid(session_id)}/report", {"report": report})


@mcp.tool
async def save_analytics(session_id: str, analytics: dict) -> dict:
    """[변경] analytics-mcp가 계산한 관리자용 분석 스냅샷(번들 version 1)을 저장한다. 파생 데이터라 승인이 필요 없고,
    Spring은 저장된 것보다 오래된 source.state_rev면 버린다(stored=false)."""
    sid = _sid(session_id)
    src = analytics.get("source") if isinstance(analytics, dict) else None
    if not isinstance(src, dict) or analytics.get("version") != 1 or isinstance(analytics.get("version"), bool):
        raise ToolError("400 분석 번들 형식(version 1, source)이 올바르지 않아요.")
    if analytics.get("session_id") != sid:
        raise ToolError("400 분석 번들의 session_id가 세션과 달라요.")
    rev = src.get("state_rev")
    if not isinstance(rev, int) or isinstance(rev, bool) or rev < 0:
        raise ToolError("400 source.state_rev는 0 이상 정수여야 해요.")
    # the parts the admin screens draw from (Spring checks the same): a partial bundle must not look like a fresh snapshot
    if not all(isinstance(analytics.get(k), dict) for k in ("row", "heatmap", "figures")) \
            or not all(isinstance(analytics.get(k), list) and analytics.get(k) for k in ("timeline", "charts")):
        raise ToolError("400 분석 번들에 row·heatmap·figures(객체)와 timeline·charts(비어 있지 않은 목록)가 있어야 해요.")
    res = await _req("PUT", f"/internal/sessions/{sid}/analytics", analytics)
    return {"stored": bool(res.get("stored"))}


@mcp.tool
async def get_account(account_id: int) -> dict:
    """[조회] 지원자 계정의 가입 정보(별칭, 이메일, 희망 직무, 관심 산업, 경력, 자기소개, 동의, 상태)."""
    if int(account_id) <= 0:
        raise ToolError("400 account_id가 올바르지 않아요.")
    return await _req("GET", f"/internal/accounts/{int(account_id)}")


@mcp.tool
async def decide_account(account_id: int, decision: str, basis: str, reason: str = "", review: dict | None = None) -> dict:
    """[변경·조건부 승인] 계정 심사 결과를 반영한다. decision=approved|rejected, basis=auto_clean|auto_schema|admin_approved|admin_rejected.
    Spring이 상태(심사 대기만 변경)와 결정-근거 일치를 다시 검증한다."""
    if decision not in ("approved", "rejected"):
        raise ToolError("400 decision은 approved 또는 rejected예요.")
    return await _req("POST", f"/internal/accounts/{int(account_id)}/decision", {"decision": decision, "basis": basis, "reason": reason, "review": review or {}})


if __name__ == "__main__":
    mcp.run(transport="http", host=os.getenv("MCP_HOST", "127.0.0.1"), port=int(os.getenv("BUSINESS_MCP_PORT", "9101")))
