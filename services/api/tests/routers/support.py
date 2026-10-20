"""라우터 테스트 공용 도구: 앱·클라이언트 조립과 report 본문 팩토리."""

import uuid
from typing import Any

import httpx
from app.config import get_settings
from app.main import create_internal_app, create_public_app
from app.services.context import AppContext


def build_clients(ctx: AppContext) -> tuple[httpx.AsyncClient, httpx.AsyncClient]:
    public = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_public_app(ctx)), base_url="http://api"
    )
    internal = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_internal_app(ctx)),
        base_url="http://api-internal",
        headers={"X-Internal-Token": get_settings().internal_token},
    )
    return public, internal


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_report_content(scenario: dict[str, Any], autos: list[int | None]) -> dict[str, Any]:
    """scenario의 평가표 항목을 순서대로 autos 값(부족하면 마지막 값 반복)으로 채운 draft 본문."""
    elements, index = [], 0
    for card in scenario["cards"]:
        if not card.get("element"):
            continue
        items = []
        for rubric in card["rubric"]:
            auto = autos[min(index, len(autos) - 1)]
            index += 1
            items.append(
                {
                    "id": rubric["id"],
                    "text": rubric["text"],
                    "auto": auto,
                    "reviewer": None,
                    "memo": None,
                    "evidence": [],
                }
            )
        elements.append(
            {
                "element": card["element"],
                "name": card["name"],
                "auto": _tally(items),
                "items": items,
            }
        )
    totals = _tally([i for e in elements for i in e["items"]])
    return {
        "stage": "draft",
        "rubric": {"elements": elements, "auto_total": totals, "reviewer_total": None},
        "sections": [],
        "ai_usage": {"used": False, "summary": "사용하지 않음", "evidence": []},
    }


def _tally(items: list[dict[str, Any]]) -> dict[str, int]:
    values = [i["auto"] for i in items]
    return {
        "met": sum(v == 1 for v in values),
        "judged": sum(v is not None for v in values),
        "no_record": sum(v is None for v in values),
    }


AUTOS = [1, 0, None, 1, 1, 1, 0, None]


async def to_report_ready(api, internal, db, service, position, invite_row, autos=AUTOS):
    """초대 → 동의·시작·제출 → 워커 draft 저장까지 진행하고 (session_id, content)를 돌려준다."""
    sid = uuid.UUID(invite_row["session_id"])
    await service.consent(sid)
    await service.start(sid)
    await service.complete(sid)
    content = make_report_content(position["scenario"], autos)
    res = await internal.post(f"/internal/sessions/{sid}/report/draft", json={"content": content})
    assert res.json() == {"status": "report_ready"}
    return sid, content
