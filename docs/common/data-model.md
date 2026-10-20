# 데이터 모델

PostgreSQL 16 + pgvector. DDL은 `infra/db/schema.sql`. 모든 id는 UUID, 시각은 timestamptz.

| 테이블 | 핵심 컬럼 | 비고 |
|---|---|---|
| companies | id, name | |
| admins | id, company_id, email(unique), password_hash | bcrypt |
| positions | id, company_id, name, mission_id text, elements text[], session_minutes int default 120, catalog_version text, scenario jsonb, created_at | 생성 시 미션 카탈로그 카드와 문서 내용을 scenario에 복사해 고정. catalog_version은 미션 폴더 해시. 수정·삭제 없음 |
| invites | id, position_id, alias, email, token_hash, expires_at, used_at, cancelled_at, previous_session_id | 토큰 원문은 링크에만. 목록 표시 상태 "만료"는 invited이고 expires_at 지남으로 계산. previous_session_id는 그 세션이 failed(session)·만료·cancelled일 때만. (position_id, alias) unique |
| sessions | id, invite_id(unique), status, consented_at, started_at, ends_at, division jsonb({parts, decided_by: candidate∣colleague_default, decided_at}), submitted_at, deadline_at, reported_at, completed_at, llm_failures int, report_enqueued_at, approve_enqueued_at, failed_stage, failed_reason, token_usage jsonb | **초대와 동시에 생성**(status invited). status: invited·cancelled·in_progress·reporting·completed·report_ready·approving·reviewed·failed. completed_at은 보고 종료 시각(마지막 관찰 창의 끝, 디브리핑 기한과 삭제 예정일의 기준). deadline_at = submitted_at + 5분 |
| session_events | id, session_id, card_id, element, due_at, status(pending·fired·done·failed), fired_at, done_at, attempts, run_id, texture bool, or_on_submit bool, document_missing bool | collab_disagree는 review와 같은 due_at의 별도 행. texture 행(midpoint_draft)은 관찰 없음. (session_id, card_id) unique. run_id는 fired 시 생성해 재실행에서도 재사용. or_on_submit 행은 제출 시 pending이면 즉시 fired. document_missing은 문서를 보내는 카드의 send_document가 재시도 뒤에도 실패했을 때 true(의존 항목은 사유 document_missing) |
| messages | id, session_id, channel(team·dm·manager_dm·assistant·notice), sender, content, event_id, run_id, seq, client_msg_id, meta jsonb, created_at | (session_id, run_id, seq) unique로 멱등. 지원자 메시지는 (session_id, client_msg_id) unique. meta에 토큰·지연·모델, 지원자 메시지는 meta.classification(recipient, kind, instruction, related_card. kind=report가 보고 메시지). 공유 문서 카드는 meta.shared_doc, 문서에 매인 답글은 meta.reply_to_doc {doc_id, version} |
| agent_runs | run_id(pk), session_id, stimulus, ref_ids, status(started·finished·failed), usage jsonb, started_at, finished_at | 실행 기록. /state의 active_runs 원천. started 120초 초과는 스케줄러가 재실행. usage로 세션 비용 합산 |
| documents | id, session_id, owner(candidate·colleague), part_no int(최종본은 null), final bool, title, content, revision int, updated_at | 문서 = 파트 하나 또는 최종본. 주인 한 명. 세션 시작 시 파트 수만큼 지원자 문서(빈 본문)와 최종본 1개를 만들고, 동료 문서는 동료가 처음 보낼 때 만든다. content는 현재 편집 내용(디바운스 저장, version 아님), revision은 마지막 자동 저장 번호. (session_id, owner, part_no) unique |
| document_revisions | id, doc_id, revision int, by(candidate·colleague), content, length int, diff_ratio float, created_at | 자동 저장마다 append(본문 스냅샷). 최종본 섹션 편집·가져오기도 남긴다(doc_id는 최종본 documents 행). (doc_id, revision) unique. observe의 `document` 근거와 재사용 추정이 읽는다. diff_ratio는 직전 revision 대비 변화율 |
| document_versions | id, doc_id, version int, revision int, content, run_id, created_at | "보내기"가 만든다. 보낸 시점의 revision을 가리킨다. (doc_id, version) unique. 동료 보내기는 (doc_id, run_id) unique로 멱등 |
| document_shares | id, doc_id, version, channel(team·dm), message_id, created_at | 보낸 기록. message_id는 채널에 올라간 문서 카드 메시지. observe의 `share` 근거, 기여 판정·정직 사실 입력의 원천 |
| document_opens | id, doc_id, version, by(candidate), created_at | 받은 문서를 연 기록. observe의 `open` 근거, 계획성 `draft_opened` |
| final_document | session_id(pk), sections jsonb([{part_no, title, content, source_doc_id, source_version, edited}]), updated_at | 최종본 섹션별 내용과 출처. "가져오기"가 source를 기록하고 edited=false(덮어쓰기만), 이후 편집 저장이 edited=true. 저장마다 최종본 documents 행의 document_revisions에도 append. 제출 시 최종본 documents 행에 version을 만든다 |
| doc_views | id, session_id, doc_id, viewed_at | 회사 문서 열람 기록 |
| tasks | session_id, part_no, assignee(candidate·colleague·both·null), status(todo·doing·done), "order" int, due_min int null, depends_on int[] | 세션 시작 때 5행을 assignee=null, order=파트 번호로 생성. depends_on은 미션 parts에서 복사(3번 → [2]). 지원자는 모든 카드의 담당·상태·순서·언제까지를 바꿀 수 있다. 5행의 assignee가 다 차고 division_min을 만족하면 api가 sessions.division을 확정(decided_by=candidate). 동료 set_division도 같은 행을 채운다 |
| task_events | id, session_id, part_no, by(candidate·colleague), field(assignee·status·order·due_min), old_value, new_value, run_id, created_at | 보드 변경 이벤트. 계획성·적응성 관찰 입력. 동료 변경은 (session_id, part_no, field, run_id) unique |
| document_releases | session_id, doc_id, release_at, released_at | 스케줄러가 released_at 기록 후 WS. release_at은 state의 `release_at_min` 원천 |
| observations | id, session_id, card_id, element, window_start, window_end, metrics jsonb, label, aux jsonb, evidence jsonb, facts jsonb, run_id, updated_run_id, created_at, updated_at | evidence는 `[{type: message∣document∣share∣open∣task_event∣doc_view∣assistant_call, id}]`(`rubric.md` 표), 같은 세션 행만(api가 검증). 창 경계는 요소 카드 due_at(planning_division은 세션 시작). facts는 정직 카드의 사실 입력(내부 `GET /honesty_facts` 응답). (session_id, card_id, window_start) unique. 종료 finalize의 PATCH(metrics_patch)는 지정 지표만 바꾸고 updated_run_id로 멱등 |
| connection_gaps | id, session_id, disconnected_at, reconnected_at | in_progress·reporting 동안 WS 연결이 없던 구간. 재접속 또는 종료 시 reconnected_at을 채운다. 점수 무관 사실 |
| assistant_calls | id, session_id, request_message_id, response_message_id, cited_doc_ids text[], created_at | |
| assistant_reuse | call_id, doc_id, part_no, ratio, applied bool, computed_at | 제출 시 호출×지원자 문서(파트·최종본)별 계산. 호출 이후 document_revisions와 비교한 최대 ratio이고 applied = ratio ≥ 0.3. 리포트에는 applied인 파트만 "반영된 파트" 사실로 싣고 비율은 싣지 않는다. 검증 행동의 증거는 아님 |
| debrief_surveys | session_id(pk), answers jsonb([{q, value}]), created_at | 종료 설문 2문항(natural·fair, 1~5). 한 번만 저장 |
| reports | session_id(pk), stage(draft·final), content jsonb, generated_at, reviewed_at, attempts, usage jsonb, auto_met·auto_unmet·auto_no_record, reviewer_met·reviewer_unmet·reviewer_no_record·review_memo·reviewer_name | 합계 컬럼은 목록 표시용. reviewer_*·review_memo·reviewer_name은 리뷰 제출(approving 전이) 트랜잭션에서 채운다. content.rubric.auto가 원천 |
| rubric_adjustments | id, session_id, element, card_id, item_id, auto_value, reviewer_value, memo, reviewer_name, admin_id, created_at | 담당자 항목 조정(append-only). GET report 때 병합 |
| report_notes | id, session_id, text, reviewer_name, admin_id, created_at | 검토 완료 뒤 추가한 메모(값은 바꾸지 않음) |
| checkpoints 등 | LangGraph PostgresSaver 기본 테이블 | api 에이전트 모듈(thread `session:{id}`, `assistant:{id}`)과 report-worker(thread `report:{id}`)가 각자 자기 thread만 접근 |
| doc_chunks | id, doc_id, chunk_no, content, embedding vector(1024), model, catalog_version | rag-mcp만 접근 |

