"""analytics-mcp (FastMCP, :9104/mcp): the admin visualizations as read-only tools (api-contract §5).

Every tool reads one session state from Spring Boot's internal API (GET /internal/sessions/{id}/state, internal
connector + X-Internal-Key) and derives everything from it: app/analytics.py (the numbers) and app/charts.py (the SVG).
Nothing is stored or changed here: the agent's ANALYTICS task saves the bundle through business-mcp (save_analytics)
and Spring keeps it as the session's snapshot, tagged with the state_rev it was computed from.

  조회  session_analytics, render_chart, render_charts, describe_charts   (read-only, no approval)

Errors are ToolError with an HTTP-like status first, like business-mcp: unknown session -> "404 …" (Spring's message),
unknown chart -> "400 …", Spring unreachable -> "503 …".

Run:  uv run --python 3.12 python -m mcp_servers.analytics.server     (Streamable HTTP, :9104/mcp)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT.parent / ".env")
sys.path.insert(0, str(ROOT))
from app import analytics, charts  # noqa: E402

BASE = os.getenv("BACKEND_INTERNAL_URL", "http://127.0.0.1:8081")
KEY = os.getenv("INTERNAL_KEY", "dev-internal-key-change-me")
_transport: httpx.AsyncBaseTransport | None = None  # tests: route to an in-process fake backend
READ_ONLY = {"readOnlyHint": True, "idempotentHint": True}

mcp = FastMCP("analytics-mcp", instructions="Day Zero 세션 상태에서 분석 수치(마일스톤 타임라인, 역량×단계 관찰 지도, 주장성·협력성 평면, "
                                             "관찰기↔디텍터 일치도, 심어 둔 확인 지점)와 SVG 차트를 계산한다. 읽기 전용이며 점수나 합격 판단을 하지 않는다.")


def use_transport(t: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = t


def _sid(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id.isalnum() or len(session_id) > 32:
        raise ToolError("400 session_id 형식이 올바르지 않아요.")
    return session_id


async def _state(session_id: str) -> dict:
    async with httpx.AsyncClient(base_url=BASE, headers={"X-Internal-Key": KEY}, timeout=20, transport=_transport) as c:
        try:
            r = await c.get(f"/internal/sessions/{_sid(session_id)}/state")
        except httpx.HTTPError as e:
            raise ToolError(f"503 backend unreachable: {e}") from e
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise ToolError(f"{r.status_code} {detail}")
    try:
        state = r.json()
    except ValueError as e:
        raise ToolError("502 세션 상태를 읽지 못했어요.") from e
    if not isinstance(state, dict):
        raise ToolError("502 세션 상태 형식이 올바르지 않아요.")
    return state


@mcp.tool(annotations=READ_ONLY)
async def session_analytics(session_id: str) -> dict:
    """[조회] 세션 하나의 분석 묶음(version 1)을 지금 상태로 계산해 돌려준다. 저장하지 않는다(저장은 business.save_analytics).

    source(계산에 쓴 state_rev와 메시지·근거·판정·마크업 수), row(대시보드 열), context(시나리오·painpoint·과제 제목),
    timeline(단계별 도달·진입 시각·메시지·근거), heatmap(역량×단계 신호별 근거 수, 합계, 최댓값),
    detector(성향 추정, 관찰기↔디텍터 일치도), dilemma(가치 딜레마와 선택), condition(배정된 상대 유형),
    artifact_checks(심어 둔 확인 지점을 마크업으로 짚었는지), figures(프롬프트·인박스용 요약 수치),
    charts(차트별 제목·설명 한 줄·available). 모두 관찰 기록과 성향 기술이며 점수나 합격 판단이 아니다.
    """
    return analytics.build(await _state(session_id))


def _chart_ids(chart_ids) -> list[str]:
    ids = [chart_ids] if isinstance(chart_ids, str) else chart_ids
    if not isinstance(ids, list) or not ids or len(ids) > len(charts.CHART_IDS):
        raise ToolError(f"400 chart_ids는 1~{len(charts.CHART_IDS)}개의 차트 id 목록이에요.")
    for cid in ids:
        if cid not in charts.CHART_IDS:
            raise ToolError(f"400 알 수 없는 차트예요: {str(cid)[:40]} (가능: {', '.join(charts.CHART_IDS)})")
    return list(dict.fromkeys(ids))  # once each, in the order asked


def _chart(bundle: dict, chart_id: str) -> dict:
    meta = next(c for c in bundle["charts"] if c["id"] == chart_id)
    return {"chart_id": chart_id, "title": meta["title"], "mime": "image/svg+xml", "svg": charts.render(bundle, chart_id),
            "available": meta["available"], "caption": meta["caption"]}


@mcp.tool(annotations=READ_ONLY)
async def render_chart(session_id: str, chart_id: str) -> dict:
    """[조회] 세션의 차트 하나를 SVG로 그린다. chart_id = timeline | heatmap | tki | agreement | checkpoints (describe_charts 참고).

    반환: {chart_id, title, mime: "image/svg+xml", svg, available, caption, state_rev}. svg는 스크립트·외부 링크가 없는 자체 완결 이미지
    (가로 720px 이하, 흰 배경, 한국어 라벨)라 <img src="data:image/svg+xml;…">로 그대로 보여 줄 수 있다. 데이터가 없으면
    (대화 없음, 디텍터 판정 없음, 같이 본 과제 없음) 이유를 적은 작은 안내 그림을 돌려주고 available=false다.
    state_rev는 그린 세션 상태의 판(session_analytics의 source.state_rev와 같은 값)이다. 여러 개는 render_charts로 한 번에 그린다.
    """
    cid = _chart_ids([chart_id])[0]
    bundle = analytics.build(await _state(session_id))
    return {**_chart(bundle, cid), "state_rev": bundle["source"]["state_rev"]}


@mcp.tool(annotations=READ_ONLY)
async def render_charts(session_id: str, chart_ids: list[str]) -> dict:
    """[조회] 세션 상태를 한 번 읽어 차트 여러 개를 같은 상태에서 그린다(리포트용). chart_ids = render_chart의 id 목록(1~5개, 중복은 한 번).

    반환: {state_rev, charts: [{chart_id, title, mime, svg, available, caption}]} (요청 순서). 모든 차트가 같은 state_rev에서 나오므로
    session_analytics 결과와 state_rev가 같으면 수치(figures)와 그림이 같은 상태를 가리킨다.
    """
    ids = _chart_ids(chart_ids)
    bundle = analytics.build(await _state(session_id))
    return {"state_rev": bundle["source"]["state_rev"], "charts": [_chart(bundle, cid) for cid in ids]}


@mcp.tool(annotations=READ_ONLY)
def describe_charts() -> list[dict]:
    """[조회] 그릴 수 있는 차트 목록 [{id, type, title, description, fields}]. fields는 그 차트가 읽는 분석 묶음(session_analytics)의 항목이다."""
    return [{k: s[k] for k in ("id", "type", "title", "description", "fields")} for s in charts.SPECS]


if __name__ == "__main__":
    mcp.run(transport="http", host=os.getenv("MCP_HOST", "127.0.0.1"), port=int(os.getenv("ANALYTICS_MCP_PORT", "9104")))
