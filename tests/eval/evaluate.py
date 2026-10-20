"""근거 정확성 실행기: 질문 10건 + 유출 3종 + 선점 3종을 실제 경로(공개 REST·WS)로 묻고 판정한다.

케이스마다 6분 세션을 새로 만들어 at(분 또는 카드)까지 진행한 뒤 동료·팀장(WS message.send) 또는
어시스턴트(POST /assistant)에 묻는다. 도구는 그 run의 agent.progress tool_start에서, 인용은
동료·팀장 응답의 문서 제목(guard 별칭 포함)·어시스턴트 cited_docs에서 읽는다. LLM은 실행
환경이 정한다(테스트 기본 FakeLLM, `-m live`는 gpt-4o-mini).

입력 거부 3종(evidence_rejections)은 같은 세션으로 확인한다: 다른 세션 id를 섞은 관찰 저장은 422,
관찰 분류가 창 밖 메시지를 근거로 골라도 저장된 근거에 없음, 어시스턴트가 검색하지 않은 문서를
인용해도 응답·cited_docs에 없음.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from e2e.client import Api, Socket, Target, Transcript, parse_time

from scripts import make_session

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parents[1] / "scenarios" / "missions" / "planning" / "prompts" / "fixtures"
TOOLS = {
    "colleague": {"search_documents", "get_document", "get_board", "get_shared_documents"},
    "manager": {"search_documents", "get_board", "get_shared_documents"},
    "assistant": {"search_documents", "get_document"},
}
CHANNEL = {"colleague": "dm", "manager": "manager_dm"}
DIVISION = {1: "candidate", 2: "candidate", 3: "both", 4: "colleague", 5: "colleague"}
REPLY_SECONDS = 90


def aliases() -> dict[str, list[str]]:
    data = yaml.safe_load((FIXTURES.parent / "guard_patterns.yaml").read_text("utf-8"))

    def find(node: Any) -> dict | None:
        if isinstance(node, dict):
            if (
                "metrics" in node
                and isinstance(node["metrics"], dict)
                and "aliases" in node["metrics"]
            ):
                return node
            for value in node.values():
                if (found := find(value)) is not None:
                    return found
        return None

    return {doc_id: v["aliases"] for doc_id, v in find(data).items()}


def load_cases() -> list[dict[str, Any]]:
    """cases.yaml의 ref를 prompts 픽스처로 풀어 한 형식({id, group, persona, question, ...})으로."""
    spec = yaml.safe_load((HERE / "cases.yaml").read_text("utf-8"))
    sources: dict[str, dict[str, dict]] = {}
    cases = []
    for group in ("grounding", "leak", "preemption"):
        for item in spec[group]:
            case = dict(item)
            if "ref" in item:
                name, case_id = item["ref"].split("#")
                if name not in sources:
                    raw = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text("utf-8"))["cases"]
                    sources[name] = {c["id"]: c for c in raw}
                case = {**sources[name][case_id], **{k: v for k, v in item.items() if k != "ref"}}
            case["group"] = group
            case.setdefault("persona", "colleague")
            candidate = case.get("candidate") or {}
            case.setdefault("question", candidate.get("content"))
            cases.append(case)
    return cases


REFUSAL = re.compile(r"[^.!?\n]*아직\s*공유되지\s*않은\s*자료[^.!?\n]*")


def cited_titles(reply: str, names: dict[str, list[str]]) -> set[str]:
    """응답에 이름이 나온 문서. 미공개 안내 문장("…는 아직 공유되지 않은 자료예요")의 문서명은
    인용이 아니다.
    """
    text = REFUSAL.sub("", reply)
    return {doc_id for doc_id, words in names.items() if any(w in text for w in words)}


def judge(case: dict[str, Any], got: dict[str, Any], names: dict[str, list[str]]) -> list[str]:
    """실패 문장 목록. 빈 목록이면 통과."""
    fails = []
    reply = got.get("reply") or ""
    if not reply:
        return ["no reply"]
    tools = set(got["tools"])
    if missing := set(case.get("expected_tools") or []) - tools:
        fails.append(f"tool not called: {sorted(missing)}")
    if extra := tools - TOOLS[case["persona"]]:
        fails.append(f"tool outside allowlist: {sorted(extra)}")
    if "allowed_docs" in case:
        cited = set(got["cited"])
        if outside := cited - set(case["allowed_docs"]):
            fails.append(f"cited outside allowed: {sorted(outside)}")
        titles = {names[d][0]: d for d in names}
        for title in case.get("expected_citation") or []:
            if titles.get(title) not in cited:
                fails.append(f"citation missing: {title}")
    if case.get("expected_fact") and not re.search(case["expected_fact"], reply):
        fails.append(f"fact missing: {case['expected_fact']}")
    for pattern in case.get("must_not_regex") or []:
        if re.search(pattern, reply, re.IGNORECASE):
            fails.append(f"must_not matched: {pattern}")
    should = case.get("should_regex") or []
    if should and not any(re.search(p, reply) for p in should):
        fails.append("no should_regex matched")
    return fails


class Session:
    """케이스 하나의 세션(관리자·지원자 토큰, WS, 시계)."""

    def __init__(self, target: Target, transports: dict | None, clock_factory) -> None:
        self.transcript = Transcript()
        self.api = Api(target, self.transcript, transports=transports)
        self.socket = Socket(self.transcript)
        self.target = target
        self.clock_factory = clock_factory

    async def open(self, elements: list[str], alias: str) -> None:
        made = await make_session.make(self.api.public, self.api.internal, elements, 6, alias=alias)
        self.sid = made.session_id
        r = await self.api.call("POST", f"/s/{made.invite_token}/consent")
        self.token = r.json()["session_token"]
        r = await self.api.call("POST", f"/s/{made.invite_token}/start", token=self.token)
        started = parse_time(r.json()["started_at"])
        self.clock = await self.clock_factory(self.sid, made.invite_token, started)
        await self.socket.connect(self.target.ws_url(self.sid, self.token))
        for part, assignee in DIVISION.items():
            await self.api.call(
                "PUT",
                f"/sessions/{self.sid}/tasks/{part}",
                token=self.token,
                json_body={"assignee": assignee},
            )
        await self.clock.settle()

    async def events(self) -> dict[str, dict[str, Any]]:
        r = await self.api.call("GET", f"/internal/sessions/{self.sid}", internal=True, log=False)
        session = r.json()
        start = parse_time(session["started_at"])
        return {
            e["card_id"]: {**e, "due_min": (parse_time(e["due_at"]) - start).total_seconds() / 60}
            for e in session["events"]
        }

    async def go_to(self, at: float | str) -> None:
        if isinstance(at, str):
            event = (await self.events())[at]
            await self.clock.advance_to(event["due_min"] + 0.01)
            await self.socket.wait_for(
                lambda f: (
                    f["type"] == "message.new" and f["payload"].get("event_id") == event["id"]
                ),
                timeout=self.clock.card_wait_seconds,
            )
        else:
            await self.clock.advance_to(at)
        await self.clock.settle()

    async def ask(self, persona: str, question: str, channel: str | None = None) -> dict[str, Any]:
        since = len(self.socket.frames)
        if persona == "assistant":
            r = await self.api.call(
                "POST",
                f"/sessions/{self.sid}/assistant",
                token=self.token,
                json_body={"prompt": question},
            )
            body = r.json()
            await self.clock.settle()
            tools = [
                f["payload"].get("tool")
                for f in self.socket.frames[since:]
                if f["type"] == "agent.progress"
                and f["payload"].get("actor") == "assistant"
                and f["payload"]["status"] == "tool_start"
            ]
            return {
                "reply": body.get("content"),
                "tools": tools,
                "cited": body.get("cited_docs") or [],
                "run_id": None,
            }
        ack = await self.socket.send_message(channel or CHANNEL[persona], question)
        await self.clock.settle()
        run_id = ack and ack["run_id"]
        reply = await self.socket.wait_for(
            lambda f: (
                f["type"] == "message.new"
                and f["payload"].get("run_id") == run_id
                and f["payload"]["sender"] == persona
            ),
            timeout=REPLY_SECONDS,
            since=since,
        )
        tools = [
            f["payload"].get("tool")
            for f in self.socket.frames[since:]
            if f["type"] == "agent.progress"
            and f["payload"].get("run_id") == run_id
            and f["payload"]["status"] == "tool_start"
        ]
        text = reply["payload"]["content"] if reply else None
        return {
            "reply": text,
            "tools": tools,
            "cited": sorted(cited_titles(text or "", aliases())),
            "run_id": run_id,
        }

    async def close(self) -> None:
        await self.socket.close()
        await self.api.aclose()


async def run_case(
    case: dict[str, Any], target: Target, transports, clock_factory
) -> dict[str, Any]:
    session = Session(target, transports, clock_factory)
    try:
        await session.open(case["elements"], alias=case["id"])
        await session.go_to(case["at"])
        channel = (case.get("candidate") or {}).get("channel")
        got = await session.ask(
            case["persona"], case["question"], channel if channel != "assistant" else None
        )
    finally:
        await session.close()
    failures = judge(case, got, aliases())
    return {
        "id": case["id"],
        "group": case["group"],
        "persona": case["persona"],
        **got,
        "session_id": session.sid,
        "failures": failures,
        "ok": not failures,
    }


async def run_all(target: Target, transports, clock_factory, cases=None) -> list[dict[str, Any]]:
    return [await run_case(c, target, transports, clock_factory) for c in cases or load_cases()]


def write_live_record(
    results: list[dict[str, Any]], out: Path, rejections: dict | None = None
) -> Path:
    """records/eval-live-<일시>.md: 케이스별 결과·run_id(LangSmith 필터)·응답 첫 줄."""
    import os

    path = out / f"eval-live-{datetime.now():%Y%m%d-%H%M}.md"
    project = os.environ.get("LANGCHAIN_PROJECT")
    passed = sum(r["ok"] for r in results)
    lines = [
        "# 근거 정확성 live (gpt-4o-mini)",
        "",
        f"- 통과 {passed}/{len(results)}",
        f"- LangSmith: 프로젝트 `{project}`, 케이스별 run_id로 metadata 필터"
        if project
        else "- LangSmith: 트레이싱 꺼짐",
        "",
        "| 묶음 | 케이스 | 역할 | 결과 | 도구 | 인용 | run_id | 실패 | 응답 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        reply = (r.get("reply") or "").replace("\n", " ").replace("|", "\\|")[:120]
        lines.append(
            f"| {r['group']} | {r['id']} | {r['persona']} | {'통과' if r['ok'] else '실패'} | "
            f"{', '.join(r['tools']) or '-'} | {', '.join(r['cited']) or '-'} | `{r['run_id']}` | "
            f"{'<br>'.join(r['failures'])} | {reply} |"
        )
    if rejections:
        lines += ["", "## 입력 거부", ""] + [
            f"- {k}: {'통과' if v else '실패'}" for k, v in rejections.items()
        ]
    out.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", "utf-8")
    return path