## 세션 상태 전이

```
invited ──동의·시작──▶ in_progress ──제출/만료──▶ reporting ──보고 메시지 또는 submitted_at+5분──▶ completed ──워커 draft──▶ report_ready ──검토 완료──▶ approving ──워커 final──▶ reviewed
   │                        │                      │                                                   └──워커 3회 실패──▶ failed ──재생성──▶ completed
   └──취소──▶ cancelled ◀────┴──────────────────────┘ (시작 후 취소 = 중도 포기)
                            └──LLM 연속 실패 3회 또는 필수 카드 3회 실패──▶ failed
```

`reporting`: 제출(또는 만료 자동 제출)로 `submitted_at`·`deadline_at(=submitted_at+5분)`을 기록하고 최종본 version을 만든 뒤, 보고 요청 카드(honesty_report 또는 흐름 report_request)가 아직 pending이면 그 자리에서 실행한다. 보고 타이머는 하나의 규칙이다: 요청(11L/12 또는 제출 시 먼저 오는 쪽) 이후 팀 채널 또는 팀장 DM의 지원자 메시지가 `meta.classification.kind = report`로 저장되면 `reported_at`을 기록하고 completed, 없으면 deadline_at에 스케줄러가 completed로 넘긴다. 요청 뒤 제출 전에 이미 보고했으면 제출 즉시 completed. completed 전이에 `completed_at`을 저장하고 마지막 관찰 창은 이 시각까지다. reporting 중에는 모든 채널의 메시지를 받되(채널 잠금 없음) 문서 편집·공유·보드·어시스턴트는 409. 재입장(resume)은 in_progress·reporting 모두 허용한다.

