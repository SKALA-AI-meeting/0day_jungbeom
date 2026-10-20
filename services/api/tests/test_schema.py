"""완료 기준: infra/db/schema.sql이 docs/common/data-model.md의 테이블·핵심 컬럼을 갖고 임시 DB에
적용된다."""

from sqlalchemy import text

TABLES = {
    "companies",
    "admins",
    "positions",
    "invites",
    "sessions",
    "session_events",
    "messages",
    "agent_runs",
    "documents",
    "document_revisions",
    "document_versions",
    "document_shares",
    "document_opens",
    "final_document",
    "doc_views",
    "tasks",
    "task_events",
    "document_releases",
    "observations",
    "connection_gaps",
    "assistant_calls",
    "assistant_reuse",
    "debrief_surveys",
    "reports",
    "rubric_adjustments",
    "report_notes",
    "doc_chunks",
}

COLUMNS = {
    "positions": {"mission_id"},
    "sessions": {"deadline_at", "reported_at", "completed_at"},
    "session_events": {"or_on_submit", "document_missing"},
    "tasks": {"assignee", "order", "due_min", "depends_on"},
    "observations": {"card_id", "aux", "facts", "updated_run_id"},
}


async def test_schema_has_data_model_tables(db):
    rows = await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    # LangGraph checkpointer 테이블(checkpoint*)은 라이브러리가 같은 DB에 만들 수 있어 뺀다
    assert {t for t in rows.scalars() if not t.startswith("checkpoint")} == TABLES

    for table, columns in COLUMNS.items():
        rows = await db.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
            {"t": table},
        )
        assert columns <= set(rows.scalars()), table

    # 관찰 키는 카드 단위, 보드 assignee는 시작 시 null
    unique = await db.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE tablename = 'observations' AND indexdef LIKE '%UNIQUE%'"
        )
    )
    assert any("(session_id, card_id, window_start)" in d for d in unique.scalars())
    nullable = await db.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'tasks' AND column_name = 'assignee'"
        )
    )
    assert nullable.scalar() == "YES"
    # data-model: due_min은 세션 분 정수
    due_type = await db.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'tasks' AND column_name = 'due_min'"
        )
    )
    assert due_type.scalar() == "integer"
