"""e2e 러너: 실제 서비스를 상대로 대본을 끝까지 돌리고 단언·기록을 남긴다.

형식과 단언은 docs/common/testing.md e2e 절.

    uv run --project services/api python tests/e2e/run.py --script all_five
    uv run --project services/api python tests/e2e/run.py --concurrent      # 단언 7
    uv run --project services/api python tests/e2e/run.py --auth            # 단언 8
    uv run --project services/api python tests/e2e/run.py --faults all      # 단언 6(러너가 앱 기동)

흐름: 세션 조립(make_session) → 동의·시작 → WS 연결 → step마다 시각까지 기다려 실행 → 제출·보고 →
종료 대기 → report_ready 대기 → 관리자 draft·검토(2a)·final·전체 기록 → 내부 API·DB에서 결과 수집 →
단언(asserts.py) → 기록(records.py).

시각: Clock이 "세션 분"을 다룬다. 실 스택은 벽시계(WallClock)로 기다리고, 테스트는 DB 시각을 당기는
시계를 끼운다(tests/e2e/conftest.py). 카드 step은 그 카드의 message.new(event_id)를 받은 시각을
기준으로 삼는다. 실패한 step은 멈추지 않고 step_errors에 남긴다(러너는 결함을 가리지 않는다).
"""

import argparse
import asyncio
import contextlib
import re
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# 저장소 루트(scripts)와 tests/(e2e 패키지). 최상위 이름 tests는 api 테스트 패키지가 쓴다
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
from e2e import asserts, records  # noqa: E402
from e2e import script as scripts  # noqa: E402
from e2e.client import Api, Socket, Target, Transcript, parse_time  # noqa: E402
from e2e.faults import Faults  # noqa: E402
from scripts import make_session  # noqa: E402

EPSILON = 0.01  # 카드 due_at을 살짝 지나서 본다(분)
CARD_WAIT_SECONDS = 105  # 카드 메시지 90초(운영 목표) + 여유
REPORT_WAIT_SECONDS = 120
ENDED = {"completed", "report_ready", "approving", "reviewed", "failed", "cancelled"}


class Clock(Protocol):
    """세션 분 단위 시계. 실 스택은 벽시계, 테스트는 DB 시각 이동."""

    card_wait_seconds: float

    async def now(self) -> float: ...
    async def advance_to(self, minute: float) -> None: ...
    async def settle(self) -> None: ...
    async def idle(self) -> None: ...


class WallClock:
    card_wait_seconds = CARD_WAIT_SECONDS

    def __init__(self, started_at: datetime) -> None:
        self.started_at = started_at

    async def now(self) -> float:
        return (datetime.now(UTC) - self.started_at).total_seconds() / 60

    async def advance_to(self, minute: float) -> None:
        wait = (minute - await self.now()) * 60
        if wait > 0:
            await asyncio.sleep(wait)

    async def settle(self) -> None:
        return None

    async def idle(self) -> None:
        await asyncio.sleep(2)


ClockFactory = Callable[[str, str, datetime], Awaitable[Clock]]


async def wall_clock(session_id: str, invite_token: str, started_at: datetime) -> Clock:
    return WallClock(started_at)


class StackControl(Protocol):
    """프로세스 제어(재시작·종료). stack.LocalStack이 구현, 없으면 restart step이 실패로 남는다."""

    async def restart_api(self) -> None: ...
    async def kill_api(self) -> None: ...
    async def start_api(self) -> None: ...


class StepError(Exception):
    pass


