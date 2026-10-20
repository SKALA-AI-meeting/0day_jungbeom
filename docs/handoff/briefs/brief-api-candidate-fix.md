# api-candidate 수정 라운드 (Codex 리뷰 반영)
리뷰 전문: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/review-api-candidate.md. 오케스트레이터 결정. 같은 브랜치에 커밋. 끝나면 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/api-candidate-report-2.md 에 수정 목록·검증 명령·결과 저장(worktree의 REVIEW.md 삭제). 마지막 응답은 경로 한 줄.
이번 라운드에 한해 foundation 파일 `app/services/session.py`, `app/auth.py`, `app/services/messages.py`의 아래 지정 변경을 허용한다. 그 밖의 foundation 파일은 그대로.

## 반드시
1. 스케줄러 순서: 세션별로 미완료 카드(fired/started 복구·재시도)와 새 pending을 `due_at` 순으로 처리하고, 같은 세션의 앞 카드가 done/failed/skipped가 아니면 뒤 카드를 디스패치하지 않는다(세션별 직렬). 재시작 테스트에 "후속 카드가 함께 due인 경우 앞 카드가 먼저" 단언을 합친다.
2. 지원자 문서 PUT 권한: 분업 확정 뒤 `colleague` 단독 파트는 403(forbidden), candidate·both만 허용. 분업 전에는 모든 파트 허용(리드가 초안을 잡을 수 있음). 기존 엔드포인트 테스트에 403 한 줄.
3. 지원자 문서 PUT을 세션 Lock 안에서 수행(지원자 진입점만, 내부 라우터는 Lock을 잡지 않음). Lock 안에서 in_progress·submitted_at 재확인 → 409 session_ending.
4. 디브리핑 기한: 종료 시각(submitted_at, 없으면 ends_at, failed면 실패 시각) + 7일로 고정해 JWT exp를 그 시각으로 발급(`auth.py`에 exp 인자 허용). GET /s/{token}·debrief 조회에서도 같은 기한을 적용(지나면 410 expired).
5. Idempotency-Key: 오케스트레이터가 계약에서 제거하기로 결정(api-admin 라운드에서 contracts.md 수정 중). 이 트랙은 아무것도 하지 않는다.
6. `messages.py` 접수 함수: submitted_at 검사를 status 검사보다 먼저 → completed/ending 세션의 message.send는 `session_ending`. WS 테스트에 제출 후 오류 프레임 확인 한 줄.
7. 카드 3회 실패의 failed 기록과 `SessionService.fail`을 같은 트랜잭션으로. 추가로 재시작 시 "failed 필수 카드가 있는 in_progress 세션"을 fail로 수렴시키는 조회를 `_retry`에 넣는다.

## 같이
- `sync_tasks` 제거(tasks 생성은 api-admin의 내부 division PUT이 담당하기로 확정). 테스트 준비가 필요하면 테스트 안에서 직접 tasks 행을 만든다.
- `SessionService.start()`(session.py): `releases_at_start` 문서의 released_at을 시작 트랜잭션에서 바로 기록. 스케줄러 releases는 released_at이 있는 행을 건너뜀(이미 그럴 것).
- 실시간 스크립트 `realtime_six_minutes.py`: 9건 done·오차 ≤10초·completed·발행 1회를 assert하고 실패 시 exit 1. 재실행 결과를 보고서에.
- `infra/.env.example`의 JWT_SECRET 줄에 "32바이트 이상" 주석(값은 건드리지 않음).

## 문서 동기화 (이번만 허용)
- `docs/common/contracts.md`: WS close code 4401(→ /resume 후 재연결)·4403·4000, 오류 프레임 `{"type":"error","payload":{code,message}}`, 알 수 없는 초대 토큰 404 not_found, 세션 실패 디브리핑 형태(events [], persona_note null, scoring_notice=중단 안내, failed_stage), 디브리핑 기한 = 종료 +7일, 지원자 문서 PUT 권한 규칙.
- `docs/api/design.md`: estimate_reuse "순수 함수는 최적 revision 반환, 저장은 호출×파트별 최대값(revision 컬럼 없음)"; 스케줄러 표에 세션별 due_at 직렬 처리.
- `docs/decisions.md` 맨 아래 "2026-10-20 api-candidate 리뷰 반영" 절: 1·2·3·4·7, 시작 시 즉시 공개, assistant_reuse revision 컬럼 보류.
주의: api-admin 트랙도 지금 contracts.md·decisions.md를 고치고 있다. 병합 때 오케스트레이터가 rebase 충돌을 처리하므로 해당 절은 새 절로만 추가하고 기존 문장은 최소로 건드린다.
