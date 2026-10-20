"""라우터 테스트 공용 도구: 앱·클라이언트 조립과 워커 draft 본문 팩토리."""

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


def _tally(values: list[int | None]) -> dict[str, int]:
    return {
        "met": sum(v == 1 for v in values),
        "unmet": sum(v == 0 for v in values),
        "no_record": sum(v is None for v in values),
    }


def make_report_content(scenario: dict[str, Any], autos: list[int | None]) -> dict[str, Any]:
    """scenario의 평가표 항목을 순서대로 autos 값(부족하면 마지막 값 반복)으로 채운 워커 draft 본문.

    형태는 contracts.md Report의 rubric(요소 → 카드 → 항목)·summary. 근거는 비운다.
    """
    elements: dict[str, dict[str, Any]] = {}
    index = 0
    for card in scenario["cards"]:
        if not card.get("element"):
            continue
        element = elements.setdefault(
            card["element"], {"element": card["element"], "name": card["element"], "cards": []}
        )
        items = []
        for rubric in card["rubric"]:
            auto = autos[min(index, len(autos) - 1)]
            index += 1
            items.append(
                {
                    "id": rubric["id"],
                    "text": rubric["text"],
                    "basis": "label" if rubric["basis"] == "label" else "metric",
                    "auto": auto,
                    "no_record_reason": None if auto is not None else "no_activity",
                    "evidence": [],
                    # 응답 시간 항목만 실제 분 값을 갖는다(관련 메시지 없으면 null)
                    **({"minutes": None} if "response_minutes" in str(rubric["when"]) else {}),
                }
            )
        element["cards"].append({"card_id": card["card_id"], "name": card["name"], "items": items})
    for element in elements.values():
        element["auto"] = _tally([i["auto"] for c in element["cards"] for i in c["items"]])
    values = [i["auto"] for e in elements.values() for c in e["cards"] for i in c["items"]]
    return {
        "summary": [
            {"element": e["element"], "name": e["name"], "line": None, **e["auto"]}
            for e in elements.values()
        ],
        "rubric": {"elements": list(elements.values()), "auto_total": _tally(values)},
        "sections": [],
        "ai_usage": {"used": False, "events": []},
    }


AUTOS = [1, 0, None, 1, 1, 1, 0, None]


async def to_report_ready(api, internal, db, service, position, invite_row, autos=AUTOS):
    """초대 → 동의·시작·제출·보고 종료 → 워커 draft 저장까지 진행하고 (session_id, content)."""
    sid = uuid.UUID(invite_row["session_id"])
    await service.consent(sid)
    await service.start(sid)
    await service.submit(sid)
    await service.complete(sid)
    content = make_report_content(position["scenario"], autos)
    res = await internal.post(f"/internal/sessions/{sid}/report/draft", json={"content": content})
    assert res.json() == {"status": "report_ready"}
    return sid, content
