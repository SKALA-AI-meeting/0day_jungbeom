# 리뷰 브리프: foundation 트랙 (W0)

역할: 읽기 전용 리뷰어. 파일 수정, git 명령(commit/push/checkout), gh, 외부 게시·코멘트 금지. 결과는 아래 경로에 파일로만 남긴다.

대상: 현재 worktree(브랜치 track/foundation)의 커밋 7512022..HEAD (3개). `git diff 7512022..HEAD`.
개발자 보고서: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report.md (먼저 읽는다)

읽을 기준 문서: AGENTS.md, docs/plan.md(M0.5 범위, 파일 소유권 foundation 행, 병렬 작업 규칙), docs/dev-process.md, docs/common/contracts.md, docs/common/data-model.md, docs/common/scenario-model.md, docs/api/design.md, infra/db/schema.sql, scenarios/catalog.yaml.

리뷰 기준(docs/dev-process.md): 계약 준수, 완료 기준 충족, 소유권 밖 파일 수정 없음, 테스트가 happy path 범위를 넘지 않음. 추가로:
- schema.sql과 models/ 불일치, 계약(contracts.md)의 상태 전이·오류 코드·WS 프레임과 SessionService·hub·messages 서비스의 불일치
- auth(JWT 역할 분리, X-Internal-Token, 초대 토큰 해시), 큐(publisher confirm 뒤 enqueued_at, DLX)의 설계 어긋남
- 보고서의 "남은 문제"·"어긋난 점" 14건 각각에 대해 동의/반대와 권장 처리(누가·언제)
- 다른 트랙이 이 기반 위에서 막힐 지점
- MVP 과잉(필요 없는 추상화·테스트)

출력 형식: Markdown. 섹션 = 1) 반드시 고칠 것(병합 차단) 2) 고치면 좋은 것 3) 보고서 쟁점별 의견 표 4) 다른 트랙 주의사항. 각 항목에 파일:줄과 한 줄 근거. 한국어.
저장 경로: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/review-foundation.md
마지막 응답은 그 파일 경로 한 줄만.
