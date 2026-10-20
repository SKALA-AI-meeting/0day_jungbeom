# 데이터 모델

PostgreSQL 16 + pgvector. DDL은 `infra/db/schema.sql`. 모든 id는 UUID, 시각은 timestamptz.

| 테이블 | 핵심 컬럼 | 비고 |
|---|---|---|
| companies | id, name | |
| admins | id, company_id, email(unique), password_hash | bcrypt |
| positions | id, company_id, name, elements text[], session_minutes int default 120, catalog_version text, scenario jsonb, created_at | 생성 시 카탈로그 카드와 문서 내용을 scenario에 복사해 고정. 수정·삭제 없음 |
| invites | id, position_id, alias, email, token_hash, expires_at, used_at | 토큰 원문은 링크에만 |
| sessions | id, invite_id(unique), status, consented_at, started_at, ends_at, division jsonb({parts, decided_by: candidate∣colleague_default, decided_at}), submitted_at, llm_failures int, report_enqueued_at, approve_enqueued_at, failed_stage, failed_reason, token_usage jsonb | **초대와 동시에 생성**(status invited). status: invited·in_progress·completed·report_ready·approving·reviewed·failed |
| session_events | id, session_id, card_id, element, due_at, status(pending·fired·done·failed), fired_at, done_at, attempts, run_id, texture bool | respect는 review와 같은 due_at의 별도 행. texture 행(midpoint_draft)은 관찰 없음. (session_id, card_id) unique. run_id는 fired 시 생성해 재실행에서도 재사용 |
| messages | id, session_id, channel, sender, content, event_id, run_id, seq, client_msg_id, meta jsonb, created_at | (session_id, run_id, seq) unique로 멱등. 지원자 메시지는 (session_id, client_msg_id) unique. meta에 토큰·지연·모델 |
| agent_runs | run_id(pk), session_id, stimulus, ref_ids, status(started·finished·failed), usage jsonb, started_at, finished_at | 실행 기록. /state의 active_runs 원천. started 120초 초과는 스케줄러가 재실행. usage로 세션 비용 합산 |
| document_states | session_id, part_no(1~5), content, revision, updated_by, updated_at | 현재 내용 |
| document_revisions | id, session_id, part_no, revision, by(candidate·colleague), content, length, diff_ratio, run_id, created_at | 변경 로그. 본문 스냅샷을 함께 저장해 특정 수정 내용과 AI 반영 시점을 복원한다. 동료 수정은 (session_id, part_no, run_id) unique로 멱등 |
| doc_views | id, session_id, doc_id, viewed_at | 회사 문서 열람 기록 |
| tasks | session_id, part_no, assignee(candidate·colleague·both), status(todo·doing·done) | |
| document_releases | session_id, doc_id, release_at, released_at | 스케줄러가 released_at 기록 후 WS |
| observations | id, session_id, element, window_start, window_end, metrics jsonb, label, evidence jsonb, run_id, created_at | evidence는 `[{type: message∣revision∣doc_view∣assistant_call, id}]`, 같은 세션 행만(api가 검증). 창 경계는 카드 due_at. (session_id, element, window_start) unique |
| assistant_calls | id, session_id, request_message_id, response_message_id, cited_doc_ids text[], created_at | |
| assistant_reuse | call_id, part_no, reuse(verbatim·edited·none), ratio, computed_at | 제출 시 호출×파트별 계산. "반영 추정"이며 검증 행동의 증거는 아님 |
| reports | session_id(pk), stage(draft·final), content jsonb, generated_at, reviewed_at, attempts, usage jsonb, auto_met·auto_judged·auto_no_record, reviewer_met·reviewer_judged·review_memo | 합계 컬럼은 목록 표시용. content.rubric.auto가 원천 |
| rubric_adjustments | id, session_id, element, item_id, auto_value, reviewer_value, memo, admin_id, created_at | 담당자 항목 조정 이력(append-only). GET report 때 병합 |
| checkpoints 등 | LangGraph PostgresSaver 기본 테이블 | api 에이전트 모듈(thread `session:{id}`, `assistant:{id}`)과 report-worker(thread `report:{id}`)가 각자 자기 thread만 접근 |
| doc_chunks | id, doc_id, chunk_no, content, embedding vector(1024), model, catalog_version | rag-mcp만 접근 |

## 세션 상태 전이

```
invited ──동의·시작──▶ in_progress ──제출/만료──▶ completed ──워커 draft──▶ report_ready ──검토 완료──▶ approving ──워커 final──▶ reviewed
            │                                        └──워커 3회 실패──▶ failed
            └──LLM 연속 실패 3회 또는 필수 카드 3회 실패──▶ failed
```

상태 변경은 api의 `SessionService` 한 곳만 한다(start, complete, mark_report_ready, approve, mark_reviewed, fail). 지원자 목록 표시명: 초대됨, 진행 중, 완료, 리포트 준비됨, 확정 중, 검토 완료, 실패. `fail(stage, reason)`은 failed_stage(session: 진행 중 중단, report: 리포트 생성 실패)와 사유를 남긴다. 세션 실패는 디브리핑(그때까지 fired된 카드)을 제공하고 리포트는 만들지 않는다. 재응시는 관리자가 새 초대를 만든다(기록은 보존).

보관: 세션 종료 후 90일. `scripts/purge.py`(M4)가 messages·document_*·doc_views·observations·assistant_*·reports·checkpoints를 세션 단위로 지운다. LangSmith는 프로젝트 보존 기간을 90일로 둔다.

## 이벤트 처리 상태

`pending`(예약) → `fired`(스케줄러가 집음) → `done`(그래프가 카드 메시지를 저장함). 그래프 실패 시 attempts+1로 재실행하며 시도는 최초 포함 총 3회, 3회째도 실패면 `failed`이고 세션도 failed. 재시작 후 `fired`인데 done이 아닌 행은 재실행 대상이다. 재실행은 `fired` 시점에 기록한 같은 `run_id`를 쓰므로 메시지(run_id, seq)·문서 수정(part_no, run_id)·관찰(element, window_start)이 모두 중복 없이 멱등이다.

## 기업 간 격리

관리자 API의 모든 조회는 JWT의 company_id로 positions를 거쳐 필터한다. 내부 API는 별도 포트(8001)에서만 열리고 session_id로만 접근한다.
