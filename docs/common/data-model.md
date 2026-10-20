# 데이터 모델

PostgreSQL 16 + pgvector. DDL은 `infra/db/schema.sql`. 모든 id는 UUID, 시각은 timestamptz.

| 테이블 | 핵심 컬럼 | 비고 |
|---|---|---|
| companies | id, name | |
| admins | id, company_id, email(unique), password_hash | bcrypt |
| positions | id, company_id, name, elements text[], session_minutes int default 120, scenario jsonb, created_at | 수정·삭제 없음 |
| invites | id, position_id, alias, email, token_hash, expires_at, used_at | 토큰 원문은 링크에만 |
| sessions | id, invite_id(unique), status, consented_at, started_at, ends_at, division jsonb, submitted_at | status: invited·in_progress·completed·report_ready·approving·reviewed·failed |
| session_events | id, session_id, card_id, due_at, fired_at | 스케줄러 대상. (session_id, card_id) unique |
| messages | id, session_id, channel, sender, content, event_id, meta jsonb, created_at | channel: team·dm·assistant. sender: manager·colleague·candidate·assistant·system. meta에 토큰·지연 |
| document_states | session_id, part_no(1~5), content, updated_at | 기획안 파트 |
| tasks | session_id, part_no, assignee(candidate·colleague·both), status(todo·doing·done) | |
| document_releases | session_id, doc_id, release_at, released_at | release_at 도달 시 스케줄러가 released_at 기록 후 WS `document.released` |
| observations | id, session_id, element, window_start, window_end, metrics jsonb, label, evidence_message_ids uuid[], created_at | |
| assistant_calls | id, session_id, request_message_id, response_message_id, cited_doc_ids text[], reused_in_part, created_at | reused_in_part: none·verbatim·edited, 제출 시 계산 |
| reports | session_id(pk), stage(draft·final), content jsonb, generated_at, reviewed_at, attempts int | 워커 그래프가 draft 뒤 interrupt, 승인 후 final |
| checkpoints 등 | LangGraph PostgresSaver 기본 테이블 | 에이전트 모듈만 접근 |
| doc_chunks | id, doc_id, chunk_no, content, embedding vector(1024) | rag-mcp만 접근 |

## 세션 상태 전이

```
invited ──동의+시작──▶ in_progress ──제출/만료──▶ completed ──워커 draft──▶ report_ready ──검토 완료(큐)──▶ approving ──워커 final──▶ reviewed
                                                      └──3회 실패──▶ failed
```

지원자 목록의 표시명: 초대됨, 진행 중, 완료, 리포트 준비됨, 검토 완료, 실패.

## 기업 간 격리

관리자 API의 모든 조회는 JWT의 company_id로 positions를 거쳐 필터한다. 내부 API는 session_id로만 접근하며 외부에 노출되지 않는다.
