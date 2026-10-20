# 브리프: docs-share 트랙 (팀 공유 문서 2종)
역할: 팀원에게 공유할 문서 작성. worktree는 현재 폴더, 브랜치 track/docs-share. 커밋은 자기 브랜치에만, main 병합·push 금지. 코드·설계 문서(docs/common 등)는 수정하지 않는다. 산출물은 `docs/share/` 아래에만 둔다.

## 읽을 것
PRD.md(기획 정본), AGENTS.md, docs/README.md, docs/common/architecture.md, docs/common/scenario-model.md, docs/common/harness.md, docs/common/rubric.md, docs/common/contracts.md(개요만), docs/agent/design.md(그래프·State·페르소나 표), docs/worker-infra/design.md, docs/plan.md, docs/decisions.md, docs/assignment/evaluation.md, docs/assignment/reference-architecture.md, infra/docker-compose.yml, services/*/README.md. 현재 구현 상태는 docs/handoff.md 진행 표.
참고 이미지(아키텍처 표현 방식의 레퍼런스, 다른 팀의 B2B 입찰 플랫폼 그림): /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/reference-architecture.png — 박스·화살표·큐 토픽·DB 테이블·AI 서비스 배치와 오른쪽 설명 글머리 방식을 참고하되 내용은 Day Zero 것으로.

## 산출물 1: `docs/share/architecture.html`
외부 의존성 없는 단일 HTML(인라인 CSS·SVG). 팀원이 브라우저로 열어 5분 안에 구조를 이해하는 것이 목적. 구성:
1. 한 줄 소개와 평가 항목 대응 요약(Biz/아키텍처/Agent 설계·구현/MCP/Harness/인증/대기열)
2. **시스템 아키텍처 그림(인라인 SVG)**: 레퍼런스처럼 Next.js web → api(FastAPI 8000 공개 / 8001 내부, JWT·세션 Lock·스케줄러·LangGraph 에이전트 모듈) → business-mcp(9101)·rag-mcp(9102, BGE-M3) → PostgreSQL+pgvector(주요 테이블 묶음 표시), RabbitMQ(report.generate / report.approve / report.dlq) → report-worker(LangGraph interrupt 승인), OpenAI gpt-4o-mini, LangSmith. 화살표에 "produce/consume", "내부 API 호출", "검색" 같은 라벨. 오른쪽에 핵심 설계 포인트 글머리 4~6개.
3. 세션 흐름 타임라인(120분, 카드 배치: kickoff 0 / division 10 / 요소 카드 30·50·70·90 / review 90 / report_request 110, 중간 초안 60)
4. 에이전트 그래프(세션 그래프 전이 요약, observe→classify→rubric 규칙 산출, 사람 승인 interrupt)
5. 하네스 8요소 대응 표, 인증 표(관리자 JWT / 지원자 세션 JWT / 디브리핑 토큰 / 내부 토큰), 대기열·재시도·DLQ 표
6. 저장소 구조와 역할별 트랙·현재 진행 상태(handoff 진행 표 기준)
한국어, 서비스명 Day Zero. 인쇄해도 깨지지 않게.

## 산출물 2: 기획 보고서 `docs/share/plan-report.html` + PDF
`/deliver:report` 스킬을 호출해 PRD.md를 **보고서 형태**로 다시 쓴다(한 쪽 = 한 메시지, 결론형 제목). 흐름: 표지 → 한눈에 보는 결론 → 문제와 사용자 → 서비스 개요(지원자·담당자 시나리오) → 시나리오·요소 카드 → 평가표(규칙 산출 + 담당자 조정, AI는 판정하지 않음) → 동료 페르소나·하네스 → 아키텍처 요약(산출물 1의 그림 축약판) → MVP 범위·제외·리스크 → 일정과 현재 진행 → 부록(기능 ID 표). 수치는 PRD·docs에서 그대로. 스킬 절차(check 루프·render·PNG 눈 검토)를 끝까지 돈다. PDF는 `docs/share/plan-report.pdf`.

## 완료 보고
두 파일 경로, 스킬 check 결과(넘침 0·꼬리 줄 0), 참고한 문서 목록, PRD와 다르게 표현한 곳이 있으면 목록을 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/docs-share-report.md 에 저장. 커밋 메시지는 한국어 한 문장. 마지막 응답은 경로 한 줄.
