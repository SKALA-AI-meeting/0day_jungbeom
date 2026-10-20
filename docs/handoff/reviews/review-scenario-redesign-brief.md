# 리뷰 브리프: scenario-redesign 트랙 (P1, 관문별 반복)
역할: 읽기 전용 리뷰어. 소스 파일 수정, git 변경 명령, gh, 외부 게시 금지. 결과는 worktree 안 `/Users/zaehorang/Projects/Day-0_zaeho.worktrees/scenario-redesign/REVIEW.md`(git에 올리지 않음)에 Markdown으로 저장하고, 마지막 응답은 그 경로 한 줄만. 관문마다 같은 파일을 "## 관문 N" 절로 덧붙인다.
출력: 1) 반드시 고칠 것(병합 차단) 2) 고치면 좋은 것 3) 보고서의 "남은 문제"·"변경 요청" 쟁점별 의견 4) 다른 트랙 주의사항. 각 항목에 파일:줄과 한 줄 근거. 한국어. 리뷰 기준(docs/dev-process.md): 계약(`docs/common/contracts.md`·`scenario-model.md`·`rubric.md`·`data-model.md`) 준수, 완료 기준 충족, 소유권 밖 파일 수정 없음(`docs/common/`·`apps/web/` 금지, 브리프의 허용 목록 참조), 테스트가 happy path 범위를 넘지 않음, MVP 과잉, 주석이 "역할·알아야 할 로직·예외 의도" 수준인지(줄 단위 설명·주석 없음 둘 다 지적).
대상: 현재 worktree(브랜치 track/scenario-redesign)의 `git diff main...HEAD`. 개발 브리프 `docs/handoff/briefs/brief-scenario-redesign.md`, 개발자 보고서 `docs/handoff/reports/scenario-redesign-report.md`(먼저 읽는다).
기준 문서: AGENTS.md, docs/plan.md(scenario-redesign 행·6건 배정), docs/common/*.md, docs/api/design.md, docs/mcp/design.md, docs/worker-infra/design.md, docs/agent/design.md, tests/fixtures/contracts/*.json, docs/handoff/reviews/review-redesign-triage.md.

## 관문 1(미션·스키마)에서 특히 볼 것
cards.yaml의 카드 7장 시각·창·레이블·aux·근거 타입·항목 id가 scenario-model.md·rubric.md와 한 글자도 다르지 않은지; fixed_opinions·선점 금지·팀장 DM 규칙이 triage 결정과 같은지; 적응성 카드가 "자료가 살아남는 변경"인지; schema.sql이 data-model.md의 테이블·컬럼·키(observations 카드 단위 키, documents 소유·버전·공유·열기·revisions, tasks null 시작)와 일치하고 옛 테이블이 남지 않았는지; version.py 해시 범위; 조립 테스트가 수치를 실제로 검증하는지(상수 복사 아님); 대본 7개가 e2e 6건을 덮는지; 호칭 "리드"·"평가"가 프롬프트·문서에 남지 않았는지.
