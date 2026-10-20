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
  mission_id text NOT NULL DEFAULT 'planning',   -- scenarios/missions/<id>/
  elements text[] NOT NULL,
  session_minutes int NOT NULL DEFAULT 120,
  catalog_version text NOT NULL,                 -- 미션 폴더 전체 해시(scenarios/version.py)
  scenario jsonb NOT NULL,                       -- 카드·문서·프롬프트 본문 복사본. 수정·삭제 없음
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (cardinality(elements) BETWEEN 1 AND 5)
);

CREATE TABLE invites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  position_id uuid NOT NULL REFERENCES positions(id),
  alias text NOT NULL,
  email text NOT NULL,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  cancelled_at timestamptz,
  previous_session_id uuid,                 -- failed(session)·만료·cancelled 세션만
  created_at timestamptz NOT NULL DEFAULT now()
);
-- 같은 채용 건 안 별칭 중복은 api가 409로 막는다. 재응시·재발행은 이전 응시와 같은 별칭을 쓰므로
-- DB unique로 두지 않는다(contracts.md 지원자 목록 예시의 retry 행).
CREATE INDEX ON invites (position_id, alias);

CREATE TABLE sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invite_id uuid NOT NULL UNIQUE REFERENCES invites(id),
  status text NOT NULL DEFAULT 'invited'
    CHECK (status IN ('invited','cancelled','in_progress','reporting','completed','report_ready','approving','reviewed','failed')),
  consented_at timestamptz,
  started_at timestamptz,
  ends_at timestamptz,
  division jsonb,                           -- {parts, decided_by: candidate|colleague_default, decided_at}
  submitted_at timestamptz,
  deadline_at timestamptz,                  -- submitted_at + 5분(보고 대기 상한)
  reported_at timestamptz,                  -- kind=report 지원자 메시지 저장 시각
  completed_at timestamptz,                 -- 보고 종료. 마지막 관찰 창의 끝, 디브리핑 기한·삭제 예정일 기준
  llm_failures int NOT NULL DEFAULT 0,
  report_enqueued_at timestamptz,
  approve_enqueued_at timestamptz,          -- report.approve 발행 기록(outbox)
  failed_stage text CHECK (failed_stage IN ('session','report')),
  failed_reason text,
  token_usage jsonb NOT NULL DEFAULT '{}'::jsonb,  -- 세션 누계(agent_runs 합), 예산 검사용
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE session_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  card_id text NOT NULL,
  element text,                             -- 흐름 카드·texture는 null
  due_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','fired','done','failed','skipped')),   -- skipped는 texture만
  fired_at timestamptz,
  done_at timestamptz,
  attempts int NOT NULL DEFAULT 0,
  run_id uuid,                              -- fired 시 생성, 재실행에서 재사용
  texture boolean NOT NULL DEFAULT false,   -- 결 메시지(midpoint_draft): 관찰 창에 안 들어감
  or_on_submit boolean NOT NULL DEFAULT false,      -- 제출 시 pending이면 즉시 fired(보고 요청)
  document_missing boolean NOT NULL DEFAULT false,  -- send_document가 재시도 뒤에도 실패
  UNIQUE (session_id, card_id)
);
CREATE INDEX ON session_events (due_at) WHERE status = 'pending';
CREATE INDEX ON session_events (session_id) WHERE status = 'fired';

CREATE TABLE messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  channel text NOT NULL CHECK (channel IN ('team','dm','manager_dm','assistant','notice')),   -- notice: 지원자에게만 보이는 시스템 알림
  sender text NOT NULL CHECK (sender IN ('manager','colleague','candidate','assistant','system')),
  content text NOT NULL,
  event_id uuid REFERENCES session_events(id),
  run_id uuid,
  seq int,
  client_msg_id text,                       -- 지원자 메시지 재전송 멱등
  meta jsonb NOT NULL DEFAULT '{}'::jsonb,  -- classification, shared_doc, reply_to_doc, 토큰·지연·모델
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, run_id, seq)
);
CREATE INDEX ON messages (session_id, created_at);
CREATE UNIQUE INDEX ON messages (session_id, client_msg_id) WHERE client_msg_id IS NOT NULL;

