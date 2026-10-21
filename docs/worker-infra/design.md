# 워커와 인프라

## report-worker (`services/report-worker/`)

리포트 생성은 작은 LangGraph 그래프다. thread `report:{session_id}`, PostgresSaver(워커는 이 thread만 접근).

```
collect → draft → approval[interrupt] → finalize   (draft 생성 노드와 interrupt 노드를 분리: 재개 시 approval 노드만 다시 실행되고 draft 생성은 반복되지 않음)
```

1. `report.generate` 소비(prefetch 1, manual ack). 본문 `{session_id, attempt}`. 처리 전에 thread `report:{session_id}`의 상태를 조회한다. 이미 interrupt에 멈춰 있으면 collect·draft를 건너뛰고 4단계(draft 저장)부터, final까지 끝났으면 ack만.
2. **collect**: 내부 API로 session(mission_id·elements·completed_at), observations(카드 단위, (card_id, window_start). 종료 시 PATCH로 확정된 `promise_kept`가 이미 들어 있으므로 워커는 다시 계산하지 않는다), assistant_calls, assistant_reuse(반영된 파트만), messages(`meta.classification` 포함), documents·document_revisions·document_versions·document_shares·document_opens, final_document(섹션별 출처·버전·edited), tasks·task_events, doc_views, connection_gaps, honesty_facts(`GET /internal/sessions/{id}/honesty_facts`, `{shares, final_sections, section_owners, empty_sections, tasks_not_done, changed_after_adaptability: bool∣null}`. api가 계산. 워커는 재계산하지 않는다).
3. **draft**: 맨 위에 `summary`(요소별 한 줄 관찰 문장과 `{met, unmet, no_record}`)를 두고, 선택 요소마다 섹션을 만들어 그 안에 **카드 소섹션**(요소당 1~2장)을 조립한다(situation은 카탈로그 카드, label→observed 문장 템플릿은 카탈로그 `label_texts`, evidence는 rubric.md의 근거 타입 그대로: message·assistant_call은 원문 인용, document는 "n번 문서 편집(t_min)"과 변화율(document_revisions에서), share는 "n번 문서 vN 보냄(t_min, 채널)", open은 "도현 n번 vN 열람(t_min)", task_event는 "n번 섹션 할 일·섹션 담당·상태·언제까지 변경(t_min)", doc_view는 문서명과 시각). 모든 근거에 `record_ref`(전체 기록 타임라인의 항목 id)를 붙여 화면이 "기록에서 보기"로 잇는다. label 매핑: 카드 레이블 → 그 문장; `no_evidence`·null → observed=null, `unclassified` → observed=null + evidence 그대로 표시. 기록 없음 사유는 **코드만** 낸다(`no_activity`·`classify_failed`·`event_not_fired`·`not_applicable`·`window_missed`·`document_missing`). 책임 주체 문장("지원자 활동 없음", "시스템: 문서 미제공" 등)으로의 매핑은 web이 한다. **평가표**: 카드마다 카탈로그 `rubric` 조건을 그 카드 observation의 label·aux·metrics에 대입해 항목 1/0/null을 계산하고, 요소 `auto` 합계는 카드 항목의 합이다(요소당 4항목: 2+2 또는 4. 순수 함수 `rubric.evaluate`, LLM 없음, 규칙은 docs/common/rubric.md). 항목마다 `basis ∈ metric∣label`(규칙 지표만으로 계산됐는지, AI 분류 레이블·aux가 들어갔는지)을 붙이고 근거를 붙인다(그 항목의 조건에 쓰인 지표·레이블의 evidence_ids만, 충족 항목에만). `only_if` 전제는 metrics `has_colleague_shares`·`has_incomplete_facts`·`has_report_message`로 판정한다. 카드 메시지 전달이 늦었으면(window_missed) 그 카드 항목 전부가 기록 없음이고, 동료 문서 전송이 끝내 실패했으면 그 문서에 의존하는 항목이 사유 `document_missing`이다. 카드 소섹션에는 `event_fired`와 근거 맥락(직전 페르소나 메시지, 카드 시각)을 넣고, 점수와 무관한 사실(aux_facts 지표, related_card가 이 카드인 창 밖 메시지)은 별도 목록이 아니라 같은 evidence 배열에 `flag ∈ aux_fact∣out_of_window`를 단 항목으로 넣는다. 정직 카드 소섹션은 honesty_facts를 사실로 표시하고(주석 "미완료는 보드 기준") 보고 메시지 원문을 옆에 둔다. **산출물** 섹션: 최종본(섹션마다 "어느 문서 v몇에서 가져옴"·주담당 편집 여부·본문)과 주고받은 문서 목록(문서·주인·버전·보낸 시각·열람 시각), 접속 끊김 구간. 합격·순위 표현은 없다. **AI 활용**은 라벨·비율 없이 시간순 사실만이다: 호출이 없으면 used=false, 있으면 `events: [{call_id, t_min, request, response, cited_docs, applied_part: part_no∣"final"∣null, record_ref}]`(applied_part는 assistant_reuse의 반영된 파트). LLM 요약·분류는 하지 않는다. 근거 id가 같은 세션 데이터인지 검증(아니면 제거). 텍스트 필드(observed·summary 문장)에 금지어 검사 후 draft를 state에 담는다(rubric 숫자 필드는 검사 대상 아님). 리포트 JSON에 `history`와 요소별 reviewer 소계는 없다. 검토 정보는 api가 GET 때 `review {memo, reviewer_name, reviewed_at}`와 `notes[]`(검토 후 메모)로 붙인다. 이어서 **approval** 노드가 `interrupt(draft)`로 멈춘다(이 시점에 체크포인트가 먼저 저장된다). 노드를 나눈 이유: LangGraph는 재개 시 interrupt가 있던 노드를 처음부터 다시 실행하므로, 같은 노드에 두면 LLM 요약이 재실행된다.
4. 그래프가 멈춘 뒤 워커가 state의 draft로 `POST /report/draft`(멱등, api가 content_hash 저장) → report_ready → **ack**. 순서가 체크포인트 → draft 저장 → ack이므로 ACK 뒤에 승인이 와도 재개 대상이 항상 있다. draft 저장 전에 죽으면 재전달이 1단계의 상태 조회로 여기부터 다시 한다. 승인 전 final은 api가 409로 거부한다.
5. `report.approve` 소비 → 같은 thread_id로 `Command(resume=True)` → **finalize**: 승인한 draft와 동일한 내용(해시 비교)으로 `POST /report/final` → reviewed → ack. thread에 멈춘 체크포인트가 없으면(generate가 아직 처리 전) nack 없이 15초 뒤 재발행.
6. 실패·예외: attempt+1로 재발행(백오프 5·15·45초) 후 원본 ack. attempt≥3이면 `report.dlq`로 보낸다. "3회"는 최초 포함 총 3회.
7. `report.dlq` 소비(같은 워커의 두 번째 소비자): `POST /report_failed` 호출 후 ack. api가 내려가 있으면 ack하지 않고 60초 뒤 재시도하므로 복구 후 세션이 failed로 반영된다.

