"""워커 테스트 공용 픽스처: 카탈로그 기반 시나리오, FakeLLM, 내부 API mock(httpx MockTransport).

내부 API mock의 draft/final 규칙은 services/api/app/routers/internal.py와 같다
(draft는 먼저 저장된 것 유지, final은 정규화 JSON 해시 비교, reviewed 재요청은 200 기존 값).
"""

import copy
import hashlib
import json
import re
import uuid
from typing import Any

import httpx
import pytest
import yaml
from report_worker.api import InternalApi
from report_worker.config import REPO_ROOT
from report_worker.llm import Completion

STARTED_AT = "2026-10-20T00:00:00+00:00"
SESSION_MINUTES = 120


def at(minutes: float) -> str:
    seconds = int(minutes * 60)
    return f"2026-10-20T{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}+00:00"


def load_catalog() -> dict[str, Any]:
    return yaml.safe_load((REPO_ROOT / "scenarios" / "catalog.yaml").read_text(encoding="utf-8"))


def card(element: str, at_min: float = 30) -> dict[str, Any]:
    """positions.scenario의 요소 카드 형식(api scenario.assemble이 복사하는 필드)."""
    source = next(c for c in load_catalog()["element_cards"] if c["id"] == element)
    return {"card_id": element, "element": element, "at_min": at_min, **copy.deepcopy(source)}


def scenario(elements: list[str]) -> dict[str, Any]:
    catalog = load_catalog()
    times = {"cooperation": 30, "responsibility": 60, "flexibility": 75, "respect": 90}
    return {
        "session_minutes": SESSION_MINUTES,
        "elements": elements,
        "cards": [card(e, times[e]) for e in elements],
        "documents": [{"doc_id": d["id"], "title": d["title"]} for d in catalog["documents"]],
        "company": catalog["company"],
    }


def event(
    event_id: str, card_id: str, due: float, status: str = "done", fired: float | None = None
):
    """GET /internal/sessions/{id}의 events 행."""
    element = None if card_id in ("kickoff", "division", "review", "report_request") else card_id
    return {
        "id": event_id,
        "card_id": card_id,
        "element": element,
        "status": status,
        "due_at": at(due),
        "fired_at": None if status == "pending" else at(due if fired is None else fired),
    }


def content_hash(content: dict[str, Any]) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class FakeLLM:
    model = "gpt-4o-mini"

    def __init__(
        self, text: str = "지원자는 재참여율 지표 요약을 맡기고 결과를 2번 파트에 고쳐 썼다."
    ) -> None:
        self.text = text
        self.calls = 0

    async def complete(self, system: str, user: str) -> Completion:
        self.calls += 1
        return Completion(text=self.text, tokens_in=120, tokens_out=40)


def ids() -> dict[str, str]:
    names = ["kick", "coop_card", "c1", "a_req", "a_res", "resp_card", "prev", "c2", "late"]
    names += ["a_req2", "a_res2", "call2"]
    names += ["r1", "v1", "call1", "foreign1", "foreign2", "e_kick", "e1", "e2"]
    return {n: str(uuid.uuid4()) for n in names}