CREATE TABLE agent_runs (
  run_id uuid PRIMARY KEY,
  session_id uuid NOT NULL REFERENCES sessions(id),
  stimulus text NOT NULL CHECK (stimulus IN ('message','event','division','end')),
  ref_ids uuid[] NOT NULL DEFAULT '{}',     -- message_id, event_id 묶음 또는 task_event id
  status text NOT NULL DEFAULT 'started' CHECK (status IN ('started','finished','failed')),
  usage jsonb NOT NULL DEFAULT '{}'::jsonb, -- llm_calls, retries, tokens_in, tokens_out, latency_ms, tool_calls
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);
CREATE INDEX ON agent_runs (session_id) WHERE status = 'started';

-- 문서 = 파트 하나 또는 최종본. 주인 한 명. 시작 시 지원자 파트 문서 5개와 최종본 1개, 동료 문서는 처음 보낼 때 생성.
CREATE TABLE documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  owner text NOT NULL CHECK (owner IN ('candidate','colleague')),
  part_no int CHECK (part_no BETWEEN 1 AND 5),   -- 최종본은 null
  final boolean NOT NULL DEFAULT false,
  title text NOT NULL,
  content text NOT NULL DEFAULT '',         -- 현재 편집 내용(디바운스 저장, version 아님)
  revision int NOT NULL DEFAULT 0,          -- 마지막 자동 저장 번호
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (final = (part_no IS NULL)),
  UNIQUE (session_id, owner, part_no)
);
CREATE UNIQUE INDEX ON documents (session_id) WHERE final;

CREATE TABLE document_revisions (            -- 자동 저장마다 append(최종본 섹션 편집·가져오기 포함)
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id uuid NOT NULL REFERENCES documents(id),
  revision int NOT NULL,
  by text NOT NULL CHECK (by IN ('candidate','colleague')),
  content text NOT NULL,                    -- 본문 스냅샷
  length int NOT NULL,
  diff_ratio real,                          -- 직전 revision 대비 변화율
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (doc_id, revision)
);

CREATE TABLE document_versions (             -- "보내기"가 만든다. 보낸 시점의 revision을 가리킨다
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id uuid NOT NULL REFERENCES documents(id),
  version int NOT NULL,
  revision int NOT NULL,
  content text NOT NULL,
  run_id uuid,                              -- 동료 보내기만. 같은 (doc_id, run_id)는 기존 행
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (doc_id, version)
);
CREATE UNIQUE INDEX ON document_versions (doc_id, run_id) WHERE run_id IS NOT NULL;

CREATE TABLE document_shares (               -- 보낸 기록. observe의 share 근거
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id uuid NOT NULL REFERENCES documents(id),
  version int NOT NULL,
  channel text NOT NULL CHECK (channel IN ('team','dm')),
  message_id uuid NOT NULL REFERENCES messages(id),   -- 채널에 올라간 문서 카드 메시지
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (doc_id, version) REFERENCES document_versions(doc_id, version)
);

CREATE TABLE document_opens (                -- 받은 문서를 연 기록. observe의 open 근거
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id uuid NOT NULL REFERENCES documents(id),
  version int NOT NULL,
  by text NOT NULL DEFAULT 'candidate' CHECK (by IN ('candidate')),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (doc_id, version) REFERENCES document_versions(doc_id, version)
);

CREATE TABLE final_document (                -- 최종본 섹션별 내용과 출처
  session_id uuid PRIMARY KEY REFERENCES sessions(id),
  sections jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{part_no, title, content, source_doc_id, source_version, edited}]
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE doc_views (                     -- 회사 문서 열람
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  doc_id text NOT NULL,
  viewed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tasks (                         -- 보드. 시작 시 5행 assignee=null, order=파트 번호
  session_id uuid NOT NULL REFERENCES sessions(id),
  part_no int NOT NULL CHECK (part_no BETWEEN 1 AND 5),
  assignee text CHECK (assignee IN ('candidate','colleague','both')),
  status text NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','doing','done')),
  "order" int NOT NULL,
  due_min int,                              -- 세션 분
  depends_on int[] NOT NULL DEFAULT '{}',
  PRIMARY KEY (session_id, part_no)
);

CREATE TABLE task_events (                   -- 보드 변경. 계획성·적응성 관찰 입력
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  part_no int NOT NULL,
  by text NOT NULL CHECK (by IN ('candidate','colleague')),
  field text NOT NULL CHECK (field IN ('assignee','status','order','due_min')),
  old_value text,
  new_value text,
  run_id uuid,                              -- 동료 변경만. 같은 (part_no, field, run_id)는 기존 행
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON task_events (session_id, created_at);
CREATE UNIQUE INDEX ON task_events (session_id, part_no, field, run_id) WHERE run_id IS NOT NULL;

CREATE TABLE document_releases (
  session_id uuid NOT NULL REFERENCES sessions(id),
  doc_id text NOT NULL,
  release_at timestamptz NOT NULL,
  released_at timestamptz,
  PRIMARY KEY (session_id, doc_id)
);

CREATE TABLE observations (                  -- 카드 단위 관찰 창
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  card_id text NOT NULL,
  element text NOT NULL,
  window_start timestamptz NOT NULL,        -- 카드 due_at(planning_division은 세션 시작)
  window_end timestamptz NOT NULL,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {<지표>: {value, evidence_ids}}
  label text,
  aux jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{type: message|document|share|open|task_event|doc_view|assistant_call, id}]
  facts jsonb,                              -- 정직 카드의 사실 입력(GET /honesty_facts)
  run_id uuid,
  updated_run_id uuid,                      -- 종료 finalize PATCH(metrics_patch) 멱등 키
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, card_id, window_start)
);

