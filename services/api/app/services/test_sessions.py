"""테스트 API(ENABLE_TEST_API=1): 단계 시드 재생과 시간 당기기. 운영에서는 라우터가 404를 낸다.

단계 시드 `scenarios/e2e/stages/<이름>.yaml`(stage-kit 소유)을 SessionService·debate·proposal 함수로
재생한다. SQL을 직접 넣지 않으므로 generation·안·입장·칸·누적 마감이 실제 흐름과 같은 규칙으로
쌓인다.
LLM·그래프는 부르지 않는다: 지원자 발언의 의도는 시드에 적힌 값(없으면 폴백)으로 같은 반영 함수를
타고,
AI 발언은 시드의 고정 문장을 내부 쓰기 함수로 넣는다. 재생 중 쌓인 자극 run은 skipped로 닫고, 마지막
단계의 phase_started만 메일박스에 넣어 이후는 실제 시계·스케줄러·그래프가 평소대로 진행한다.

시드 문법(e2e 대본과 같은 `at`: 절대 분 또는 `+분`, 세션 시작 기준·실제 세션 길이의 분):

    steps:
      - at: 0.3
        say: "물이 좋겠어요"                       # 지원자 room 메시지
        intent: {intent: propose, scenario_option_key: water, confidence: high}   # 선택
      - at: +0.1
        ai: {seat: p3, content: "...", propose: water}      # propose(키 또는 라벨)·support·oppose
      - at: 1.0
        confirm: {phase: keyword, option_key: water}        # problem·solution은 value(+option_key)
      - proposal: {idea_credit: "..."}                      # 기획안 칸 일부 덮어쓰기
      - submit: true

시간 당기기(advance)는 sessions의 started_at·phase_started_at·phase_deadline_at·ends_at을 같은
초만큼
앞당긴다. 메시지 created_at은 그대로 두며, 처리는 다음 스케줄러 틱이 평소 경로로 한다.
"""

import math
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select, update

from app.agent import intent as intent_module
from app.agent.runner import Stimulus
from app.auth import debrief_token, hash_password, session_token
from app.models import Admin, AgentRun, Company, Message, Option, Proposal, Session
from app.services import admin as admin_service
from app.services import debate, views
from app.services import proposal as proposal_service
from app.services import scenario as sc
from app.services import session as session_service
from app.services.clock import FakeClock, MonotonicClock
from app.services.common import Effects, invalid, iso, load_context, serialize_message

START_AT = ("entry", "keyword", "problem", "solution", "proposal", "ended")
SEED_PASSWORD = "e2e-password"


def stage_path(scenarios_dir: Path, name: str) -> Path:
    return Path(scenarios_dir) / "e2e" / "stages" / f"{name}.yaml"


def load_stage(scenarios_dir: Path, name: str) -> list[dict[str, Any]]:
    path = stage_path(scenarios_dir, name)
    if not path.is_file():
        raise invalid("invalid_input", f"stage seed not found: {name}")
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("steps") or []


def step_times(steps: list[dict[str, Any]]) -> list[float]:
    """step마다 세션 시작 기준 분. `at` 생략은 직전 step과 같은 시각."""
    times, current = [], 0.0
    for step in steps:
        at = step.get("at")
        if isinstance(at, str) and at.startswith("+"):
            current += float(at[1:])
        elif at is not None:
            try:
                current = float(at)
            except ValueError as exc:
                raise invalid("invalid_input", f"seed step at must be minutes: {at}") from exc
        times.append(current)
    return times


async def create(ctx, body: dict[str, Any]) -> dict[str, Any]:
    """POST /internal/test/sessions. 관리자·채용 건·초대를 만들고 start_at까지 시드를 재생한다."""
    start_at = body.get("start_at") or "entry"
    if start_at not in START_AT:
        raise invalid("invalid_input", f"unknown start_at: {start_at}")
    steps = (
        []
        if start_at == "entry"
        else load_stage(ctx.settings.scenarios_dir, body.get("stage") or start_at)
    )
    session_id, raw, minutes = await _invite(ctx, body)
    result: dict[str, Any] = {
        "session_id": str(session_id),
        "token": raw,
        "invite_url": session_service.invite_url(ctx.settings.web_base_url, raw),
        "phase": None,
    }
    if start_at == "entry":
        return result
    session = await _replay(ctx, session_id, steps)
    if start_at == "ended":
        if session.status != "completed":
            raise invalid("invalid_input", "seed did not submit the proposal")
        result["phase"] = "completed"
        result["debrief_token"] = debrief_token(session.id, views.debrief_until(session))
        result["admin_report_url"] = (
            f"{ctx.settings.web_base_url.rstrip('/')}/admin/sessions/{session.id}/report"
        )
        return result
    if session.status != "in_progress" or session.phase != start_at:
        raise invalid("invalid_input", f"seed ended in {session.phase}, expected {start_at}")
    result["phase"] = session.phase
    result["session_token"] = session_token(session.id, minutes)
    return result


