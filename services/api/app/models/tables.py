"""테이블 모델. infra/db/schema.sql과 1:1이며 DDL은 그 파일이 정본이다.

여기서 create_all 하지 않는다.

LangGraph checkpointer 테이블과 rag-mcp 전용 doc_chunks는 매핑하지 않는다.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import REAL, Boolean, ForeignKey, Integer, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TZ = TIMESTAMP(timezone=True)
NOW = text("now()")
GEN_UUID = text("gen_random_uuid()")


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=GEN_UUID)


def _session_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)


def _doc_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[uuid.UUID] = _pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    mission_id: Mapped[str] = mapped_column(Text, server_default=text("'planning'"))
    elements: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    session_minutes: Mapped[int] = mapped_column(Integer, server_default=text("120"))
    catalog_version: Mapped[str] = mapped_column(Text, nullable=False)
    scenario: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[uuid.UUID] = _pk()
    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("positions.id"), nullable=False
    )
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(TZ)
    cancelled_at: Mapped[datetime | None] = mapped_column(TZ)
    previous_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = _pk()
    invite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invites.id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'invited'"))
    consented_at: Mapped[datetime | None] = mapped_column(TZ)
    started_at: Mapped[datetime | None] = mapped_column(TZ)
    ends_at: Mapped[datetime | None] = mapped_column(TZ)
    division: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    submitted_at: Mapped[datetime | None] = mapped_column(TZ)
    deadline_at: Mapped[datetime | None] = mapped_column(TZ)
    reported_at: Mapped[datetime | None] = mapped_column(TZ)
    completed_at: Mapped[datetime | None] = mapped_column(TZ)
    llm_failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    report_enqueued_at: Mapped[datetime | None] = mapped_column(TZ)
    approve_enqueued_at: Mapped[datetime | None] = mapped_column(TZ)
    failed_stage: Mapped[str | None] = mapped_column(Text)
    failed_reason: Mapped[str | None] = mapped_column(Text)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class SessionEvent(Base):
    __tablename__ = "session_events"
    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _session_fk()
    card_id: Mapped[str] = mapped_column(Text, nullable=False)
    element: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    fired_at: Mapped[datetime | None] = mapped_column(TZ)
    done_at: Mapped[datetime | None] = mapped_column(TZ)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    texture: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    or_on_submit: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    document_missing: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _session_fk()
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("session_events.id")
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    seq: Mapped[int | None] = mapped_column(Integer)
    client_msg_id: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = _session_fk()
    stimulus: Mapped[str] = mapped_column(Text, nullable=False)
    ref_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'started'"))
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    started_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    finished_at: Mapped[datetime | None] = mapped_column(TZ)


class Document(Base):
    """파트 문서 또는 최종본(part_no null, final). 주인 한 명."""

    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _session_fk()
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    part_no: Mapped[int | None] = mapped_column(Integer)
    final: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, server_default=text("''"))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class DocumentRevision(Base):
    __tablename__ = "document_revisions"
    id: Mapped[uuid.UUID] = _pk()
    doc_id: Mapped[uuid.UUID] = _doc_fk()
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    by: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    length: Mapped[int] = mapped_column(Integer, nullable=False)
    diff_ratio: Mapped[float | None] = mapped_column(REAL)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id: Mapped[uuid.UUID] = _pk()
    doc_id: Mapped[uuid.UUID] = _doc_fk()
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class DocumentShare(Base):
    __tablename__ = "document_shares"
    id: Mapped[uuid.UUID] = _pk()
    doc_id: Mapped[uuid.UUID] = _doc_fk()
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class DocumentOpen(Base):
    __tablename__ = "document_opens"
    id: Mapped[uuid.UUID] = _pk()
    doc_id: Mapped[uuid.UUID] = _doc_fk()
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    by: Mapped[str] = mapped_column(Text, server_default=text("'candidate'"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class FinalDocument(Base):
    """최종본 섹션별 내용과 출처. 저장 이력은 최종본 documents 행의 revisions에 남긴다."""

    __tablename__ = "final_document"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), primary_key=True
    )
    sections: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class DocView(Base):
    __tablename__ = "doc_views"
    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _session_fk()
    doc_id: Mapped[str] = mapped_column(Text, nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class Task(Base):
    __tablename__ = "tasks"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), primary_key=True
    )
    part_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignee: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'todo'"))
    order: Mapped[int] = mapped_column("order", Integer, nullable=False)
    due_min: Mapped[int | None] = mapped_column(Integer)
    depends_on: Mapped[list[int]] = mapped_column(ARRAY(Integer), server_default=text("'{}'"))


class TaskEvent(Base):
    __tablename__ = "task_events"
    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _session_fk()
    part_no: Mapped[int] = mapped_column(Integer, nullable=False)
    by: Mapped[str] = mapped_column(Text, nullable=False)
    field: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class DocumentRelease(Base):
    __tablename__ = "document_releases"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), primary_key=True
    )
    doc_id: Mapped[str] = mapped_column(Text, primary_key=True)
    release_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(TZ)


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _session_fk()
    card_id: Mapped[str] = mapped_column(Text, nullable=False)
    element: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[datetime] = mapped_column(TZ, nullable=False)
    window_end: Mapped[datetime] = mapped_column(TZ, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    label: Mapped[str | None] = mapped_column(Text)
    aux: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    facts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class ConnectionGap(Base):
    __tablename__ = "connection_gaps"
    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _session_fk()
    disconnected_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    reconnected_at: Mapped[datetime | None] = mapped_column(TZ)


class AssistantCall(Base):
    __tablename__ = "assistant_calls"
    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _session_fk()
    request_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False
    )
    response_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id")
    )
    cited_doc_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class AssistantReuse(Base):
    __tablename__ = "assistant_reuse"
    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assistant_calls.id"), primary_key=True
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True
    )
    part_no: Mapped[int | None] = mapped_column(Integer)
    ratio: Mapped[float] = mapped_column(REAL, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class DebriefSurvey(Base):
    __tablename__ = "debrief_surveys"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), primary_key=True
    )
    answers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class Report(Base):
    __tablename__ = "reports"
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), primary_key=True
    )
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
    reviewed_at: Mapped[datetime | None] = mapped_column(TZ)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    auto_met: Mapped[int | None] = mapped_column(Integer)
    auto_unmet: Mapped[int | None] = mapped_column(Integer)
    auto_no_record: Mapped[int | None] = mapped_column(Integer)
    reviewer_met: Mapped[int | None] = mapped_column(Integer)
    reviewer_unmet: Mapped[int | None] = mapped_column(Integer)
    reviewer_no_record: Mapped[int | None] = mapped_column(Integer)
    review_memo: Mapped[str | None] = mapped_column(Text)
    reviewer_name: Mapped[str | None] = mapped_column(Text)


class RubricAdjustment(Base):
    __tablename__ = "rubric_adjustments"
    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _session_fk()
    element: Mapped[str] = mapped_column(Text, nullable=False)
    card_id: Mapped[str] = mapped_column(Text, nullable=False)
    item_id: Mapped[str] = mapped_column(Text, nullable=False)
    auto_value: Mapped[int | None] = mapped_column(SmallInteger)
    reviewer_value: Mapped[int | None] = mapped_column(SmallInteger)
    memo: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_name: Mapped[str] = mapped_column(Text, nullable=False)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admins.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)


class ReportNote(Base):
    __tablename__ = "report_notes"
    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = _session_fk()
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_name: Mapped[str] = mapped_column(Text, nullable=False)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admins.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TZ, server_default=NOW)
