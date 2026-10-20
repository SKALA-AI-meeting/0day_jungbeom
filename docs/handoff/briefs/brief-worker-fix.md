# worker 수정 라운드 (Codex 리뷰 반영)
리뷰 전문: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/review-worker.md. 오케스트레이터 결정. 같은 브랜치에 커밋. 끝나면 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/worker-report-2.md 에 수정 목록·검증 명령·결과 저장(worktree의 REVIEW.md 삭제). 마지막 응답은 경로 한 줄.
이번 라운드에 한해 `services/api/app/routers/internal.py`(아래 지정 변경만)와 `docs/common/contracts.md`·`docs/decisions.md` 수정을 허용한다. web-admin은 이미 main에 병합돼 있으니(`apps/web/components/admin/`) 화면이 읽는 형태를 직접 확인해 맞춘다. 화면 코드는 수정하지 않는다.

## 리포트 JSON 형태 확정 (web-admin이 이미 이렇게 읽는다)
- 근거 `context.prev_persona_message`: **문자열** "<보낸이> · <t분>분: <본문>" (없으면 null). `context.card_at_t_min`: 실제 카드 메시지 시각(분). 지연 전달이면 실제 시각.
- 섹션 `aux_facts`: **string[]** (빈 배열 허용). `out_of_window_messages`: [{t_min, channel, quote}]. 섹션 `no_record_reason`.
- 항목 `items[].minutes`(응답 시간 항목만, 무관련이면 null), `items[].no_record_reason`.
- AI 활용 `ai_usage.evidence[].category ∈ delegate|context|verify`: 규칙으로 붙인다. reuse verbatim/edited → delegate, 지원자 요청문에 검토·확인·맞는지·검증 류 표현 → verify, 그 외 → context.
- 실제 워커 출력 fixture 1개를 `services/report-worker/tests/fixtures/report_sample.json`에 저장하고, 그 JSON을 web-admin의 타입(`apps/web/components/admin/types.ts`)과 대조한 결과를 보고에 적는다(가능하면 `apps/web`에서 그 JSON으로 `renderToStaticMarkup` 1회 실행해 오류 없음을 확인. 화면 코드 수정 금지).

## 반드시
1. 위 형태로 생산 변경(P1).
2. usage: `internal.py`의 `ReportIn`에 `usage: dict | None` 추가, draft 저장 시 `reports.usage`에 기록(재전달은 최초 값 유지), 해시는 content만. 테스트는 워커 쪽 전송 + api 쪽 저장 1개(services/api/tests/routers/test_internal.py의 기존 draft 테스트에 단언 추가).
3. 이벤트 상태: `GET /internal/sessions/{id}` 응답에 `events: [{card_id, element, status, due_at, fired_at}]` 추가(internal.py). 워커 `event_fired`·`card_at_t_min`·window_missed 판단을 이걸로 바꾸고 대용 추정 삭제. 리뷰의 respect/review 재현을 테스트 단언으로.
4. 메시지 전체 수집: `GET /internal/sessions/{id}/messages`에 `offset` 쿼리 추가(internal.py), 워커는 limit 500으로 offset 페이지네이션.
5. 금지어: 1위·N위·N등·만점·감점·가산점·상위 N%·등수 추가(우선순위·quote 원문·평가표 숫자는 보존). 테스트에 대표 표현 포함.
6. pyproject·lock 변경은 **승인**(psycopg[binary] 런타임, pyyaml dev). decisions.md에 소유권 예외로 기록.

## 같이
- test_graph happy path에 approve 뒤 `llm.calls == 1` 단언.
- DLQ·Postgres fixture: 부분 초기화 실패 시에도 정리.
- config: OPENAI_MODEL이 gpt-4o-mini가 아니면 시작 시 오류.
- null 지표 사유: 레이블이 정상이어도 aux 기반 지표가 null이면 `classify_failed`. window_missed 형식은 `metrics.window_missed: {value: true, evidence_ids: []}`로 확정(bool도 허용).

## 문서
- contracts.md: Report JSON의 위 형태(섹션·항목·근거 context·ai_usage category), 내부 API `report/draft` 본문 `usage`, `GET /internal/sessions/{id}`의 `events`, messages `offset`, 관찰 `window_missed` 형식, 큐 재시도 백오프 5·15·45초.
- decisions.md 맨 아래 "2026-10-20 worker 리뷰 반영" 절: 형태 확정, usage·events·offset, null 사유, 소유권 예외.