def session_data(i: dict[str, str]) -> dict[str, Any]:
    """협력·책임감 2요소 세션. 협력 관찰에 다른 세션 id(foreign1·2)를 섞어 둔다."""

    def msg(key, sender, channel, t, content, event=None, related=None):
        meta = {"classification": {"related_card": related}} if related else {}
        return {
            "id": i[key],
            "channel": channel,
            "sender": sender,
            "content": content,
            "event_id": i[event] if event else None,
            "run_id": None,
            "t_min": t,
            "created_at": at(t),
            "meta": meta,
        }

    def metric(value, *keys):
        return {"value": value, "evidence_ids": [i[k] for k in keys]}

    session_id = str(uuid.uuid4())
    return {
        "session": {
            "id": session_id,
            "status": "completed",
            "position": {
                "elements": ["cooperation", "responsibility"],
                "scenario": scenario(["cooperation", "responsibility"]),
                "catalog_version": "test",
            },
            "division": None,
            "started_at": STARTED_AT,
            "ends_at": at(SESSION_MINUTES),
            "t_min_now": None,
            "current_element": None,
            "events": [
                event(i["e_kick"], "kickoff", 0),
                event(i["e1"], "cooperation", 30),
                event(i["e2"], "responsibility", 60),
            ],
        },
        "messages": [
            msg("kick", "manager", "team", 0, "이번 건 리드를 맡아 주세요.", event="e_kick"),
            msg("coop_card", "colleague", "dm", 30, "10분만 같이 봐 주실 수 있어요?", event="e1"),
            msg(
                "c1",
                "candidate",
                "dm",
                32,
                "제 파트 마무리하고 15분 뒤에 봐요.",
                related="cooperation",
            ),
            msg("a_req", "candidate", "assistant", 41, "재참여율 지표를 요약해 줘"),
            msg("a_res", "assistant", "assistant", 41.1, "지표 현황 기준 재참여율은 22%입니다."),
            msg(
                "resp_card",
                "system",
                "notice",
                60,
                "[리서치 채널 알림] 약 15분 늦어집니다.",
                event="e2",
            ),
            msg("prev", "colleague", "team", 61, "저는 4번 사례 정리 중이에요."),
            msg(
                "a_req2",
                "candidate",
                "assistant",
                80,
                "이 문단 수치가 지표 문서와 맞는지 확인해 줘",
            ),
            msg("a_res2", "assistant", "assistant", 80.1, "지표 현황의 22%와 같습니다."),
            msg(
                "c2",
                "candidate",
                "team",
                62,
                "인터뷰 요약이 늦어서 지표 문서로 먼저 잡을게요.",
                related="responsibility",
            ),
            msg(
                "late",
                "candidate",
                "dm",
                95,
                "아까 말한 기준 지금 같이 봐요.",
                related="cooperation",
            ),
        ],
        "observations": [
            {
                "id": str(uuid.uuid4()),
                "element": "cooperation",
                "window_start": at(30),
                "window_end": at(60),
                "label": "negotiate_timing",
                "evidence": [
                    {"type": "message", "id": i["c1"]},
                    {"type": "message", "id": i["foreign1"]},
                ],
                "metrics": {
                    "responded_to_request": metric(True, "c1"),
                    "response_minutes": metric(2.0, "c1"),
                    "response_specific": metric(True, "c1", "foreign2"),
                    "first_recipient": metric("colleague", "c1"),
                },
            },
            {
                "id": str(uuid.uuid4()),
                "element": "responsibility",
                "window_start": at(60),
                "window_end": at(SESSION_MINUTES),
                "label": "notify_with_alternative",
                "evidence": [
                    {"type": "message", "id": i["c2"]},
                    {"type": "revision", "id": i["r1"]},
                ],
                "metrics": {
                    "response_minutes": metric(2.0, "c2"),
                    "first_recipient": metric(None),
                    "notified_before_release": metric(True, "c2"),
                    "notified_in_team": metric(True, "c2"),
                    "proposes_alternative": metric(True, "c2"),
                    "doc_opened_after_release": metric(True, "v1"),
                },
            },
        ],
        "assistant_calls": [
            {
                "id": i["call1"],
                "request_message_id": i["a_req"],
                "response_message_id": i["a_res"],
                "cited_doc_ids": ["metrics"],
                "created_at": at(41),
            },
            {
                "id": i["call2"],
                "request_message_id": i["a_req2"],
                "response_message_id": i["a_res2"],
                "cited_doc_ids": ["metrics"],
                "created_at": at(80),
            },
        ],
        "assistant_reuse": [{"call_id": i["call1"], "part_no": 2, "reuse": "edited", "ratio": 0.4}],
        "document_revisions": [
            {
                "id": i["r1"],
                "part_no": 2,
                "revision": 1,
                "by": "candidate",
                "content": "지표 기준 가설",
                "length": 7,
                "diff_ratio": 1.0,
                "created_at": at(70),
            }
        ],
        "doc_views": [{"id": i["v1"], "doc_id": "interview_summary", "viewed_at": at(76)}],
    }


class FakeInternalApi:
    """api 내부 앱 흉내. calls에 (method, path, body)를 남긴다."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.session_id = data["session"]["id"]
        self.status = "completed"
        self.report: dict[str, Any] | None = None
        self.report_hash: str | None = None
        self.calls: list[tuple[str, str, Any]] = []
        self.down = False
        self.lose_final_response_once = False

    def error(self, status: int, code: str) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": code, "message": code}})

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        self.calls.append((request.method, path, body))
        if self.down:
            raise httpx.ConnectError("api down", request=request)
        match = re.fullmatch(r"/internal/sessions/([^/]+)(/.*)?", path)
        if match is None or match.group(1) != self.session_id:
            return self.error(404, "not_found")
        suffix = match.group(2) or ""
        if request.method == "GET":
            key = suffix.strip("/") or "session"
            rows = self.data[key]
            if key == "messages":  # 내부 API처럼 offset·limit 페이지
                offset = int(request.url.params.get("offset", 0))
                rows = rows[offset : offset + int(request.url.params.get("limit", 200))]
            return httpx.Response(200, json=rows)
        if suffix == "/report/draft":
            if self.status == "completed":
                self.report = body["content"]
                self.report_hash = content_hash(body["content"])
                self.status = "report_ready"
            return httpx.Response(200, json={"status": "report_ready"})
        if suffix == "/report/final":
            if self.report is None or self.status not in ("approving", "reviewed"):
                return self.error(409, "conflict")
            if content_hash(body["content"]) != self.report_hash:
                return self.error(409, "draft_mismatch")
            self.status = "reviewed"
            if self.lose_final_response_once:
                self.lose_final_response_once = False
                raise httpx.ReadError("connection lost after final saved", request=request)
            return httpx.Response(200, json={"status": "reviewed", "reviewed_at": at(200)})
        if suffix == "/report_failed":
            self.status = "failed"
            return httpx.Response(200, json={"status": "failed"})
        return self.error(404, "not_found")

    def posts(self, suffix: str) -> list[Any]:
        return [b for m, p, b in self.calls if m == "POST" and p.endswith(suffix)]


@pytest.fixture
def ids_map() -> dict[str, str]:
    return ids()


@pytest.fixture
def fake_api(ids_map) -> FakeInternalApi:
    return FakeInternalApi(session_data(ids_map))


@pytest.fixture
async def api(fake_api):
    client = InternalApi(
        "http://api:8001", "test-token", transport=httpx.MockTransport(fake_api.handler)
    )
    yield client
    await client.close()