class Runner:
    def __init__(
        self,
        script: dict[str, Any],
        target: Target,
        *,
        clock_factory: ClockFactory = wall_clock,
        stack: StackControl | None = None,
        faults: Faults | None = None,
        transports: dict[str, httpx.AsyncBaseTransport] | None = None,
        admin: make_session.Admin | None = None,
        alias: str = "e2e",
    ) -> None:
        self.script = script
        self.target = target
        self.clock_factory = clock_factory
        self.stack = stack
        self.faults = faults
        self.admin_account = admin
        self.alias = alias
        self.transcript = Transcript()
        self.api = Api(target, self.transcript, transports=transports)
        self.socket = Socket(self.transcript)
        self.vars: dict[str, str] = {}
        self.b: dict[str, Any] = {
            "script": script,
            "name": script["name"],
            "elements": script["elements"],
            "step_errors": [],
            "steps": [],
            "says": [],
            "writes": [],
            "shares": [],
            "opens": [],
            "imports": [],
            "resumes": [],
            "submit": None,
            "restart": None,
            "injects": [],
            "review": {},
            "db": {},
        }
        self.last_at = 0.0
        self.report_wait_seconds = REPORT_WAIT_SECONDS
        self.regenerate_on_failure = (
            False  # 장애 주입 report_3fail: failed(report)면 regenerate 1회
        )

    # ───────────── 진행 ─────────────

    async def run(self) -> dict[str, Any]:
        watcher = None
        try:
            await self.open_session()
            watcher = asyncio.create_task(self.watch_events())
            for index, step in enumerate(self.script["steps"]):
                await self.run_step(index, step)
            await self.wait_ended()
            await self.report_phase()
            await self.collect()
        finally:
            if watcher is not None:
                watcher.cancel()
            await self.socket.close()
            await self.api.aclose()
        self.b["transcript"] = self.transcript.lines
        self.b["frames"] = self.socket.frames
        return self.b

    async def open_session(self) -> None:
        made = await make_session.make(
            self.api.public,
            self.api.internal,
            self.script["elements"],
            self.script["minutes"],
            admin=self.admin_account,
            alias=self.alias,
        )
        self.made = made
        self.b["session_id"] = self.sid = made.session_id
        self.b["admin_email"] = made.admin.email
        r = await self.api.call("POST", f"/s/{made.invite_token}/consent")
        r.raise_for_status()
        self.token = r.json()["session_token"]
        r = await self.api.call("POST", f"/s/{made.invite_token}/start", token=self.token)
        r.raise_for_status()
        started_at = parse_time(r.json()["started_at"])
        self.clock = await self.clock_factory(self.sid, made.invite_token, started_at)
        self.b["state_start"] = (await self.get("/state")).json()
        await self.socket.connect(self.target.ws_url(self.sid, self.token))
        # 화면처럼 연결 뒤 /state로 따라잡는다: 연결 전에 나온 카드 메시지(킥오프)는 여기서만 보인다
        caught_up = (await self.get("/state")).json()["messages"]
        self.caught_up = {m["event_id"]: m for m in caught_up if m["event_id"]}
        self.b["caught_up_event_ids"] = sorted(self.caught_up)
        await self.refresh_events()

    async def watch_events(self) -> None:
        """카드 행의 (status, document_missing) 변화를 시간순으로 남긴다. C5처럼 재실행으로 지워지는
        중간 상태(document_missing=true)를 보려면 끝 상태가 아니라 이력이 필요하다."""
        last: dict[str, tuple] = {}
        history = self.b["event_history"] = []
        while True:
            with contextlib.suppress(Exception):
                r = await self.api.call(
                    "GET", f"/internal/sessions/{self.sid}", internal=True, log=False
                )
                for e in r.json()["events"]:
                    now = (e["status"], e["document_missing"])
                    if last.get(e["card_id"]) != now:
                        last[e["card_id"]] = now
                        history.append(
                            {
                                "at": time.time(),
                                "card_id": e["card_id"],
                                "status": now[0],
                                "document_missing": now[1],
                            }
                        )
            await asyncio.sleep(0.5)

    async def refresh_events(self) -> dict[str, Any]:
        r = await self.api.call("GET", f"/internal/sessions/{self.sid}", internal=True, log=False)
        r.raise_for_status()
        session = r.json()
        started = parse_time(session["started_at"])
        self.events = {
            e["card_id"]: {**e, "due_min": (parse_time(e["due_at"]) - started).total_seconds() / 60}
            for e in session["events"]
        }
        return session

    async def run_step(self, index: int, step: dict[str, Any]) -> None:
        at = step["at"]
        planned = None
        if isinstance(at, str) and at.startswith("+"):
            target = self.last_at + float(at[1:])
        elif isinstance(at, int | float):
            target = float(at)
        else:
            target = None
        if target is not None:
            await self.clock.advance_to(target)
            self.last_at = target
        else:
            planned, actual = await self.wait_card(at)
            self.last_at = actual if actual is not None else planned
        self.b["steps"].append(
            {"index": index, "at": at, "planned": planned, "t_min": round(self.last_at, 3)}
        )
        for action in scripts.actions(step):
            try:
                await getattr(self, f"do_{action}")(step[action], step)
            except StepError as exc:
                self.b["step_errors"].append(
                    {"index": index, "at": at, "action": action, "error": str(exc)}
                )
        await self.clock.settle()

    async def wait_card(self, card_id: str) -> tuple[float, float | None]:
        """그 카드의 due 시각까지 기다린 뒤 카드 메시지(message.new.event_id)를 받은 세션 분."""
        if card_id not in self.events:
            await self.refresh_events()
        event = self.events.get(card_id)
        if event is None:
            self.b["step_errors"].append({"at": card_id, "error": "card not in session_events"})
            return await self.clock.now(), None
        if event["id"] in self.caught_up:
            return event["due_min"], self.caught_up[event["id"]]["t_min"]
        await self.clock.advance_to(event["due_min"] + EPSILON)
        frame = await self.socket.wait_for(
            lambda f: f["type"] == "message.new" and f["payload"].get("event_id") == event["id"],
            timeout=self.clock.card_wait_seconds,
        )
        if frame is None:
            self.b["step_errors"].append({"at": card_id, "error": "card message not received"})
            return event["due_min"], None
        await self.clock.settle()
        return event["due_min"], frame["payload"]["t_min"]

    async def wait_ended(self) -> None:
        """세션이 completed 이후가 될 때까지(보고 메시지 또는 deadline). 상한은 ends_at+5분+여유."""
        limit = self.script["minutes"] + 7
        while True:
            session = await self.refresh_events()
            if session["status"] in ENDED:
                self.b["ended_status"] = session["status"]
                return
            if await self.clock.now() > limit:
                self.b["step_errors"].append(
                    {"at": "end", "error": f"not ended: {session['status']}"}
                )
                return
            await self.clock.idle()

    # ───────────── 지원자 행동 ─────────────

    def sub(self, value: str) -> str:
        return re.sub(r"\{(\w+)\}", lambda m: self.vars.get(m.group(1), m.group(0)), value)

    async def get(self, suffix: str) -> httpx.Response:
        return await self.api.call("GET", f"/sessions/{self.sid}{suffix}", token=self.token)

    async def send(self, method: str, suffix: str, body: Any = None, ok=(200,)) -> Any:
        r = await self.api.call(
            method, f"/sessions/{self.sid}{suffix}", token=self.token, json_body=body
        )
        if r.status_code not in ok:
            raise StepError(f"{method} {suffix} → {r.status_code} {r.text[:200]}")
        return r.json()

    async def my_documents(self) -> dict[str, Any]:
        return (await self.get("/my-documents")).json()

    async def received_doc(self, part_no: int) -> str:
        found = [
            d["doc_id"] for d in (await self.my_documents())["received"] if d["part_no"] == part_no
        ]
        if not found:
            raise StepError(f"colleague part {part_no} not received at {self.last_at:.2f}")
        return found[0]

    async def do_board(self, items: list[dict[str, Any]], step) -> None:
        for item in items:
            body = {k: v for k, v in item.items() if k not in ("part_no", "expect")}
            await self.send("PUT", f"/tasks/{item['part_no']}", body, ok=(item.get("expect", 200),))

    async def do_say(self, say: dict[str, Any], step) -> None:
        reply = None
        if say.get("reply_to_doc"):
            ref = say["reply_to_doc"]
            reply = {"doc_id": await self.received_doc(ref["part_no"]), "version": ref["version"]}
        content = self.sub(say["content"])
        sent_at = time.time()
        ack = await self.socket.send_message(say["channel"], content, reply)
        self.b["says"].append(
            {
                "t_min": self.last_at,
                "channel": say["channel"],
                "content": content,
                "run_id": ack and ack["run_id"],
                "message_id": ack and ack["message_id"],
                "sent_at": sent_at,
            }
        )
        if ack is None:
            raise StepError(f"no ack for {content[:30]}")

    async def do_write(self, write: dict[str, Any], step) -> None:
        part = write["part_no"]
        if part == "final":
            body = {"sections": write["content"]}
        else:
            body = {"content": self.sub(write["content"])}
        before = None
        if part != "final":
            before = next(
                d["revision"]
                for d in (await self.my_documents())["documents"]
                if d["part_no"] == part
            )
        saved = await self.send("PUT", f"/my-documents/{part}", body)
        self.b["writes"].append({"part_no": part, "before": before, "after": saved["revision"]})

    async def do_share(self, share: dict[str, Any], step) -> None:
        since = len(self.socket.frames)
        result = await self.send(
            "POST", f"/my-documents/{share['part_no']}/share", {"channel": share["channel"]}
        )
        shared = await self.socket.wait_for(
            lambda f: (
                f["type"] == "document.shared"
                and f["payload"].get("message_id") == result["message_id"]
            ),
            timeout=10,
            since=since,
        )
        self.b["shares"].append({**share, **result, "ws_shared": shared is not None})

    async def do_open(self, item: dict[str, Any], step) -> None:
        doc_id = await self.received_doc(item["part_no"])
        await self.send("POST", f"/documents/{doc_id}/open", {"version": item["version"]})
        self.b["opens"].append({**item, "doc_id": doc_id})

    async def do_import(self, items: list[dict[str, Any]], step) -> None:
        for item in items:
            if item["from"] == "colleague":
                source = await self.received_doc(item["part_no"])
            else:
                docs = (await self.my_documents())["documents"]
                source = next(d["doc_id"] for d in docs if d["part_no"] == item["part_no"])
            section = await self.send(
                "PUT",
                f"/final/sections/{item['part_no']}/import",
                {"source_doc_id": source, "version": item["version"]},
            )
            self.b["imports"].append({**item, "source_doc_id": source, "section": section})

    async def do_view(self, doc_id: str, step) -> None:
        await self.send("GET", f"/documents/{doc_id}")

    async def do_assistant(self, prompt: str, step) -> None:
        result = await self.send("POST", "/assistant", {"prompt": self.sub(prompt)})
        if step.get("capture_as"):
            self.vars[step["capture_as"]] = result["content"]
        self.b.setdefault("assistant_calls", []).append(result["call_id"])

    async def do_submit(self, _: Any, step) -> None:
        since = len(self.socket.frames)
        result = await self.send("POST", "/submit")
        self.b["submit"] = {"t_min": self.last_at, "response": result, "frame_index": since}

    async def do_restart(self, what: str, step) -> None:
        """api 프로세스 재시작 → resume·state가 90초 안에 되는지 잰다(단언 5)."""
        if self.stack is None:
            raise StepError("restart needs --manage-stack")
        before = await self.refresh_events()
        await self.socket.close()
        started = time.time()
        await self.stack.restart_api()
        restored = await self.reconnect(started)
        self.b["restart"] = {"events_before": before["events"], "restored_seconds": restored}
        if restored is None:
            raise StepError("state not restored within 120s")

    async def reconnect(self, started: float | None = None) -> float | None:
        """api가 다시 뜬 뒤 resume(새 JWT) → /state → WS 재연결. /state까지 걸린 초(실패면 None)."""
        started = started or time.time()
        await self.socket.close()
        while time.time() - started < 120:
            with contextlib.suppress(httpx.TransportError):
                r = await self.api.call("POST", f"/s/{self.made.invite_token}/resume")
                if r.status_code == 200:
                    self.token = r.json()["session_token"]
                    if (await self.get("/state")).status_code == 200:
                        restored = time.time() - started
                        await self.socket.connect(self.target.ws_url(self.sid, self.token))
                        return restored
            await asyncio.sleep(1)
        return None

    async def do_disconnect(self, seconds: float, step) -> None:
        """WS를 실제로 끊고 seconds 뒤 resume(새 JWT) → state → 재연결."""
        await self.socket.close()
        await self.clock.advance_to(await self.clock.now() + seconds / 60)
        old = self.token
        r = await self.api.call("POST", f"/s/{self.made.invite_token}/resume")
        if r.status_code != 200:
            raise StepError(f"resume → {r.status_code}")
        self.token = r.json()["session_token"]
        state = (await self.get("/state")).json()
        self.b["resumes"].append(
            {
                "status": state["session"]["status"],
                "deadline_at": state["session"]["deadline_at"],
                "new_token": self.token != old,
            }
        )
        await self.socket.connect(self.target.ws_url(self.sid, self.token))

    async def do_inject(self, inject: dict[str, Any], step) -> None:
        if self.faults is None:
            raise StepError("inject needs the fault proxy (--manage-stack)")
        self.faults.fail_tool(inject["tool"], inject["fail_times"])
        self.b["injects"].append(inject)
        if inject["tool"] == "send_document":
            self.b["fault"] = {"name": "doc_fail"}  # 단언 6의 동료 문서 보내기 실패(C5)

    # ───────────── 리포트·검토 ─────────────

    async def admin(self, method: str, suffix: str, body: Any = None) -> httpx.Response:
        return await self.api.call(
            method,
            f"/admin/sessions/{self.sid}{suffix}",
            token=self.made.admin.token,
            json_body=body,
        )

    async def wait_report(self, stage: str) -> dict[str, Any] | None:
        started = time.time()
        while time.time() - started < self.report_wait_seconds:
            r = await self.admin("GET", "/report")
            if r.status_code == 200 and r.json()["stage"] == stage:
                return r.json()
            session = await self.refresh_events()
            if session["status"] == "failed":
                if not self.regenerate_on_failure or self.b.get("regenerated") is not None:
                    return None
                self.b["regenerated"] = (await self.admin("POST", "/report/regenerate")).status_code
            await asyncio.sleep(1)
        return None

    async def report_phase(self) -> None:
        draft = await self.wait_report("draft")
        self.b["report_draft"] = draft
        if draft is None:
            self.b["step_errors"].append({"at": "report", "error": "report_ready not reached"})
            return
        self.b["db"]["hash_draft"] = await self.report_hash()
        item, value = pick_adjustment(draft)
        review = self.b["review"]
        review["item"] = {"id": item["id"], "auto": item["auto"], "value": value}
        no_memo = {"adjustments": [{"item_id": item["id"], "value": value}], "reviewer_name": "e2e"}
        review["no_memo_status"] = (await self.admin("POST", "/review", no_memo)).status_code
        body = {
            "adjustments": [{"item_id": item["id"], "value": value, "memo": "e2e 조정 메모"}],
            "memo": "e2e 검토",
            "reviewer_name": "e2e 검토자",
        }
        first = await self.admin("POST", "/review", body)
        again = await self.admin("POST", "/review", body)
        review["status"], review["again"] = first.status_code, again.status_code
        review["again_body"] = again.json() if again.status_code == 200 else None
        final = await self.wait_report("final")
        self.b["report_final"] = final
        if final is None:
            self.b["step_errors"].append({"at": "report", "error": "final not reached"})
            return
        self.b["db"]["hash_final"] = await self.report_hash()
        changed = {
            **body,
            "adjustments": [{**body["adjustments"][0], "value": item["auto"], "memo": "재조정"}],
        }
        review["readjust_status"] = (await self.admin("POST", "/review", changed)).status_code
        note = {"text": "e2e 메모", "reviewer_name": "e2e 검토자"}
        review["notes_status"] = (await self.admin("POST", "/report/notes", note)).status_code
        self.b["record"] = (await self.admin("GET", "/record")).json()

    # ───────────── 수집 ─────────────

    async def internal(self, suffix: str) -> Any:
        r = await self.api.call(
            "GET", f"/internal/sessions/{self.sid}{suffix}", internal=True, log=False
        )
        r.raise_for_status()
        return r.json()

    async def collect(self) -> None:
        b = self.b
        b["session"] = await self.internal("")
        b["scenario"] = b["session"]["position"]["scenario"]
        messages, offset = [], 0
        while True:
            page = await self.internal(f"/messages?limit=500&offset={offset}")
            messages += page
            if len(page) < 500:
                break
            offset += 500
        b["messages"] = messages
        for key, suffix in (
            ("observations", "/observations"),
            ("docs", "/docs"),
            ("task_events", "/task_events"),
            ("doc_views", "/doc_views"),
            ("assistant_calls_internal", "/assistant_calls"),
            ("assistant_reuse", "/assistant_reuse"),
            ("revisions", "/document_revisions"),
        ):
            b[key] = await self.internal(suffix)
        r = await self.get("/state")
        b["state_end"] = r.json() if r.status_code == 200 else None
        await self.collect_db()

    async def sql(self, query: str, **params: Any) -> list[dict[str, Any]]:
        if not self.target.database_url:
            return []
        engine = create_async_engine(self.target.database_url)
        try:
            async with engine.connect() as conn:
                rows = await conn.execute(text(query), params)
                return [dict(r._mapping) for r in rows]
        finally:
            await engine.dispose()

    async def report_hash(self) -> str | None:
        rows = await self.sql("SELECT content_hash FROM reports WHERE session_id = :s", s=self.sid)
        return rows[0]["content_hash"] if rows else None

    async def collect_db(self) -> None:
        """API에 없는 측정값: 실행별 사용량, 메시지 seq, 문서 버전 run_id, 리포트 사용량."""
        db = self.b["db"]
        db["agent_runs"] = await self.sql(
            "SELECT run_id::text, stimulus, status, usage FROM agent_runs WHERE session_id = :s "
            "ORDER BY started_at",
            s=self.sid,
        )
        db["message_keys"] = await self.sql(
            "SELECT id::text, run_id::text, seq, event_id::text FROM messages "
            "WHERE session_id = :s",
            s=self.sid,
        )
        db["versions"] = await self.sql(
            "SELECT v.doc_id::text, v.version, v.run_id::text FROM document_versions v "
            "JOIN documents d ON d.id = v.doc_id WHERE d.session_id = :s",
            s=self.sid,
        )
        rows = await self.sql("SELECT usage FROM reports WHERE session_id = :s", s=self.sid)
        db["report_usage"] = rows[0]["usage"] if rows else None
        with contextlib.suppress(Exception):
            rows = await self.sql(
                "SELECT count(*) AS n FROM checkpoints WHERE thread_id = :t", t=f"report:{self.sid}"
            )
            db["report_checkpoints"] = rows[0]["n"] if rows else None