## RabbitMQ
- exchange `dayzero`(direct). 큐 `report.generate`, `report.approve`(둘 다 durable, DLX → `report.dlq`), `report.dlq`.
- 메시지 persistent. 관리 UI는 `127.0.0.1:15672`에만 바인딩.

## Docker Compose (`infra/docker-compose.yml`)
서비스: postgres, rabbitmq, api(8000 공개, 8001 내부), business-mcp, rag-mcp, report-worker, web(3000 공개). healthcheck: api·MCP는 `/health`, web은 `/api/health` 라우트, report-worker는 30초마다 갱신하는 `/tmp/heartbeat` 파일(90초 이상 오래되면 unhealthy). 의존은 `service_healthy`. 공개 포트는 web·api 8000·rabbitmq 관리(로컬 바인딩)뿐.

## 환경변수
`OPENAI_API_KEY, OPENAI_MODEL=gpt-4o-mini, DATABASE_URL, RABBITMQ_URL, JWT_SECRET, INTERNAL_TOKEN, API_INTERNAL_URL=http://api:8001, BUSINESS_MCP_URL, RAG_MCP_URL, EMBEDDING_MODEL, SCENARIOS_DIR, ENABLE_TEST_API, LANGCHAIN_*, NEXT_PUBLIC_API_URL, NEXT_PUBLIC_WS_URL`

## 완료 기준
- 픽스처로 draft 생성 후 그래프가 멈춤 → approve 메시지로 같은 thread 재개 → final 저장(draft와 동일 해시), 중복 approve는 멱등(reviewed면 상태 확인 후 ack), final 저장 후 ack 전 재전달은 200 기존 값
- LLM 사용량을 `reports.usage`에 기록
- 금지어·타 세션 근거 id 제거 테스트
- `rubric.evaluate` 단위 테스트: 카드 7장 각각 픽스처 observations → 카드 항목 값·요소 합계(2+2 합산, 기록 없음 사유 코드 처리, 창 밖 related_card 메시지 포함, basis 표시, only_if 지표 3개, 적응성 반영 항목은 document_changed_after와 target_applied 둘 다 참일 때만, 종료 시 확정된 promise_kept 반영, document_missing 사유)
- 리포트 형태: summary 요약표, evidence마다 record_ref, 점수 무관 근거는 flag(aux_fact∣out_of_window), history·reviewer 소계 없음, ai_usage는 시간순 사실만(라벨·비율 없음)
- 산출물 섹션: 최종본 섹션 출처·주담당 편집 여부와 주고받은 문서 목록·접속 끊김 구간이 픽스처와 일치. 정직 소섹션에 honesty_facts(empty_sections·tasks_not_done·changed_after_adaptability null 포함)가 그대로 표시됨
- api를 내린 상태에서 발행 → 3회 재시도 후 DLQ, 복구 후 report_failed 반영
- `docker compose up`으로 전부 healthy
