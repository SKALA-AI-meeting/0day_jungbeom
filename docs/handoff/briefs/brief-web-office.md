# 브리프: web-office 트랙 (W2)
역할: 지원자 화면·가상 오피스 개발.
## 공통 규칙
- worktree는 현재 폴더, 브랜치 track/<트랙>. 커밋은 자기 브랜치에만, main 병합·push 금지.
- 읽을 것: AGENTS.md, docs/plan.md(자기 트랙 행·파일 소유권·병렬 규칙), docs/dev-process.md, docs/common/contracts.md, docs/decisions.md의 2026-10-20 절 전부(foundation·api-admin·prompts 리뷰 반영).
- 앞선 트랙 보고서의 "다른 트랙에 알릴 것"에서 자기 트랙 항목을 읽는다: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report.md, foundation-report-2.md, api-admin-report.md, api-admin-report-2.md, api-candidate-report.md, business-mcp-report.md, rag-mcp-report.md, prompts-report.md, prompts-report-2.md.
- 소유권 밖 파일은 수정하지 않는다. 바꿔야 하면 보고서에 "변경 요청"으로 적고 가능한 범위에서 계속한다.
- TDD, happy path 중심. 완료 기준 한 줄당 테스트 하나. LLM은 mock(FakeLLM), 실제 호출은 live 마커. 통합 스택은 한 번에 하나이므로 `make up`·api 상시 기동 금지. 공용 postgres·rabbitmq는 main에서 `make infra-up`으로 떠 있음(localhost:5432, 5672).
- `infra/.env` 키 값 출력·복사 금지. 커밋 메시지는 한국어 한 문장 + 본문에 테스트 명령.
- 끝나면 완료 기준 각 줄의 명령·결과, 수정 파일, 남은 문제, 변경 요청, 다른 트랙에 알릴 것을 Markdown으로 저장. 마지막 응답은 그 파일 경로 한 줄.
## 추가로 읽을 것
docs/frontend/design.md(가상 오피스 레이아웃·재연결·완료 기준), PRD.md 7장, docs/common/contracts.md(/s·/sessions·WS 프레임·close code 4401/4403/4000·오류 프레임·디브리핑), apps/web/(foundation 골격: components/ui props, lib/api.ts, mocks/README.md·index.ts·types.ts·ws-replay.ts, fixtures/office/state.json, fixtures/ws_events.json), services/api/app/routers/{candidate,ws}.py(실제 응답·프레임), tests/fixtures/contracts/{state,ws_events}.json.
## 범위
`apps/web/app/s/`, `components/office/`, `lib/ws.ts`, `mocks/office.ts`, `mocks/fixtures/office/`. 흐름: 링크 입장(만료·취소·완료 안내, 알 수 없는 토큰 404) → 안내·동의 → 대기 → 오피스(상단 회사명·타이머 mm:ss·제출, 좌 채널 목록+안 읽음, 중 메시지+입력(client_msg_id, ack 확정, agent.progress로 "입력 중…"), 우 탭 4개: 기획안 문서(파트 5 textarea, 1초 디바운스 PUT, 동료 파트 읽기 전용 안내), 태스크 보드, 회사 문서(잠금·document.released), AI 어시스턴트(POST 대기 표시; API 미구현이면 mock만)) → 제출 확인 창 → 디브리핑(실패 세션은 중단 안내만). notice 채널은 상단 알림 띠. 재연결: 3초 후 재접속 + /state 전체 갱신, 4401이면 /resume 후 재연결, session.replaced(4000)는 "다른 창에서 접속" 안내. "평가 중"이 드러나지 않는 업무 도구 톤. `components/ui/` 내부·props 수정 금지.
## 완료 기준 (docs/frontend/design.md 지원자 줄)
만료·완료 링크 안내, 동의 전 시작 불가, 오피스 4탭, 타이머, 진행 표시, 제출, 디브리핑, 재연결 후 상태 복원이 mock(ws-replay)으로 동작. vitest 화면 단계당 1개(5개 안팎), `pnpm lint`, `pnpm test`, 루트 `make lint`·`make test`. 보고서에 `NEXT_PUBLIC_MOCK=1 pnpm dev`로 확인한 단계 목록.
## 보고서 경로
/private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/web-office-report.md
