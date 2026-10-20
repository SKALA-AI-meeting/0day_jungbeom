-- Day Zero 스키마. 정본은 docs/common/data-model.md. LangGraph checkpointer 테이블은 라이브러리가 만든다.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE companies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admins (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES companies(id),
  email text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE positions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL REFERENCES companies(id),
  name text NOT NULL,
  elements text[] NOT NULL,
  session_minutes int NOT NULL DEFAULT 120,
  catalog_version text NOT NULL,
  scenario jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (cardinality(elements) BETWEEN 1 AND 4)
);

CREATE TABLE invites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  position_id uuid NOT NULL REFERENCES positions(id),
  alias text NOT NULL,
  email text NOT NULL,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invite_id uuid NOT NULL UNIQUE REFERENCES invites(id),
  status text NOT NULL DEFAULT 'invited'
    CHECK (status IN ('invited','in_progress','completed','report_ready','approving','reviewed','failed')),
  consented_at timestamptz,
  started_at timestamptz,
  ends_at timestamptz,
  division jsonb,
  submitted_at timestamptz,
  llm_failures int NOT NULL DEFAULT 0,
  report_enqueued_at timestamptz,
  approve_enqueued_at timestamptz,          -- report.approve 발행 기록(outbox)
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE session_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  card_id text NOT NULL,
  element text,
  due_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','fired','done','failed')),
  fired_at timestamptz,
  done_at timestamptz,
  attempts int NOT NULL DEFAULT 0,
  run_id uuid,                              -- fired 시 생성, 재실행에서 재사용
  UNIQUE (session_id, card_id)
);
CREATE INDEX ON session_events (due_at) WHERE status = 'pending';
CREATE INDEX ON session_events (session_id) WHERE status = 'fired';

CREATE TABLE messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  channel text NOT NULL CHECK (channel IN ('team','dm','assistant')),
  sender text NOT NULL CHECK (sender IN ('manager','colleague','candidate','assistant','system')),
  content text NOT NULL,
  event_id uuid REFERENCES session_events(id),
  run_id uuid,
  seq int,
  meta jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, run_id, seq)
);
CREATE INDEX ON messages (session_id, created_at);

CREATE TABLE document_states (
  session_id uuid NOT NULL REFERENCES sessions(id),
  part_no int NOT NULL CHECK (part_no BETWEEN 1 AND 5),
  content text NOT NULL DEFAULT '',
  revision int NOT NULL DEFAULT 0,
  updated_by text CHECK (updated_by IN ('candidate','colleague')),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (session_id, part_no)
);

CREATE TABLE document_revisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  part_no int NOT NULL,
  revision int NOT NULL,
  by text NOT NULL CHECK (by IN ('candidate','colleague')),
  content text NOT NULL,                    -- 본문 스냅샷
  length int NOT NULL,
  diff_ratio real,
  run_id uuid,                              -- 동료 수정만. 같은 (part_no, run_id)는 기존 행 반환
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, part_no, revision)
);
CREATE UNIQUE INDEX ON document_revisions (session_id, part_no, run_id) WHERE run_id IS NOT NULL;

CREATE TABLE doc_views (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  doc_id text NOT NULL,
  viewed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tasks (
  session_id uuid NOT NULL REFERENCES sessions(id),
  part_no int NOT NULL CHECK (part_no BETWEEN 1 AND 5),
  assignee text NOT NULL CHECK (assignee IN ('candidate','colleague','both')),
  status text NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','doing','done')),
  PRIMARY KEY (session_id, part_no)
);

CREATE TABLE document_releases (
  session_id uuid NOT NULL REFERENCES sessions(id),
  doc_id text NOT NULL,
  release_at timestamptz NOT NULL,
  released_at timestamptz,
  PRIMARY KEY (session_id, doc_id)
);

CREATE TABLE observations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  element text NOT NULL,
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  label text,
  evidence_message_ids uuid[] NOT NULL DEFAULT '{}',
  run_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, element, window_start)
);

CREATE TABLE assistant_calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  request_message_id uuid NOT NULL REFERENCES messages(id),
  response_message_id uuid REFERENCES messages(id),
  cited_doc_ids text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE assistant_reuse (
  call_id uuid NOT NULL REFERENCES assistant_calls(id),
  part_no int NOT NULL,
  reuse text NOT NULL CHECK (reuse IN ('none','verbatim','edited')),
  ratio real NOT NULL,
  computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (call_id, part_no)
);

CREATE TABLE reports (
  session_id uuid PRIMARY KEY REFERENCES sessions(id),
  stage text NOT NULL CHECK (stage IN ('draft','final')),
  content jsonb NOT NULL,
  generated_at timestamptz NOT NULL DEFAULT now(),
  reviewed_at timestamptz,
  attempts int NOT NULL DEFAULT 0
);

CREATE TABLE doc_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id text NOT NULL,
  chunk_no int NOT NULL,
  content text NOT NULL,
  embedding vector(1024) NOT NULL,
  model text NOT NULL DEFAULT 'BAAI/bge-m3',
  catalog_version text NOT NULL,
  UNIQUE (catalog_version, doc_id, chunk_no)
);
