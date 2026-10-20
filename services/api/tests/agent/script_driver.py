"""e2e 대본(scenarios/e2e/*.yaml)을 테스트 프로세스 안에서 실제 그래프로 돌리는 드라이버.

- 시계: 세션의 모든 시각 열을 과거로 당겨(shift) "세션 시각"을 앞으로 보낸다. 스케줄러 tick은 실제
  now로 돌리므로 카드는 due_at 직후에 fired → 실행된다(카드 시점 ±10초 확인). 테스트 DB는 테스트마다
  세션 하나라 public 스키마의 timestamptz 열을 모두 당긴다(체크포인터 테이블 제외).
- 지원자 행동은 공개 앱 REST(보드·문서·보내기·열기·가져오기·회사 문서·제출·resume·state)와 WS와 같은
  접수 함수(message.send)로 한다. LLM은 FakeLLM(tests/agent/brain.py의 Brain)이다.
- step 키는 scenarios/e2e/README.md. restart·inject·assistant는 이 드라이버가 다루지 않는다.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import yaml
from app import scheduler
from app.auth import session_token
from app.config import REPO_ROOT
from app.models import Session, SessionEvent
from app.services.messages import accept_candidate_message
from sqlalchemy import select, text

E2E = REPO_ROOT / "scenarios" / "e2e"
EPSILON = 0.01  # 시각을 정확히 due_at에 두지 않고 살짝 지나게(분)


def load_script(name: str) -> dict[str, Any]:
    return yaml.safe_load((E2E / f"{name}.yaml").read_text("utf-8"))


async def _time_columns(db) -> list[tuple[str, str]]:
    rows = await db.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'timestamp with time zone' "
            "AND table_name NOT LIKE 'checkpoint%'"
        )
    )
    return [(t, c) for t, c in rows.all()]


class MissingDocument(AssertionError):
    """대본 step이 가리킨 동료 문서가 아직 없다."""


@dataclass
class Driver:
    stack: Any
    session_id: uuid.UUID
    invite_token: str
    minutes: int
    last_at: float = 0.0
    log: list[tuple[float, str]] = field(default_factory=list)
    _columns: list[tuple[str, str]] | None = None

    @property
    def ctx(self):
        return self.stack.ctx

    def client(self) -> httpx.AsyncClient:
        token = session_token(self.session_id, self.minutes)
        return httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{self.stack.servers.public_port}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )

    # ───────────── 시계 ─────────────

    async def now(self) -> float:
        async with self.ctx.session_factory() as db:
            started = await db.scalar(
                select(Session.started_at).where(Session.id == self.session_id)
            )
            delta = await db.scalar(text("SELECT now()"))
        return (delta - started).total_seconds() / 60

    async def shift(self, minutes: float) -> None:
        """세션 시각을 minutes만큼 앞으로(모든 시각 열을 그만큼 과거로)."""
        async with self.ctx.session_factory() as db:
            if self._columns is None:
                self._columns = await _time_columns(db)
            interval = f"{minutes * 60:.3f} seconds"
            for table, column in self._columns:
                await db.execute(
                    text(f'UPDATE "{table}" SET "{column}" = "{column}" - interval \'{interval}\'')
                )
            # 분업 확정 시각은 JSON 안의 ISO 문자열이라 따로 당긴다
            await db.execute(
                text(
                    "UPDATE sessions SET division = jsonb_set(division, '{decided_at}', "
                    f"to_jsonb((division->>'decided_at')::timestamptz - interval '{interval}')) "
                    "WHERE division ? 'decided_at'"
                )
            )
            await db.commit()

    async def _stops(self, now: float, until: float) -> list[float]:
        """now와 until 사이의 예약 시각: pending 카드 due_at, 미공개 공개 시각, 만료·보고 상한."""
        async with self.ctx.session_factory() as db:
            session = await db.get(Session, self.session_id, populate_existing=True)
            started = session.started_at
            times = [
                e.due_at
                for e in (
                    await db.execute(
                        select(SessionEvent).where(
                            SessionEvent.session_id == self.session_id,
                            SessionEvent.status == "pending",
                        )
                    )
                ).scalars()
            ]
            releases = await db.execute(
                text(
                    "SELECT release_at FROM document_releases "
                    "WHERE session_id = :sid AND released_at IS NULL"
                ),
                {"sid": self.session_id},
            )
            times += [r for (r,) in releases.all()]
            times += [t for t in (session.ends_at, session.deadline_at) if t is not None]
        minutes = sorted((t - started).total_seconds() / 60 for t in times)
        return [m for m in minutes if now < m <= until]

    async def settle(self) -> None:
        await scheduler.Scheduler(self.ctx).tick()
        await scheduler.drain()

    async def advance_to(self, target: float) -> None:
        """target(세션 분)까지 예약 시각마다 멈춰 tick한다."""
        while True:
            now = await self.now()
            stops = await self._stops(now, target)
            stop = stops[0] + EPSILON if stops else target
            if stop > now:
                await self.shift(stop - now)
            await self.settle()
            if not stops:
                return

    # ───────────── 대본 ─────────────

    async def card_at(self, card_id: str) -> float:
        async with self.ctx.session_factory() as db:
            session = await db.get(Session, self.session_id, populate_existing=True)
            event = await db.scalar(
                select(SessionEvent)
                .where(SessionEvent.session_id == self.session_id, SessionEvent.card_id == card_id)
                .execution_options(populate_existing=True)
            )
        return (event.due_at - session.started_at).total_seconds() / 60

    async def resolve(self, at: Any) -> float:
        if isinstance(at, str) and at.startswith("+"):
            return self.last_at + float(at[1:])
        if isinstance(at, int | float):
            return float(at)
        return await self.card_at(at) + EPSILON

    async def run(self, steps: list[dict[str, Any]], *, tolerant: bool = False) -> None:
        """tolerant면(live) 실패한 step(동료 문서 없음·API 거절)을 log에 남기고 다음으로 간다."""
        for index, step in enumerate(steps):
            at = await self.resolve(step["at"])
            self.last_at = at
            await self.advance_to(at)
            try:
                await self.do(step, index)
            except AssertionError as exc:
                if not tolerant:
                    raise
                self.log.append((at, f"skipped:{exc}"))
        await self.settle()  # 마지막 행동(보고 메시지 등)이 남긴 종료를 스케줄러가 처리

    async def do(self, step: dict[str, Any], index: int) -> None:
        async with self.client() as http:
            for task in step.get("board") or []:
                body = {k: v for k, v in task.items() if k != "part_no"}
                r = await http.put(
                    f"/sessions/{self.session_id}/tasks/{task['part_no']}", json=body
                )
                assert r.status_code == 200, r.text
            await scheduler.drain()
            if "say" in step:
                await self.say(step["say"], f"s-{index}", http)
            if "write" in step:
                write = step["write"]
                part = write["part_no"]
                body = (
                    {"sections": write["content"]}
                    if part == "final"
                    else {"content": write["content"]}
                )
                r = await http.put(f"/sessions/{self.session_id}/my-documents/{part}", json=body)
                assert r.status_code == 200, r.text
            if "share" in step:
                share = step["share"]
                r = await http.post(
                    f"/sessions/{self.session_id}/my-documents/{share['part_no']}/share",
                    json={"channel": share["channel"]},
                )
                assert r.status_code == 200, r.text
            if "open" in step:
                doc_id = await self.received_doc(http, step["open"]["part_no"])
                r = await http.post(
                    f"/sessions/{self.session_id}/documents/{doc_id}/open",
                    json={"version": step["open"]["version"]},
                )
                assert r.status_code == 200, r.text
            for item in step.get("import") or []:
                if item["from"] == "colleague":
                    source = await self.received_doc(http, item["part_no"])
                else:
                    source = await self.my_doc(http, item["part_no"])
                r = await http.put(
                    f"/sessions/{self.session_id}/final/sections/{item['part_no']}/import",
                    json={"source_doc_id": source, "version": item["version"]},
                )
                assert r.status_code == 200, r.text
            if "view" in step:
                r = await http.get(f"/sessions/{self.session_id}/documents/{step['view']}")
                assert r.status_code == 200, r.text
            if step.get("submit"):
                r = await http.post(f"/sessions/{self.session_id}/submit")
                assert r.status_code == 200, r.text
                self.log.append((self.last_at, f"submit:{r.json()['status']}"))
            if "disconnect" in step:
                # WS를 실제로 끊지 않고 재입장 경로만 확인한다(resume → 새 JWT → state)
                r = await http.post(f"/s/{self.invite_token}/resume")
                assert r.status_code == 200, r.text
                state = await http.get(
                    f"/sessions/{self.session_id}/state",
                    headers={"Authorization": f"Bearer {r.json()['session_token']}"},
                )
                assert state.status_code == 200, state.text
                self.log.append((self.last_at, f"resume:{state.json()['session']['status']}"))
        await scheduler.drain()

    async def say(self, say: dict[str, Any], client_id: str, http: httpx.AsyncClient) -> None:
        reply = None
        if say.get("reply_to_doc"):
            ref = say["reply_to_doc"]
            reply = {
                "doc_id": await self.received_doc(http, ref["part_no"]),
                "version": ref["version"],
            }
        async with self.ctx.session_factory() as db:
            message, run_id, _ = await accept_candidate_message(
                db, self.ctx.hub, self.session_id, client_id, say["channel"], say["content"], reply
            )
            message_id = message.id
        scheduler.spawn(
            run_id, lambda: scheduler.run_message(self.ctx, self.session_id, message_id, run_id)
        )
        await scheduler.drain()

    async def received_doc(self, http: httpx.AsyncClient, part_no: int) -> str:
        """받은 동료 문서 id. 없으면(실제 모델에서 동료가 못 보냈을 때) 실패한다."""
        r = await http.get(f"/sessions/{self.session_id}/my-documents")
        found = [d["doc_id"] for d in r.json()["received"] if d["part_no"] == part_no]
        if not found:
            raise MissingDocument(f"colleague part {part_no} not received at {self.last_at}")
        return found[0]

    async def my_doc(self, http: httpx.AsyncClient, part_no: int) -> str:
        r = await http.get(f"/sessions/{self.session_id}/my-documents")
        return next(d["doc_id"] for d in r.json()["documents"] if d["part_no"] == part_no)


async def start(stack, service, make_position, elements, minutes) -> Driver:
    position = await make_position(list(elements), minutes)
    session, _, token = await service.create_for_invite(position.id, "지원자A", "a@example.com")
    await service.consent(session.id)
    await service.start(session.id)
    driver = Driver(stack, session.id, token, minutes)
    await driver.settle()  # 킥오프(0분)
    return driver
