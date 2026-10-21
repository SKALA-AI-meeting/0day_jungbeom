"""세션 LLM 비용 누적과 하드 상한(R5-11). 판단은 이 모듈 한 곳만 한다.

- debate_cost_usd: 세션 중 토론 LLM 비용(의도 분류·턴·페르소나·어시스턴트). 하드 상한 판단용.
- cost_usd: 토론 + 리포트 평가 전체(관측). 리포트 비용은 여기에만 더해 상한에 들지 않는다.
cost_left = SESSION_COST_HARD_USD(기본 $2) − debate_cost_usd. 0 이하면 페르소나는 고정 안전 문구만
쓴다.
"""

import os
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session


def hard_limit() -> Decimal:
    return Decimal(os.environ.get("SESSION_COST_HARD_USD", "2"))


def cost_left(session: Session) -> float:
    return float(hard_limit() - Decimal(session.debate_cost_usd or 0))


def usage_cost(usage: dict[str, Any] | None) -> Decimal:
    return Decimal(str((usage or {}).get("cost_usd") or 0))


async def add_debate_cost(db: AsyncSession, session_id: uuid.UUID, usage: dict | None) -> None:
    cost = usage_cost(usage)
    if cost:
        await db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(
                debate_cost_usd=Session.debate_cost_usd + cost, cost_usd=Session.cost_usd + cost
            )
        )


async def add_report_cost(db: AsyncSession, session_id: uuid.UUID, usage: dict | None) -> None:
    cost = usage_cost(usage)
    if cost:
        await db.execute(
            update(Session).where(Session.id == session_id).values(cost_usd=Session.cost_usd + cost)
        )
