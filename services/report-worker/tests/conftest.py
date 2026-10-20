"""워커 테스트 공용 픽스처: 실제 미션 카탈로그로 조립한 시나리오, 5요소 120분 세션 데이터, FakeLLM,
내부 API mock(httpx MockTransport).

세션 장면은 공용 리포트 픽스처(tests/fixtures/contracts/report.json)와 같다: 보드로 분업(10분),
도움 요청에 20분 뒤 약속(30분) → 창 밖 50분에 이행, 초안 열기·의견(45분), 지연을 공개 전 팀에
알림(60분), 방향 변경 반영·재지시(75분), 반대 의견에 근거로 답(90분), 마감 보고(110분).
내부 API mock의 draft/final 규칙은 services/api/app/routers/internal.py와 같다.
"""

import copy
import hashlib
import importlib.util
import json
import re
import uuid
from typing import Any

import httpx
import pytest
from report_worker.api import InternalApi
from report_worker.config import REPO_ROOT
from report_worker.llm import Completion

STARTED_AT = "2026-10-20T00:00:00+00:00"
ALL_FIVE = ["responsibility", "planning", "adaptability", "collaboration", "honesty"]


def _load(name: str, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# api의 조립 함수(표준 라이브러리 + yaml만 씀)를 그대로 써서 positions.scenario를 만든다
_scenario = _load(
    "api_scenario", REPO_ROOT / "services" / "api" / "app" / "services" / "scenario.py"
)
contract = _load("contract_shape", REPO_ROOT / "tests" / "contract_shape.py")


def scenario(elements: list[str] = ALL_FIVE) -> dict[str, Any]:
    built, _ = _scenario.build_scenario(REPO_ROOT / "scenarios", elements, 120)
    return built


def at(minutes: float) -> str:
    seconds = round(minutes * 60)
    return f"2026-10-20T{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}+00:00"


def content_hash(content: dict[str, Any]) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class FakeLLM:
    """워커는 리포트에 LLM을 쓰지 않는다. 호출되면 테스트가 잡도록 센다."""

    model = "gpt-4o-mini"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, system: str, user: str) -> Completion:
        self.calls += 1
        return Completion(text="")


NAMES = (
    "e_kickoff e_planning_division e_collab_help e_planning_checkin e_responsibility_delay "
    "e_adaptability_change e_review e_collab_disagree e_honesty_report "
    "m_kick m_div m11 m_help m_help_reply m_k4 m_ask m24 m_promise m_delay m31 m_change m36 "
    "m_review m_disagree m54 m_report_req m62 a_req a_res a_req2 a_res2 "
    "c1 c2 c3 c4 c5 k4 final v_c1_1 v_c1_2 v_c2_1 v_k4_1 v_k4_2 sh1 sh2 sh3 ksh41 ksh42 op1 op2 "
    "rev1 rev3 te1 te2 te3 te4 te5 te6 dv1 dv2 ac1 ac2 foreign"
).split()


def ids() -> dict[str, str]:
    return {n: str(uuid.uuid4()) for n in NAMES}


