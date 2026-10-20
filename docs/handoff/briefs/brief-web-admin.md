# 브리프: web-admin 트랙 (W2)
역할: 관리자 화면 개발.
## 공통 규칙
- worktree는 현재 폴더, 브랜치 track/<트랙>. 커밋은 자기 브랜치에만, main 병합·push 금지.
- 읽을 것: AGENTS.md, docs/plan.md(자기 트랙 행·파일 소유권·병렬 규칙), docs/dev-process.md, docs/common/contracts.md, docs/decisions.md의 2026-10-20 절 전부(foundation·api-admin·prompts 리뷰 반영).
- 앞선 트랙 보고서의 "다른 트랙에 알릴 것"에서 자기 트랙 항목을 읽는다: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report.md, foundation-report-2.md, api-admin-report.md, api-admin-report-2.md, api-candidate-report.md, business-mcp-report.md, rag-mcp-report.md, prompts-report.md, prompts-report-2.md.
- 소유권 밖 파일은 수정하지 않는다. 바꿔야 하면 보고서에 "변경 요청"으로 적고 가능한 범위에서 계속한다.
- TDD, happy path 중심. 완료 기준 한 줄당 테스트 하나. LLM은 mock(FakeLLM), 실제 호출은 live 마커. 통합 스택은 한 번에 하나이므로 `make up`·api 상시 기동 금지. 공용 postgres·rabbitmq는 main에서 `make infra-up`으로 떠 있음(localhost:5432, 5672).
- `infra/.env` 키 값 출력·복사 금지. 커밋 메시지는 한국어 한 문장 + 본문에 테스트 명령.
- 끝나면 완료 기준 각 줄의 명령·결과, 수정 파일, 남은 문제, 변경 요청, 다른 트랙에 알릴 것을 Markdown으로 저장. 마지막 응답은 그 파일 경로 한 줄.
## 추가로 읽을 것
docs/frontend/design.md(경로 표·관리자 리포트 화면·완료 기준), docs/common/contracts.md(/admin 전부, Report JSON, 오류 코드·우선순위), docs/common/rubric.md, apps/web/(foundation 골격: components/ui props, lib/api.ts, mocks/README.md·index.ts·types.ts, globals.css 토큰), services/api/app/routers/admin.py(실제 응답 형태), tests/fixtures/contracts/report.json.
## 범위
`apps/web/app/admin/`, `components/admin/`, `mocks/admin.ts`, `mocks/fixtures/admin/`. 화면 5개: 로그인·가입, 채용 건 목록, 채용 건 생성(요소 체크 1~4개, 평가표 항목 미리보기), 채용 건 상세(지원자 목록 7상태 배지·점수 칩 by_element·초대 폼·링크 복사·세션 취소), 리포트(단계 배지, 합계, 헤더 문구, ①산출물 ②요소별 카드+평가표 항목 조정 토글·메모 필수 ③AI 활용, 검토 완료 → 확정 중 폴링 → reviewed 이력). `components/ui/` 내부와 props는 수정 금지. mock은 `NEXT_PUBLIC_MOCK=1`로 전 화면이 돌아야 한다. 합격·등급·순위 UI 없음.
## 완료 기준 (docs/frontend/design.md 관리자 줄)
가입→생성(요소 0·5개 거부)→초대(링크 복사)→목록 상태 7종·합계→리포트 draft(산출물·평가표)→조정(메모 필수, already_reviewed·memo_required 오류 표시)→검토 완료→reviewed 이력이 mock으로 동작. vitest로 화면당 렌더 테스트 1개(총 5개 안팎), `pnpm lint`, `pnpm test`, 루트 `make lint`·`make test`. 보고서에 `NEXT_PUBLIC_MOCK=1 pnpm dev`로 확인한 화면 목록.
## 보고서 경로
/private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/web-admin-report.md
