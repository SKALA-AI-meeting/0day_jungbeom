# api-admin 수정 라운드 (Codex 리뷰 반영)
리뷰 전문: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/review-api-admin.md. 아래는 오케스트레이터 결정. 같은 브랜치에 커밋. 끝나면 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/api-admin-report-2.md 에 수정 목록·검증 명령·결과 저장(worktree의 REVIEW.md 삭제). 마지막 응답은 경로 한 줄.

## 반드시
- B1: since_t_min은 Python에서 started_at + timedelta(minutes=…)로 계산해 비교. 소수 분 정상 경로 1개를 기존 메시지 테스트에 추가.
- B2: current_element는 "가장 최근에 fired/done된 **요소 카드**" 기준(흐름 카드·texture는 창을 닫지 않음). 마지막 요소 창은 세션 종료(제출)까지. respect→report_request 뒤에도 respect가 나오는 경로 1개를 기존 테스트에 합친다.
- B3 결정(계약 변경): MVP에서는 `Idempotency-Key` 헤더를 계약에서 **뺀다**. 멱등은 도메인 규칙(세션 전이·내부 저장 키·리뷰 본문 비교)으로만 보장하고, 화면은 생성 POST를 자동 재시도하지 않는다. contracts.md 공통 항목을 그렇게 고치고 decisions.md에 기록.
- B4: 같은 parts·decided_by 재요청은 저장된 division 그대로 반환, decided_at 유지, 브로드캐스트 생략. 테스트 한 줄 합치기.
- B5(이번만 foundation 파일 수정 허용): `app/main.py`의 공통 `_base`에 RequestValidationError 핸들러 추가 → 422 `{"error":{"code":"invalid_input","message":...}}`. 두 앱 공통.
- B6: 내부 문서 PUT·task PUT·division PUT은 세션이 in_progress일 때만(submitted_at 기록 여부와 무관). 이미 저장된 run_id 재전달은 기존 결과 반환(멱등 유지). 종료 뒤 새 쓰기 거부 경로 1개를 기존 권한 테스트에 합친다.

## 같이
- 내부 메시지 GET/PUT 응답은 `meta`(classification 포함)를 포함한다(내부 API 전용, 공개 API는 제외). contracts.md 내부 표에 한 줄.
- final 재전달은 세션 행 FOR UPDATE 안에서 상태 재조회 → reviewed_at 안정.
- 리뷰 오류 우선순위: already_reviewed(409) → memo_required/invalid_item/duplicate_item(400). contracts.md에 명시.
- tasks 생성 담당은 **api-admin 내부 division PUT로 확정**(division+tasks 한 트랜잭션). api-candidate의 sync_tasks는 그쪽 수정 라운드에서 제거시킨다. decisions.md에 기록(기존 "api-candidate" 결정 정정).

## 문서 동기화 (이번만 수정 허용)
- `docs/common/contracts.md`: /admin/catalog 필드 출처(situation_public=카드 situation, pilot_value 기본 false, candidate_notice_template 자리표시자), 리포트 `rubric.elements[].items[].adjusted`와 `review`·`history` 구조, division 422 `invalid_division`, `duplicate_item`(400), 테스트 세션 token=초대 토큰 원문, 가입 409 conflict·로그인 401, 위 B3·메시지 meta·오류 우선순위.
- `docs/common/data-model.md`: "검토 완료 시"를 "리뷰 제출(approving 전이) 트랜잭션"으로.
- `docs/decisions.md` 맨 아래 "2026-10-20 api-admin 리뷰 반영" 절: B2·B3·B6·tasks 담당 정정·오류 우선순위.

## 하지 않을 것
초대 토큰 복원, 공개 API의 meta 노출, 라우터별 중복 핸들러. 키 값 출력 금지.