async def _invite(ctx, body: dict[str, Any]) -> tuple[uuid.UUID, str, int]:
    now = ctx.clock.now()
    async with ctx.session_factory() as db:
        email = body.get("admin_email") or "e2e@example.com"
        admin = await db.scalar(select(Admin).where(Admin.email == email))
        if admin is None:
            company = Company(name="e2e 회사")
            db.add(company)
            await db.flush()
            admin = Admin(
                company_id=company.id, email=email, password_hash=hash_password(SEED_PASSWORD)
            )
            db.add(admin)
            await db.flush()
        position = await admin_service.create_position(
            db,
            body.get("company_id") or admin.company_id,
            name="e2e",
            session_minutes=body.get("session_minutes") or 15,
            mission_id=sc.DEFAULT_MISSION,
            scenarios_dir=ctx.settings.scenarios_dir,
            now=now,
        )
        alias = body.get("alias") or f"지원자-{uuid.uuid4().hex[:6]}"
        session, _invite, raw = await admin_service.invite(
            db, position, alias=alias, email="e2e@example.com", previous_session_id=None, now=now
        )
        await db.commit()
        return session.id, raw, position.session_minutes


async def _replay(ctx, session_id: uuid.UUID, steps: list[dict[str, Any]]) -> Session:
    """가짜 시계를 '지금 − 시드 경과 시간'에서 시작해 재생하므로 끝나면 시계가 지금과 맞는다."""
    times = step_times(steps)
    elapsed = max(times, default=0.0)
    fake = FakeClock(ctx.clock.now() - timedelta(minutes=elapsed))
    clock = MonotonicClock(fake)
    start = fake.now()
    await _run(ctx, session_id, clock, _start)
    for index, (step, at) in enumerate(zip(steps, times, strict=True)):
        fake.set(max(fake.now(), start + timedelta(minutes=at)))
        await _run(ctx, session_id, clock, _step, index, step)
    return await _settle(ctx, session_id)


async def _run(ctx, session_id: uuid.UUID, clock, fn, *args) -> None:
    """한 동작 = 한 트랜잭션. WS 프레임·큐 발행은 평소대로 보내고 자극은 넣지 않는다(뒤에서
    skipped)."""
    fx = Effects()
    async with ctx.session_factory() as db:
        session, position, invite = await load_context(db, session_id, lock=True)
        await fn(db, session, position, invite, clock, fx, *args)
        await db.commit()
    fx.stimuli.clear()
    await ctx.apply(session_id, fx)


async def _start(db, session, position, invite, clock, fx) -> None:
    session_service.consent(session, invite.alias, clock.now())
    await session_service.start(db, session, position, clock, fx)
    invite.used_at = clock.now()


async def _step(db, session, position, invite, clock, fx, index: int, step: dict) -> None:
    if "say" in step:
        await _say(db, session, position, clock, fx, index, step)
    if "ai" in step:
        await _ai(db, session, clock, fx, index, step["ai"])
    if "confirm" in step:
        c = step["confirm"]
        phase = c.get("phase", session.phase)
        await debate.confirm_slot(
            db, session, position, phase, c.get("value"), c.get("option_key"), clock, fx
        )
    if "proposal" in step:
        proposal = await db.get(Proposal, session.id)
        sections = {**proposal.sections, **step["proposal"]}
        await proposal_service.put(
            db, session, sections, proposal.revision, position.scenario["proposal_template"], clock
        )
    if step.get("submit"):
        await proposal_service.submit(
            db, session, position.scenario["proposal_template"], clock, fx
        )


async def _say(db, session, position, clock, fx, index: int, step: dict) -> None:
    say = step["say"]
    content = say if isinstance(say, str) else say["content"]
    fixed = step.get("intent") or (say.get("intent") if isinstance(say, dict) else None)
    message, _run_id, _stimulus = await debate.save_candidate_message(
        db, session, f"seed-{index}", content, clock
    )
    fx.emit("message.new", serialize_message(session, message))

    async def classify(_message: str, **_kwargs: Any):
        if not fixed:
            return intent_module.fallback(), True
        return {**intent_module.fallback(), **fixed}, False

    await debate.classify_and_apply(db, session, position, message, classify, clock)


async def _ai(db, session, clock, fx, index: int, ai: dict) -> None:
    run_id = uuid.uuid5(session.id, f"seed:{index}")
    message = await debate.post_internal_message(
        db,
        session,
        {
            "sender": ai["seat"],
            "content": ai["content"],
            "run_id": run_id,
            "seq": 1,
            "is_invite": bool(ai.get("is_invite")),
            "card_ids": ai.get("card_ids") or [],
            "meta": {"kind": "seed"},
        },
        clock,
        fx,
    )
    for key, stance in (("propose", "support"), ("support", "support"), ("oppose", "oppose")):
        if key not in ai:
            continue
        option = await _seed_option(db, session, ai[key], ai["seat"], message, clock, key)
        await debate.internal_stance(
            db,
            session,
            {
                "participant": ai["seat"],
                "option_id": option.id,
                "stance": stance,
                "source_message_id": message.id,
                "run_id": run_id,
            },
            clock,
        )


