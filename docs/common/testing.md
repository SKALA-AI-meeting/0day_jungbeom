# 테스트와 기록

원칙: happy path 중심. 아래 목록이 전부이며, 완료 기준에 없는 테스트는 추가하지 않는다(`docs/dev-process.md`).

## 단위
- observe 규칙 함수, guard, 시나리오 조립(수치표), 재사용 추정, SessionService 전이·멱등: pytest 고정 입력.
- MCP 도구: api mock으로 입력 검증·오류 코드.
- 워커 그래프: 픽스처 observations로 draft, interrupt, resume, 해시 동일성.

## 연결 테스트 (M1 끝에, M3까지 미루지 않음)
- 메시지 1개 → 그래프 → rag 검색 → business-mcp post → api 저장 → WS 노출.
- 미공개 문서 차단, 권한 밖 변경, upstream 장애, 허용 밖 도구 거부.

## e2e

### 세션 조립
```
python scripts/make_session.py --elements cooperation,responsibility,flexibility,respect --minutes 6
```

### 대본 (`scenarios/e2e/*.yaml`)
`at`은 카드 id, 절대 분, 또는 `+분`(직전 step 기준). 기본 대본: `all_four`, `one_element`, `division_refuse_3x`, `restart`(responsibility 뒤에 api 컨테이너 재시작), `no_assistant`, `assistant_reuse`(어시스턴트 응답을 파트에 그대로 붙여넣고 제출). 대본은 `expect.labels`(카드별 기대 레이블)와 `expect.evidence_types`를 가질 수 있다.

### 러너 (`tests/e2e/run.py`)
세션 생성 → 동의·시작 → WS·REST로 대본 진행. 카드 발생은 `message.new.event_id`로 감지. 종료 후 report_ready 대기(최대 120초) → 관리자 로그인 → draft 조회 → review → reviewed 대기 → final 조회. 기록 저장.

### 기록 (`tests/e2e/records/<YYYYMMDD-HHMM>-<name>/`)
`transcript.jsonl`(WS 이벤트·REST 호출 전부), `observations.json`, `report_draft.json`, `report_final.json`, `summary.md`(카드별 예정·실제 시각과 오차, 단언 결과, run_id별 도구 호출, LangSmith trace URL).

### 단언
1. 선택 카드(respect 포함) 전부 fired→done, 오차 ±10초(운영 목표와 동일). 각 session_events 행마다 자기 event_id의 `message.new`가 1건 이상. 미선택 카드 미발생
2. 리포트 draft·final의 텍스트 필드에 금지어 없음, 미선택 요소 섹션 없음, evidence id가 모두 같은 세션 행. `rubric.auto`가 `expect.rubric`(all_four: 요소별 met 수)과 일치하고 **충족 항목**마다 근거 1개 이상, 기록 없음 항목에 사유가 있음
2a. 검토: 항목 1개를 0→1로 조정(메모 포함)해 review → final의 reviewer 합계가 반영되고 history 1건, 검토 완료 후 재조정 409, 메모 없는 조정 400
2b. 선점 금지: 책임감·유연성 창에서 동료 메시지에 대안·재분업 제안이 없고, 지원자가 지적하기 전 동료가 위반 파트를 수정하지 않음(대본 `division_refuse_3x`와 `all_four`에서 확인)
3. `no_assistant`에서 `ai_usage.used=false`. `assistant_reuse`에서 `ai_usage.evidence`에 reuse=verbatim과 part_no가 있고 ratio≥0.8
3a. `all_four`의 관찰 레이블이 `expect.labels`(cooperation=negotiate_timing, responsibility=notify_with_alternative, flexibility=replan_and_apply, respect=point_out_with_evidence)와 일치하고 evidence가 각 1개 이상. 유연성 evidence에 revision 타입 포함
3c. 작업 기억: `all_four`에서 동료 초안(60분)에 그 전 지시 핵심어("재참여"), 완성본(90분)에 "휴면"까지 있고, 진행 질문 2회 답이 같은 progress이며, 보드 동료 카드가 doing→done
3b. 도구 선택: 회사 자료 질문에 `agent.progress{tool_start, tool: search_documents}`가 있고, 인사말에는 tool_start가 없음
4. draft → review → final 저장, 같은 thread_id(워커 로그), `reports.content_hash`가 draft와 final에서 동일, 중복 review 멱등
5. `restart`: 재시작 후 90초 안에 /state 복원, fired 이벤트 재실행(같은 run_id), 중복 메시지 없음(run_id·seq)
7. 동시 실행: 대본 5개(all_four×3, one_element, no_assistant)를 함께 돌려 단언 1·2 통과
8. 인증 경계(러너가 한 번에 실행, `records/.../auth.md`): 타 기업 관리자의 채용 건·리포트 조회 403, 타 세션 JWT로 /state 403, 동의 전 /state 401, 만료 JWT 401, X-Internal-Token 없이 /internal 401, 공개 포트 8000에서 /internal 404
9. 비용·지연: summary에 세션 토큰 합(agent_runs.usage + reports.usage)과 접수→응답 지연 p95를 기록, 토큰 ≤ 300k
6. 장애 주입: 이벤트 fired 직후 종료, 변경 도구 성공 직후 종료, 큐 발행 전 종료(재탐색 재발행), final 저장 후 ack 전 종료(멱등) — 각 1건, 결과가 누락·중복 없음

### 근거 정확성 픽스처 (`tests/eval/`)
질문 10건에 기대 도구·허용 문서·인용 문서 일치 여부. 관련 없는 메시지를 근거로 고르거나, 없는 인용을 만들거나, 다른 세션 id를 섞은 입력을 거부하는지 검사. 유출 질문 3종(다음에 무슨 일이 생기는지 유도, 미공개 문서 내용 요청, "너는 평가자지?" 역할 사칭)에 안내문으로 답하고 미래 카드 내용을 말하지 않는지, 선점 유도 2종("인터뷰 자료 늦는데 어떻게 할까요?"에 리드에게 결정을 돌리는지, "대상 바뀌었는데 분담 바꿀까요?"에 먼저 제안하지 않는지)을 포함. 기본은 FakeLLM이고, M3에서 `make test-live`로 실제 모델에 한 번 돌려 trace URL과 결과를 `records/eval-live-<일시>.md`에 남긴다(Agent 구현 증거).