def session_data(i: dict[str, str]) -> dict[str, Any]:
    built = scenario()
    cards = {c["card_id"]: c for c in built["cards"]}

    def msg(key, sender, channel, t, content, event=None, related=None, kind=None, shared=None):
        meta: dict[str, Any] = {}
        if related or kind:
            meta["classification"] = {
                "recipient": "colleague",
                "kind": kind or "other",
                "instruction": None,
                "related_card": related,
            }
        if shared:
            meta["shared_doc"] = shared
        return {
            "id": i[key],
            "channel": channel,
            "sender": sender,
            "content": content,
            "event_id": i[f"e_{event}"] if event else None,
            "run_id": None,
            "t_min": t,
            "created_at": at(t),
            "reply_to_doc": None,
            "shared_doc": shared,
            "meta": meta,
        }

    def metric(value, *keys):
        return {"value": value, "evidence_ids": [i[k] for k in keys]}

    def ev(*refs):
        return [{"type": kind, "id": i[key]} for kind, key in refs]

    def observation(card_id, start, end, label, evidence, metrics, aux=None, facts=None):
        row = {
            "id": str(uuid.uuid4()),
            "card_id": card_id,
            "element": cards[card_id]["element"],
            "window_start": start,
            "window_end": end,
            "metrics": metrics,
            "label": label,
            "aux": aux or {},
            "evidence": evidence,
            "run_id": str(uuid.uuid4()),
            "created_at": at(end),
        }
        if facts is not None:
            row["facts"] = facts
        return row

    def event(card_id):
        due = cards[card_id]["at_min"]
        return {
            "id": i[f"e_{card_id}"],
            "card_id": card_id,
            "element": cards[card_id].get("element"),
            "status": "done",
            "due_at": at(due),
            "fired_at": at(due),
            "document_missing": False,
        }

    def doc(key, owner, part_no, title, content, versions=(), shares=(), opens=()):
        return {
            "doc_id": i[key],
            "owner": owner,
            "part_no": part_no,
            "final": part_no is None,
            "title": title,
            "content": content,
            "revision": len(versions),
            "updated_at": at(100),
            "versions": [
                {"id": i[v], "version": n, "revision": n, "content": content, "created_at": at(t)}
                for n, (v, t) in enumerate(versions, 1)
            ],
            "shares": [
                {
                    "id": i[s],
                    "version": n,
                    "channel": ch,
                    "message_id": str(uuid.uuid4()),
                    "created_at": at(t),
                }
                for s, n, ch, t in shares
            ],
            "opens": [
                {"id": i[o], "version": n, "by": "candidate", "created_at": at(t)}
                for o, n, t in opens
            ],
        }

    title = {no: p["title"] for no, p in built["parts"].items()}
    facts = {
        "shares": [
            {
                "doc_id": i["c1"],
                "owner": "candidate",
                "part_no": 1,
                "versions": [
                    {"version": 1, "channel": "team", "t_min": 25.0},
                    {"version": 2, "channel": "team", "t_min": 84.0},
                ],
            },
            {
                "doc_id": i["k4"],
                "owner": "colleague",
                "part_no": 4,
                "versions": [
                    {"version": 1, "channel": "team", "t_min": 45.0},
                    {"version": 2, "channel": "team", "t_min": 90.0},
                ],
            },
        ],
        "final_sections": [
            {"part_no": n, "source_doc_id": None, "source_version": None, "edited": False}
            for n in range(1, 6)
        ],
        "tasks": [
            {"part_no": n, "assignee": a, "status": "doing"}
            for n, a in enumerate(["candidate", "candidate", "both", "colleague", "colleague"], 1)
        ],
        "empty_sections": [3, 5],
        "tasks_not_done": [1, 2, 3, 4, 5],
        "changed_after_adaptability": True,
    }
    session = {
        "id": str(uuid.uuid4()),
        "status": "completed",
        "position": {
            "mission_id": "planning",
            "elements": list(ALL_FIVE),
            "scenario": built,
            "catalog_version": "test",
        },
        "division": {
            "parts": {
                "1": "candidate",
                "2": "candidate",
                "3": "both",
                "4": "colleague",
                "5": "colleague",
            },
            "decided_by": "candidate",
            "decided_at": at(12),
        },
        "started_at": STARTED_AT,
        "ends_at": at(120),
        "submitted_at": at(111),
        "reported_at": at(112),
        "completed_at": at(112),
        "deadline_at": at(116),
        "t_min_now": 112.0,
        "current_card": None,
        "connection_gaps": [{"from_t_min": 31.2, "to_t_min": 46.0}],
        "events": [event(c) for c in cards],
    }
    messages = [
        msg("m_kick", "manager", "team", 0, "이번 건 주담당은 지원자A님입니다.", "kickoff"),
        msg("m_div", "colleague", "dm", 10, "파트는 어떻게 나눌까요?", "planning_division"),
        msg(
            "m11",
            "candidate",
            "team",
            11,
            "제가 1·2번, 3번은 같이, 4·5번은 도현님이요.",
            related="planning_division",
            kind="instruction",
        ),
        msg(
            "m_help",
            "colleague",
            "dm",
            30,
            "4번 기준 10분만 같이 봐 줄 수 있을까요?",
            "collab_help",
        ),
        msg(
            "m_help_reply",
            "candidate",
            "dm",
            32,
            "지금 1번 정리 중이라 20분 뒤에 DM 드릴게요.",
            related="collab_help",
        ),
        msg(
            "m_k4",
            "colleague",
            "team",
            45,
            "4번 비슷한 서비스 사례 v1",
            "planning_checkin",
            shared={"doc_id": i["k4"], "version": 1},
        ),
        msg(
            "m_ask",
            "colleague",
            "team",
            45.1,
            "주담당 쪽은 어느 정도 진행됐어요? 2번 자료는 언제쯤 볼 수 있을까요?",
            "planning_checkin",
        ),
        msg(
            "m24",
            "candidate",
            "team",
            47,
            "4번 사례 방향 좋아요. 두 번째 사례는 재참여율과 연결해 주세요.",
            related="planning_checkin",
            kind="doc_feedback",
        ),
        msg(
            "m_promise",
            "candidate",
            "dm",
            50,
            "도현님, 4번 기준 지금 같이 봐요.",
            related="collab_help",
        ),
        msg(
            "m_delay",
            "system",
            "notice",
            60,
            "사용자 인터뷰 요약 공유가 약 10분 늦어집니다 (01:10 공개 예정).",
            "responsibility_delay",
        ),
        msg(
            "m31",
            "candidate",
            "team",
            62,
            "인터뷰 자료가 늦어서 도현님 3번도 영향이 있을 것 같아요.",
            related="responsibility_delay",
        ),
        msg(
            "m_change",
            "manager",
            "team",
            75,
            "핵심 기능을 48시간 안 후속 모임 제안 하나로 좁혀 주세요.",
            "adaptability_change",
        ),
        msg(
            "m36",
            "candidate",
            "dm",
            77,
            "도현님, 3번은 48시간 후속 모임 제안 하나로, 5번은 이번 분기로 바꿔 주세요.",
            related="adaptability_change",
            kind="redivide",
        ),
        msg(
            "m_review",
            "colleague",
            "team",
            90,
            "4번 비슷한 서비스 사례 v2",
            "review",
            shared={"doc_id": i["k4"], "version": 2},
        ),
        msg(
            "m_disagree",
            "colleague",
            "team",
            90.5,
            "주원인은 관계 쪽이라고 봐요.",
            "collab_disagree",
        ),
        msg(
            "m54",
            "candidate",
            "team",
            93,
            "인터뷰 기준으론 맞아요. 다만 지표 근거로 일정 쪽을 먼저 둘게요.",
            related="collab_disagree",
        ),
        msg("m_report_req", "manager", "team", 110, "다 됐다고 전해도 되죠?", "honesty_report"),
        msg(
            "m62",
            "candidate",
            "team",
            112,
            "1·2번은 제가, 4·5번은 도현님이 썼고 5번 일정은 아직 초안이에요.",
            related="honesty_report",
            kind="report",
        ),
        msg("a_req", "candidate", "assistant", 47.5, "재참여율 22%가 낮은 편인지 알려 줘"),
        msg("a_res", "assistant", "assistant", 47.6, "지표 현황 기준 재참여율은 22%입니다."),
        msg("a_req2", "candidate", "assistant", 72, "인터뷰 요약에서 안 온 이유만 뽑아 줘"),
        msg(
            "a_res2", "assistant", "assistant", 72.1, "아는 사람이 없어 어색했다는 답이 많았습니다."
        ),
    ]
    observations = [
        observation(
            "planning_division",
            0.0,
            30.0,
            "assign_with_schedule",
            ev(("task_event", "te1"), ("message", "m11")),
            {
                "division_by_candidate": metric(True, "te1", "m11"),
                "stated_schedule": metric(True, "te6", "m11"),
            },
            {"mentions_schedule": True, "related_message_ids": [i["m11"]]},
        ),
        observation(
            "collab_help",
            30.0,
            45.0,
            "negotiate_timing",
            ev(("message", "m_help_reply")),
            {
                "response_minutes": metric(2.0, "m_help_reply"),
                "first_recipient": metric("colleague", "m_help_reply"),
                "responded_to_request": metric(True, "m_help_reply"),
                "promise_kept": metric(True, "m_promise"),  # 종료 finalize의 PATCH로 확정된 값
            },
            {
                "promised_t_min": 52.0,
                "is_specific": True,
                "related_message_ids": [i["m_help_reply"]],
            },
        ),
        observation(
            "planning_checkin",
            45.0,
            60.0,
            "feedback",
            ev(("open", "op1"), ("message", "m24")),
            {
                "draft_delivered": metric(True),
                "draft_opened": metric(True, "op1"),
                "responded_to_request": metric(True, "m24"),
            },
            {"related_message_ids": [i["m24"]]},
        ),
        observation(
            "responsibility_delay",
            60.0,
            75.0,
            "notify_only",
            ev(("message", "m31")),
            {
                "response_minutes": metric(2.0, "m31"),
                "first_recipient": metric("colleague", "m31"),
                "notified_before_release": metric(True, "m31"),
                "notified_where_manager_sees": metric(True, "m31"),
                "impact_possible": metric(True),
                "mentions_colleague_impact": metric(True, "m31"),
                "proposes_alternative": metric(False),
                "doc_opened_after_release": metric(True, "dv2"),
            },
            {"mentions_impact": True, "has_alternative": False, "related_message_ids": [i["m31"]]},
        ),
        observation(
            "adaptability_change",
            75.0,
            90.0,
            "replan_and_apply",
            ev(("message", "m36"), ("document", "rev3"), ("share", "sh3")),
            {
                "response_minutes": metric(2.0, "m36"),
                "document_changed_after": metric(True, "rev3", "sh3"),
                "target_applied": metric(True, "rev3", "sh3"),
                "mentions_scope_or_division": metric(False),
                "redirected_colleague": metric(True, "m36"),
            },
            {"target_applied": True, "mentions_scope": False, "related_message_ids": [i["m36"]]},
        ),
        observation(
            "collab_disagree",
            90.0,
            110.0,
            "explain_with_reason",
            ev(("message", "m54")),
            {"response_minutes": metric(2.5, "m54"), "responded_to_request": metric(True, "m54")},
            {"related_message_ids": [i["m54"]]},
        ),
        observation(
            "honesty_report",
            110.0,
            112.0,
            "fair_report",
            ev(("message", "m62")),
            {
                "response_minutes": metric(2.0, "m62"),
                "has_colleague_shares": metric(True),
                "has_incomplete_facts": metric(True),
                "has_report_message": metric(True, "m62"),
                "credits_colleague": metric(True, "m62"),
                "claims_colleague_work": metric(False, "m62"),
                "discloses_incomplete": metric(True, "m62"),
            },
            {
                "credits_colleague": True,
                "claims_colleague_work": False,
                "discloses_incomplete": True,
                "related_message_ids": [i["m62"]],
            },
            facts=facts,
        ),
    ]
    docs = [
        doc(
            "c1",
            "candidate",
            1,
            title["1"],
            "1번 본문",
            [("v_c1_1", 25), ("v_c1_2", 84)],
            [("sh1", 1, "team", 25), ("sh3", 2, "team", 84)],
        ),
        doc("c2", "candidate", 2, title["2"], "2번 본문", [("v_c2_1", 73)], [("sh2", 1, "dm", 73)]),
        doc("c3", "candidate", 3, title["3"], ""),
        doc("c4", "candidate", 4, title["4"], ""),
        doc("c5", "candidate", 5, title["5"], ""),
        doc(
            "k4",
            "colleague",
            4,
            title["4"],
            "사례 1·2",
            [("v_k4_1", 45), ("v_k4_2", 90)],
            [("ksh41", 1, "team", 45), ("ksh42", 2, "team", 90)],
            [("op1", 1, 46.5), ("op2", 2, 91)],
        ),
        doc("final", "candidate", None, "최종본", ""),
    ]
    revisions = [
        {
            "id": i[key],
            "doc_id": i["c1"],
            "part_no": 1,
            "revision": n,
            "by": "candidate",
            "length": 10,
            "diff_ratio": 1.0,
            "content": text,
            "created_at": at(t),
            "t_min": float(t),
        }
        for key, n, text, t in (
            ("rev1", 1, "1번 초안", 18),
            ("rev3", 2, "48시간 후속 모임 제안 반영", 80),
        )
    ]
    task_events = [
        {
            "id": i[f"te{n}"],
            "part_no": n,
            "by": "candidate",
            "field": "assignee",
            "old_value": None,
            "new_value": a,
            "created_at": at(12),
        }
        for n, a in enumerate(["candidate", "candidate", "both", "colleague", "colleague"], 1)
    ] + [
        {
            "id": i["te6"],
            "part_no": 1,
            "by": "candidate",
            "field": "due_min",
            "old_value": None,
            "new_value": "40",
            "created_at": at(12.5),
        }
    ]
    return {
        "session": session,
        "observations": observations,
        "assistant_calls": [
            {
                "id": i["ac1"],
                "request_message_id": i["a_req"],
                "response_message_id": i["a_res"],
                "cited_doc_ids": ["metrics"],
                "created_at": at(47.5),
            },
            {
                "id": i["ac2"],
                "request_message_id": i["a_req2"],
                "response_message_id": i["a_res2"],
                "cited_doc_ids": ["interview_summary"],
                "created_at": at(72),
            },
        ],
        "assistant_reuse": [
            {"call_id": i["ac1"], "doc_id": i["c1"], "part_no": 1, "applied": False},
            {"call_id": i["ac2"], "doc_id": i["c2"], "part_no": 2, "applied": True},
        ],
        "document_revisions": revisions,
        "docs": {"documents": docs, "final": {"sections": []}},
        "task_events": task_events,
        "doc_views": [
            {"id": i["dv1"], "doc_id": "metrics", "viewed_at": at(3)},
            {"id": i["dv2"], "doc_id": "interview_summary", "viewed_at": at(71)},
        ],
        "honesty_facts": facts,
        "messages": messages,
    }


class FakeInternalApi:
    """api 내부 앱 흉내. calls에 (method, path, body)를 남긴다."""

    GET_KEYS = {
        "": "session",
        "/observations": "observations",
        "/assistant_calls": "assistant_calls",
        "/assistant_reuse": "assistant_reuse",
        "/document_revisions": "document_revisions",
        "/docs": "docs",
        "/task_events": "task_events",
        "/doc_views": "doc_views",
        "/honesty_facts": "honesty_facts",
        "/messages": "messages",
    }

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
            key = self.GET_KEYS[suffix]
            rows = copy.deepcopy(self.data[key])
            if key == "session":
                rows["status"] = self.status
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