def pick_adjustment(report: dict[str, Any]) -> tuple[dict[str, Any], int | None]:
    """2a: 자동 0인 항목을 1로. 없으면 1→0, 그것도 없으면 기록 없음→1."""
    items = [i for e in report["rubric"]["elements"] for c in e["cards"] for i in c["items"]]
    for auto, value in ((0, 1), (1, 0), (None, 1)):
        for item in items:
            if item["auto"] == auto:
                return item, value
    raise ValueError("report has no rubric items")


# ───────────── CLI ─────────────


def target_from_env() -> Target:
    values = make_session.env()
    return Target(
        public_url=values.get("E2E_PUBLIC_URL", "http://localhost:8000"),
        internal_url=values.get("E2E_INTERNAL_URL", "http://localhost:8001"),
        internal_token=values.get("INTERNAL_TOKEN", ""),
        database_url=values.get("E2E_DATABASE_URL") or values.get("DATABASE_URL"),
    )


async def run_one(name: str, target: Target, out: Path, **kwargs: Any) -> dict[str, Any]:
    script = scripts.load(name)
    bundle = await Runner(script, target, **kwargs).run()
    bundle["results"] = asserts.check(bundle)
    records.write(bundle, out)
    return bundle


async def run_concurrent(target: Target, out: Path) -> list[dict[str, Any]]:
    """단언 7: all_five×3, one_element, no_assistant를 함께."""
    names = ["all_five", "all_five", "all_five", "one_element", "no_assistant"]
    runners = [Runner(scripts.load(name), target, alias=f"e2e-{i}") for i, name in enumerate(names)]
    bundles = await asyncio.gather(*(r.run() for r in runners))
    for bundle in bundles:
        bundle["results"] = asserts.check(bundle)
    records.write_concurrent(bundles, out)
    return bundles


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", default="all_five")
    parser.add_argument("--concurrent", action="store_true")
    parser.add_argument("--auth", action="store_true")
    parser.add_argument("--faults", help="장애 주입 이름 또는 all")
    parser.add_argument(
        "--manage-stack", action="store_true", help="api·mcp·worker를 러너가 띄운다"
    )
    parser.add_argument("--out", default=str(records.RECORDS))
    args = parser.parse_args()
    target = target_from_env()
    out = Path(args.out)

    async def go() -> bool:
        if args.auth:
            from e2e import auth

            return await auth.run(target, out)
        if args.faults:
            from e2e import stack as stacks

            return await stacks.run_faults(args.faults, out)
        if args.manage_stack:
            from e2e import stack as stacks

            return await stacks.run_managed(args.script, out)
        if args.concurrent:
            bundles = await run_concurrent(target, out)
            return all(asserts.passed(b["results"], only=("1", "2")) for b in bundles)
        bundle = await run_one(args.script, target, out)
        return asserts.passed(bundle["results"])

    sys.exit(0 if asyncio.run(go()) else 1)


if __name__ == "__main__":
    main()