상태 변경은 api의 `SessionService` 한 곳만 한다(start, submit, complete, cancel, mark_report_ready, approve, mark_reviewed, fail, regenerate). 지원자 목록 표시명은 다섯 묶음이다: 대기(초대됨·초대됨(만료)), 진행(진행 중·보고 중·완료), 검토 필요(리포트 준비됨), 완료(확정 중·검토 완료), 문제(실패·취소). `cancel`은 invited·in_progress·reporting에서 허용하고 시작 후 취소는 리포트를 만들지 않는다. `fail(stage, reason)`은 failed_stage(session: 진행 중 중단, report: 리포트 생성 실패)와 사유를 남기며 목록에 담당자 행동 안내(`next_action`)를 붙인다. 세션 실패(failed_stage=session)는 연출 설명 없이 중단 안내만 보여 주고(재응시 가능, PRD 7.4·contracts의 debrief) 리포트는 만들지 않는다. 재응시는 관리자가 새 초대를 만든다(기록은 보존, previous_session_id는 failed·만료·cancelled만). 리포트 실패(failed_stage=report)는 재초대가 아니라 `regenerate`로 completed로 되돌려 다시 발행한다.

보관: 세션 종료(completed_at) 후 90일. 삭제 예정일(`purge_at`)은 관리자 목록·리포트에 표시한다. `scripts/purge.py`(M4)가 messages·documents·document_revisions·document_versions·document_shares·document_opens·final_document·doc_views·tasks·task_events·observations·connection_gaps·assistant_*·debrief_surveys·reports·rubric_adjustments·report_notes·agent_runs·session_events·document_releases·checkpoints를 세션 단위로 지우고, sessions 행과 invites의 email·alias·token_hash도 지운다(조정 메모 포함. positions의 지원자 수만 남는다). LangSmith는 프로젝트 보존 기간을 90일로 둔다.

## 이벤트 처리 상태

`pending`(예약) → `fired`(스케줄러가 집음) → `done`(그래프가 카드 메시지를 저장함). 그래프 실패 시 attempts+1로 재실행하며 시도는 최초 포함 총 3회, 3회째도 실패면 `failed`이고 세션도 failed. 문서를 보내는 카드(planning_checkin·review)에서 `send_document`가 1회 재시도 뒤에도 실패하면 그 시도는 실패로 세고(같은 3회 규칙), 행에 `document_missing=true`를 남겨 그 문서에 의존하는 항목이 사유 document_missing으로 기록 없음이 된다. 재시작 후 `fired`인데 done이 아닌 행은 재실행 대상이다. 재실행은 `fired` 시점에 기록한 같은 `run_id`를 쓰므로 메시지(run_id, seq)·동료 문서 보내기(doc_id, run_id)·보드 변경(part_no, field, run_id)·관찰(card_id, window_start)·관찰 갱신(card_id, window_start, run_id)이 모두 중복 없이 멱등이다.

## 기업 간 격리

관리자 API의 모든 조회는 JWT의 company_id로 positions를 거쳐 필터한다. 내부 API는 별도 포트(8001)에서만 열리고 session_id로만 접근한다.
