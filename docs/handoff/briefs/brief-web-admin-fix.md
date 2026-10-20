# web-admin 수정 라운드 (Codex 리뷰 반영)
리뷰 전문: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/review-web-admin.md. 오케스트레이터 결정. 같은 브랜치에 커밋. 끝나면 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/web-admin-report-2.md 에 수정 목록·검증 명령·결과 저장(worktree의 REVIEW.md 삭제). 마지막 응답은 경로 한 줄.

## 반드시
1. 재초대(F-02): 지원자 행이 failed·expired·cancelled·completed(리포트 없음)일 때 "다시 초대" 동작 → 초대 폼에 alias·email을 채우고 `previous_session_id`를 함께 보낸다. mock도 저장·"재응시" 표시까지 연결.
2. 채용 건 생성 화면: 선택 요소에 따른 타임라인(catalog.timeline·session_minutes)과 지원자 안내 문안(candidate_notice_template, 자리표시자 그대로) 미리보기. mock catalog.json의 비율을 실제 카탈로그(0.0833·0.9167)와 배치 설명(리뷰에 붙는 카드 제외)으로 맞춘다.
3. 확정 중 폴링: GET 실패 시 마지막 성공 데이터 유지, 폴링 계속(최대 재시도 뒤 "다시 불러오기" 버튼). POST 직후 첫 GET 실패도 같은 처리.
4. 카드 발생 시각은 계약의 `evidence[].context.card_at_t_min`을 읽는다(섹션 `card_t_min`은 있으면 우선, 없으면 근거 context에서). fixture도 context 값만으로 표시되는지 확인.
5. mock: reviewed 세션을 조회만으로 approving으로 되돌리지 않는다(초기 상태 보존).
6. mock: 동일 본문 재전달은 현재 상태(approving 또는 reviewed)를 돌려준다.
7. `mocks/admin.test.ts`를 `components/admin/` 아래로 옮긴다(소유권).

## 같이
- 관찰 없음 항목에도 담당자 메모를 관찰 안내 옆에 표시.
- 보고서 문구 정정: 요소 칩 분모는 judged, 기록 없음 수는 4−judged.

## 리포트 JSON 필드 확정(worker 산출 기준, contracts.md는 worker 라운드에서 반영)
- 항목: `items[].no_record_reason`(no_activity·classify_failed·event_not_fired·window_missed·not_applicable), 응답 시간 항목은 `items[].minutes`(화면의 response_minutes를 minutes로 바꾼다). 섹션에도 `no_record_reason`.
- 섹션: `aux_facts: string[]`, `out_of_window_messages: [{t_min, channel, quote}]`, 근거 `context {prev_persona_message, card_at_t_min}`, revision 근거 `summary`·`change_ratio`, doc_view 근거 `summary`.
- AI 활용: `ai_usage.evidence[].category ∈ delegate|context|verify`(worker가 규칙으로 붙임). 없으면 "기타".
fixture를 이 모양으로 맞춘다.