async def _seed_option(db, session, ref: str, seat: str, message: Message, clock, key: str):
    """시드의 안 참조(시나리오 키 또는 라벨). propose면 없을 때 만들고, support·oppose는 기존
    행만."""
    found = await db.scalar(
        select(Option).where(
            Option.session_id == session.id,
            Option.phase == session.phase,
            (Option.scenario_option_key == ref) | (Option.label == ref),
        )
    )
    if found is not None or key != "propose":
        if found is None:
            raise invalid("invalid_input", f"seed option not found: {ref}")
        return found
    _, position, _ = await load_context(db, session.id)
    kw = await debate.keyword_key(db, session.id)
    catalog = {
        c["scenario_option_key"]: c["label"]
        for c in sc.catalog_options(position.scenario, session.phase, kw)
    }
    option, _ = await debate.get_or_create_option(
        db,
        session.id,
        session.phase,
        label=catalog.get(ref, ref),
        proposer=seat,
        now=clock.now(),
        key=ref if ref in catalog else None,
        source_message_id=message.id,
    )
    return option


async def _settle(ctx, session_id: uuid.UUID) -> Session:
    """재생 중 쌓인 run을 skipped로 닫고, 진행 중이면 현재 단계 phase_started만 메일박스에
    넣는다."""
    async with ctx.session_factory() as db:
        session = await db.get(Session, session_id)
        keep = session.status == "in_progress" and session.phase in sc.PHASES
        current = uuid.uuid5(session_id, "phase:" + session.phase) if keep else None
        closing = update(AgentRun).where(
            AgentRun.session_id == session_id, AgentRun.status == "queued"
        )
        if current is not None:
            closing = closing.where(AgentRun.run_id != current)
        await db.execute(
            closing.values(
                status="skipped", finished_at=ctx.clock.now(), decision={"reason": "seed"}
            )
        )
        run = await db.get(AgentRun, current) if current else None
        await db.commit()
        ctx.generations[session_id] = session.generation
    if run is not None and run.status == "queued":
        stimulus = Stimulus("phase_started", session.phase, run.generation or session.generation)
        ctx.mailboxes.put(session_id, stimulus, run.run_id)
    return session


async def advance(ctx, session_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """POST /internal/test/sessions/{id}/advance {seconds | to}."""
    seconds, to = body.get("seconds"), body.get("to")
    if (seconds is None) == (to is None):
        raise invalid("invalid_input", "give exactly one of seconds or to")
    async with ctx.session_factory() as db:
        session, position, _ = await load_context(db, session_id, lock=True)
        if session.status != "in_progress":
            raise invalid("invalid_input", "session is not in progress")
        now = ctx.clock.now()
        if to is not None:
            target = await _target(db, session, position.scenario, str(to))
            seconds = max(math.ceil((target - now).total_seconds()), 0)
        if int(seconds) < 0:
            raise invalid("invalid_input", "seconds must be >= 0")
        delta = timedelta(seconds=int(seconds))
        for column in ("started_at", "phase_started_at", "phase_deadline_at", "ends_at"):
            setattr(session, column, getattr(session, column) - delta)
        await db.commit()
        return {
            "shifted_seconds": int(seconds),
            "phase": session.phase,
            "phase_deadline_at": iso(session.phase_deadline_at),
            "ends_at": iso(session.ends_at),
        }


async def _target(db, session: Session, scenario: dict, to: str) -> datetime:
    """시간을 당겨 닿을 시각(지금 기준). deadline·idle·card:<id>."""
    if to == "deadline":
        return session.phase_deadline_at
    if to == "idle":
        if session.phase not in sc.DEBATE_PHASES:
            raise invalid("invalid_input", "idle only in debate phases")
        rule = scenario["silence_invite"]
        spoke = await db.scalar(
            select(func.count()).where(
                Message.session_id == session.id,
                Message.sender == "candidate",
                Message.channel == "room",
                Message.phase == session.phase,
            )
        )
        # 메시지 시각은 당기지 않으므로 지원자가 이미 말했으면 '단계 절반 무의견' 조건으로 닿는다
        if not spoke:
            minutes = rule["idle_min"]
        else:
            budget = sc.stage(scenario, session.phase)["budget_min"]
            minutes = budget * rule["no_opinion_after_budget_ratio"]
        return session.phase_started_at + timedelta(minutes=minutes)
    if to.startswith("card:"):
        card_id = to.removeprefix("card:")
        card = next((c for c in scenario["cards"] if c["card_id"] == card_id), None)
        if card is None or card["stage_id"] != session.phase or card.get("offset_min") is None:
            raise invalid("invalid_input", f"card not schedulable in this phase: {card_id}")
        return session.phase_started_at + timedelta(minutes=card["offset_min"])
    raise invalid("invalid_input", f"unknown advance target: {to}")
