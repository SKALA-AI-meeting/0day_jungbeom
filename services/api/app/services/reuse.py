"""어시스턴트 응답의 반영 추정(docs/api/design.md "제출 처리").

estimate_reuse는 순수 함수다. record_reuse는 SessionService.complete()의 reuse_estimator 훅으로,
종료 실행 뒤 호출×파트별 결과를 assistant_reuse에 남긴다. 결과는 "반영 추정"이며 검증 행동의
증거가 아니다.
"""

import re
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AssistantCall, AssistantReuse, DocumentRevision, Message

MIN_LENGTH = 20  # 정규화 길이와 공통 부분 문자열 모두 이 길이 이상만 센다
VERBATIM = 0.8
EDITED = 0.3

_STRIP = re.compile(r"[\W_]+")


@dataclass(frozen=True)
class Revision:
    part_no: int
    revision: int
    content: str


def normalize(text: str) -> str:
    """공백·구두점을 지우고 소문자로."""
    return _STRIP.sub("", text).lower()


def _ratio(response: str, content: str) -> float:
    # autojunk는 200자 넘는 문자열에서 자주 나오는 글자를 버려 한국어 본문의 일치를 놓친다
    matcher = SequenceMatcher(None, response, content, autojunk=False)
    common = sum(b.size for b in matcher.get_matching_blocks() if b.size >= MIN_LENGTH)
    return round(common / len(response), 4)


def estimate_reuse(
    response: str, revisions: list[Revision]
) -> tuple[str, float, int | None, int | None]:
    """(reuse, ratio, part_no, revision). revisions는 호출 이후 지원자가 저장한 스냅샷들."""
    norm = normalize(response)
    if len(norm) < MIN_LENGTH or not revisions:
        return "none", 0.0, None, None
    ratio, rev = max(
        ((_ratio(norm, normalize(r.content)), r) for r in revisions), key=lambda x: x[0]
    )
    if ratio >= VERBATIM:
        reuse = "verbatim"
    elif ratio >= EDITED:
        reuse = "edited"
    else:
        reuse = "none"
    return reuse, ratio, rev.part_no, rev.revision


async def record_reuse(db: AsyncSession, session_id: uuid.UUID) -> None:
    """호출마다, 그 호출 이후 지원자가 고친 파트별로 최대 ratio를 저장한다(재실행은 덮어씀).

    커밋은 호출자(complete)가 한다.
    """
    calls = (
        await db.execute(
            select(AssistantCall, Message.content)
            .join(Message, Message.id == AssistantCall.response_message_id)
            .where(AssistantCall.session_id == session_id)
        )
    ).all()
    if not calls:
        return
    revisions = (
        (
            await db.execute(
                select(DocumentRevision).where(
                    DocumentRevision.session_id == session_id, DocumentRevision.by == "candidate"
                )
            )
        )
        .scalars()
        .all()
    )
    for call, response in calls:
        later = [r for r in revisions if r.created_at > call.created_at]
        for part_no in sorted({r.part_no for r in later}):
            snapshots = [
                Revision(r.part_no, r.revision, r.content) for r in later if r.part_no == part_no
            ]
            reuse, ratio, _, _ = estimate_reuse(response, snapshots)
            stmt = insert(AssistantReuse).values(
                call_id=call.id, part_no=part_no, reuse=reuse, ratio=ratio
            )
            await db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["call_id", "part_no"],
                    set_={"reuse": reuse, "ratio": ratio},
                )
            )
    await db.flush()
