# docs-share 트랙 완료 보고

브랜치 `track/docs-share` (worktree `Day-0_zaeho.worktrees/docs-share`). 커밋은 이 브랜치에만, push·병합 없음. 수정 파일은 `docs/share/` 아래 신규 3개뿐.

## 산출물

| 파일 | 내용 |
|---|---|
| `docs/share/architecture.html` | 외부 의존성 없는 단일 HTML(인라인 CSS·SVG). 1 평가 항목 대응표 / 2 시스템 아키텍처 SVG(web → api 8000·8001[JWT·SessionService·스케줄러·LangGraph 모듈] → business-mcp 9101·rag-mcp 9102 → PostgreSQL+pgvector 테이블 4묶음, RabbitMQ report.generate·approve·dlq → report-worker, OpenAI·LangSmith, compose 신뢰 경계 점선, 화살표 라벨 ①~⑧) + 핵심 설계 포인트 6개 + 번호별 처리 흐름 표 / 3 120분 타임라인(흐름 카드·요소 카드·관찰 창·01:05 공개) / 4 에이전트 그래프(phase 전이, observe→classify→rubric.evaluate→담당자 조정, 리포트 그래프 interrupt) / 5 하네스 8요소·인증 4토큰·큐 표 / 6 저장소 구조·트랙 진행(handoff 진행 표). 화면 폭 860px 이하 1단, 인쇄용 @media print(A4) |
| `docs/share/plan-report.html` | `/deliver:report` 템플릿 기반 14쪽 기획 보고서(표지 → 한눈에 → 문제 → 사용자·시점 → 서비스 개요 → 공통 시나리오 → 요소 카드 → 평가표 → 페르소나·하네스 → 아키텍처 요약 → MVP 범위·리스크 → 일정·진행 → 부록 기능 ID 2쪽) |
| `docs/share/plan-report.pdf` | 위 HTML을 `report_tool.py render`로 만든 PDF(14쪽) |

## 스킬 검사 결과

- `report_tool.py check --breaks`: **넘침 0건, 짧은 꼬리 줄 0건, 결과 통과**(14쪽, 최대 사용 높이 239/281mm).
- 줄바꿈 지점 66곳을 전부 읽고 갈라진 묶음(평가 방식, 팀장이 보는 곳, 범위·일정·분담, 검토 완료, 페르소나 성향 4개, 트랙 이름 등)을 `nw`로 묶거나 문장을 다시 씀.
- `render`로 PDF와 쪽별 PNG를 만들어 14쪽 전부 눈으로 검토. 타임라인의 인터뷰 요약 공개 표시가 55분 위치에 잘못 찍혀 있던 것을 65분으로 고침.
- PDF 텍스트를 뽑아 PRD 수치(94.1%, 10.7%, 0.54/0.31, 60.6%, 58.9%, 51.5%, 34.9%/33.4%, 22%, $0.5, 9/14, 파일럿 80%·100%) 대조 일치.
- architecture.html은 스킬 대상이 아니라 헤드리스 Chrome 스크린샷(1240px)과 인쇄 PDF로 눈 검토. 상자 밖으로 넘치는 SVG 글자 3곳, 인쇄 시 표 오른쪽 잘림을 고침.

## 참고한 문서

PRD.md, AGENTS.md, docs/README.md, docs/common/architecture.md, docs/common/scenario-model.md, docs/common/harness.md, docs/common/rubric.md, docs/common/contracts.md(공통·인증·WS·MCP 도구·큐 절), docs/common/data-model.md, docs/agent/design.md, docs/api/design.md(구조·스케줄러), docs/worker-infra/design.md, docs/plan.md, docs/decisions.md, docs/assignment/evaluation.md, docs/assignment/reference-architecture.md, docs/handoff.md(진행 표), infra/docker-compose.yml, services/*/README.md, scenarios/catalog.yaml(persona·rubric 항목 문구), 참고 이미지 reference-architecture.png.

## PRD와 다르게 표현한 곳

1. **에이전트 그래프**: PRD 부록 A.3의 초안 노드(route·kickoff·negotiate·check_agreement·work·observe·inject·review·submit·enqueue_report) 대신 `docs/agent/design.md`의 phase 전이(kickoff→negotiate→work→review→submit→done)와 노드를 그렸다. PRD 스스로 부록을 "참고용, 바꿔도 됨"으로 둔다.
2. **구성도**: PRD A.2의 report-worker 설명 "규칙 지표 + LLM 요약" 대신 설계 문서 기준(리포트 그래프 collect→draft→approval[interrupt]→finalize, rubric.evaluate는 규칙)으로 표현. 규칙 지표 계산은 observe(api 안)에 있다.
3. **지원자 상태 수**: PRD 7.2 표는 6개 상태, F-03은 "확정 중"을 포함한 7개. 보고서·아키텍처 문서는 F-03과 data-model 기준 7개로 썼다.
4. **MVP 제외 기능**: PRD는 F-05·F-06(P1), F-07(선택), F-25(P1, 예외 흐름에만 MVP 제외)로 등급만 적는다. 보고서 부록과 범위 표에는 `docs/plan.md`·decisions.md의 MVP 제외 결정에 따라 "제외"를 함께 표시했다.
5. **요소 카드 배치 규칙 문구**: PRD 6.4 "L×1/4부터 L×3/4까지 균등 배치"를 scenario-model.md 공식(존중을 뺀 카드는 L/4 + i·(L/2)/n, 존중은 리뷰와 같은 3L/4)에 맞춰 "L/4부터 L/2 길이 구간에 균등, 존중은 3L/4"로 썼다. 120분·4개 결과(30·50·70·90)는 PRD와 같다.
6. **세션 원가**: PRD 14장은 "LLM 비용 0.5달러 이하, 10장"으로 적혀 있다. "10장"의 뜻이 불분명해 보고서에는 "$0.5 이하, 호출 350회 가정(A.1)"만 옮겼다.
7. **요약·압축**: 문제 근거 표, 이해관계자 표, 리스크 표(9행 → 6행: 지원자 고지·AI 어시스턴트 영향·유사 서비스 등장 행 생략), 시장·경쟁(12장)·기대 임팩트(13장)·비즈니스 모델 표(14장)는 쪽 흐름에 없어 넣지 않고 가격 가설 한 줄만 일정 쪽에 남겼다.
8. **진행 상태**: 병합 5 / 진행 중 4 / 대기 5는 handoff 진행 표(2026-10-20, d8adeca) 기준이며, 대기 5에는 W4 docs-final을 포함하고 fix-*는 세지 않았다.
