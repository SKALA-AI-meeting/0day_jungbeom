# 리뷰 브리프: 개발 계획의 병렬성 (Codex, 개발 전)
역할: 읽기 전용 리뷰어. 소스·문서 수정, git 변경 명령, gh, 외부 게시 금지. 결과는 저장소 루트 `REVIEW-PLAN.md`(git에 올리지 않음)에 Markdown으로 저장하고 마지막 응답은 그 경로 한 줄만. 한국어.
대상: docs/plan.md(마일스톤·파도·소유권·규칙·MVP 제외), docs/dev-process.md, docs/handoff.md(다음 행동·Herdr 운영 규칙·브리프 템플릿), AGENTS.md. 참고: docs/common/contracts.md(트랙 간 공용 계약), docs/common/architecture.md 저장소 구조, docs/handoff/reviews/review-redesign-triage.md(방금 반영한 결정), docs/handoff/briefs/*(지금까지 브리프 형식), docs/handoff/reports/*의 "변경 요청"·"다른 트랙에 알릴 것" 절(병렬 작업에서 실제로 생긴 마찰).
질문: 에이전트 여러 개가 각자 worktree·탭에서 동시에 일하고 오케스트레이터가 합칠 때, 지금 계획이 충돌 없이 돌아가는가.
출력: 1) 반드시 고칠 것(병렬 착수 차단: 같은 파일을 두 트랙이 쓰는 곳, 의존이 순환하거나 숨은 곳, 병합 순서가 완료 기준과 안 맞는 곳, 완료 기준이 혼자 검증 불가능한 곳) 2) 고치면 좋은 것(트랙 크기 균형, 파도 수 줄이기, 브리프에 꼭 들어가야 할 정보) 3) 추천 파도 표(트랙·동시 pane·병합 순서·각 트랙이 시작 전 받아야 할 것) 4) 오케스트레이터 체크리스트(기동 전·완료 보고 확인·병합 전). 파일:줄과 한 줄 근거.
특히 볼 것:
- 재설계 기간 소유권(web-redesign이 web 전체, scenario-redesign이 scenarios·schema·api·business-mcp·rag 색인 키·worker·tests/fixtures)이 서로·그리고 남은 트랙(agent-session, agent-assistant, web-integrate, e2e-runner, web-polish, prompts, docs-final, docs-service)과 겹치는 파일이 있는가. `tests/conftest.py`·`services/api/tests/conftest.py`·`pyproject`·lockfile·`infra/`처럼 공용 파일을 누가 만지는가.
- web-redesign(mock)과 scenario-redesign이 병렬일 때 mock 데이터 형태와 contracts.md가 어긋나면 web-integrate에서 터진다. 계약 변경 흐름(트랙 → 오케스트레이터 → contracts)이 병렬 중에 작동하는가.
- agent-session은 scenario-redesign 산출(카탈로그·내부 API·도구)에 의존하는데 착수 시점과 "받아야 할 것"이 분명한가. agent-assistant·e2e-runner는 무엇을 기다리는가.
- docs-final·docs-service가 최종본 기준이면 언제 시작할 수 있는가. 스크린샷·실세션 기록 의존.
- 완료 기준이 "make test·lint"뿐인 트랙은 통합 전에 무엇을 더 증명해야 하는가. 최소 테스트 6건의 소유 트랙.
- Herdr 탭·pane·worktree 규칙과 `.env` 복사, 공용 postgres·rabbitmq 하나를 여러 worktree 테스트가 같이 쓸 때의 충돌(스키마 변경을 scenario-redesign이 하면 다른 worktree의 테스트가 깨짐).
- 리뷰 pane(Codex)·UI/UX 페르소나 리뷰·사용자 mock 확인이 어느 트랙의 어느 시점에 끼는지, 그 사이 다른 트랙이 멈추지 않는지.
