# 리뷰 브리프: business-mcp 트랙 (W1)
역할: 읽기 전용 리뷰어. 파일 수정, git 변경 명령, gh, 외부 게시 금지. 결과는 마지막 응답에 Markdown으로 그대로 출력한다(파일 저장 불필요).
대상: 현재 worktree(브랜치 track/business-mcp)의 `git diff main..HEAD`. 개발자 보고서: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/business-mcp-report.md (먼저 읽는다).
기준 문서: AGENTS.md, docs/plan.md(소유권·병렬 규칙), docs/dev-process.md, docs/common/contracts.md(MCP 도구 표·오류 코드·내부 API), docs/mcp/design.md, docs/common/harness.md.
리뷰 기준: 계약 준수(도구 10개 이름·입출력·오류 코드), 완료 기준 충족, 소유권 밖 파일 수정 없음, 테스트가 happy path 범위를 넘지 않음, 멱등 키·meta 그대로 전달, 재시도·타임아웃 설계 일치, 보고서의 "구현 메모"에서 계약에 없는 선택(410→conflict, 423→not_released, 그 외 4xx→invalid_input)의 타당성, MVP 과잉.
출력: 1) 반드시 고칠 것(병합 차단) 2) 고치면 좋은 것 3) 보고서 쟁점별 의견 4) 다른 트랙 주의사항. 각 항목에 파일:줄과 한 줄 근거. 한국어.