CREATE TABLE connection_gaps (               -- in_progress·reporting 중 WS 연결이 없던 구간. 점수 무관 사실
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  disconnected_at timestamptz NOT NULL,
  reconnected_at timestamptz
);
CREATE INDEX ON connection_gaps (session_id);

CREATE TABLE assistant_calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  request_message_id uuid NOT NULL REFERENCES messages(id),
  response_message_id uuid REFERENCES messages(id),
  cited_doc_ids text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE assistant_reuse (               -- 제출 시 호출 × 지원자 문서(파트·최종본)별 계산
  call_id uuid NOT NULL REFERENCES assistant_calls(id),
  doc_id uuid NOT NULL REFERENCES documents(id),
  part_no int,                              -- 최종본은 null
  ratio real NOT NULL,                      -- 내부 값. 응답·리포트에 싣지 않음
  applied boolean NOT NULL,                 -- ratio >= 0.3
  computed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (call_id, doc_id)
);

CREATE TABLE debrief_surveys (               -- 종료 설문 2문항(natural·fair, 1~5). 한 번만 저장
  session_id uuid PRIMARY KEY REFERENCES sessions(id),
  answers jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reports (
  session_id uuid PRIMARY KEY REFERENCES sessions(id),
  stage text NOT NULL CHECK (stage IN ('draft','final')),
  content jsonb NOT NULL,
  content_hash text NOT NULL,               -- 정규화 JSON 해시. final은 승인 draft와 같아야 함
  generated_at timestamptz NOT NULL DEFAULT now(),
  reviewed_at timestamptz,
  attempts int NOT NULL DEFAULT 0,
  usage jsonb NOT NULL DEFAULT '{}'::jsonb, -- 워커 LLM 사용량
  auto_met int, auto_unmet int, auto_no_record int,              -- draft 저장 시 api가 content.rubric에서 추출
  reviewer_met int, reviewer_unmet int, reviewer_no_record int,  -- 검토 완료(approving 전이) 시
  review_memo text,
  reviewer_name text
);

CREATE TABLE rubric_adjustments (            -- 항목별 담당자 조정(append-only). GET report 때 병합
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  element text NOT NULL,
  card_id text NOT NULL,
  item_id text NOT NULL,
  auto_value smallint,
  reviewer_value smallint,                  -- null 조정 허용(기록 없음으로)
  memo text NOT NULL,
  reviewer_name text NOT NULL,
  admin_id uuid NOT NULL REFERENCES admins(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, item_id)              -- 검토 완료는 1회라 항목당 조정 1행
);
CREATE INDEX ON rubric_adjustments (session_id);

CREATE TABLE report_notes (                  -- 검토 완료 뒤 추가한 메모(값은 바꾸지 않음)
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  text text NOT NULL,
  reviewer_name text NOT NULL,
  admin_id uuid NOT NULL REFERENCES admins(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON report_notes (session_id);

CREATE TABLE doc_chunks (                    -- rag-mcp만 접근
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id text NOT NULL,
  chunk_no int NOT NULL,
  content text NOT NULL,
  embedding vector(1024) NOT NULL,
  model text NOT NULL DEFAULT 'BAAI/bge-m3',
  catalog_version text NOT NULL,
  UNIQUE (catalog_version, doc_id, chunk_no)
);
