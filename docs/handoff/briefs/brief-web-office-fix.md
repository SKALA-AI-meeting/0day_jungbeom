# web-office 수정 라운드 (Codex 리뷰 반영)
리뷰 전문: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/review-web-office.md. 오케스트레이터 결정. 같은 브랜치에 커밋. 끝나면 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/web-office-report-2.md 에 수정 목록·검증 명령·결과 저장(worktree의 REVIEW.md 삭제). 마지막 응답은 경로 한 줄. 먼저 `git rebase main`(main에는 api-candidate·web-admin·docs가 이미 병합됨)을 하고 시작한다. 충돌이 나면 보고.

## 반드시
1. 저장 실패 보존: part-saver는 실패 시 최신 본문을 유지하고 "저장 실패, 다시 시도" 표시, 타이머 run에 catch. flush()는 성공 또는 명시적 권한 거부(403)까지 확인. dirty는 성공 뒤에만 해제.
2. 제출 실패 처리: flush·submit 실패면 오피스를 닫지 않고 원고 보존 + 오류·재시도. `session_ending`/`conflict`는 `/state`로 실제 종료를 확인한 뒤에만 종료 화면.
3. 재연결 경합: `/state` 조회 중 도착한 WS 프레임을 모았다가 스냅샷 적용 후 순서대로 재적용(메시지 id·revision 중복 제거). `/state` 실패 시 재시도.
4. 초기 notice 복원: 첫 스냅샷에서 notice 채널 메시지는 알림 띠에 복원(안 읽음 배지 제외와 분리).
5. 동료 파트 403: 저장 콜백에서 403이면 해당 파트를 서버 본문으로 되돌리고 "동료 담당이라 저장되지 않음" 안내, 예약된 디바운스 취소. mock도 분업 확정 뒤 동료 파트 PUT에 403.
6. 타이머: `ends_at` 기준으로 deadline 계산(remaining_seconds는 보조).
## 같이
- 파트별 저장 직렬화: 진행 중 PUT이 끝난 뒤 최신 본문 하나만 보냄.
- 디브리핑 `/debrief` 410 expired는 "기한(종료 후 7일)이 지났습니다, 담당자에게 문의" 안내로 구분.
- 재입장 `/resume`·`/state` 일시 장애는 제출 완료 안내가 아니라 연결 실패·다시 시도 안내.
- 기존 테스트에 단언 추가(새 테스트 파일 없이): 저장 실패 후 flush가 성공으로 끝나지 않음, 제출 전 PUT 완료 후 POST, 조회 중 프레임 보존, 초기 notice, 403 복구, ends_at 타이머.
## 결정(변경 요청 답)
State 파트 제목·virtual_company·session_id 추가는 M2(agent-min 이후 api 보강)로 넘김. 지금 방식 유지. contracts.md 보충은 main에 이미 반영돼 있으니 그 기준으로 재확인.
