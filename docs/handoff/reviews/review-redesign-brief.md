# 리뷰 브리프: 재설계 설계 리뷰 (Codex, 개발 전)
역할: 읽기 전용 리뷰어. 소스 수정, git 변경 명령, gh, 외부 게시 금지. 결과는 저장소 루트 `REVIEW.md`(git에 올리지 않음)에 Markdown으로 저장하고 마지막 응답은 그 경로 한 줄만. 한국어.
대상: 2026-10-20 재설계가 반영된 기획·계획·설계 문서 전체. 코드는 아직 옛 설계라 보지 않는다(코드와 문서가 다른 것은 지적 대상이 아님).
읽는 순서: AGENTS.md → PRD.md → docs/prd-change-proposals.md(재설계 절) → docs/frontend/design-direction.md → docs/frontend/design-system.md → docs/common/{architecture,scenario-model,rubric,contracts,data-model,harness,testing}.md → docs/{agent,api,mcp,worker-infra,frontend}/design.md → docs/plan.md → docs/decisions.md → docs/dev-process.md.
출력: 1) 반드시 고칠 것(개발 시작 차단: 문서 간 모순, 계약 누락, 관찰이 불가능한 평가 항목, 공정성 깨짐) 2) 고치면 좋은 것 3) MVP 과잉·부족 4) 개발 순서·소유권의 위험. 파일:줄과 한 줄 근거.
특히 볼 것:
- 요소 5개·카드 7장이 PRD 5.2/5.3/6.4, scenario-model.md, rubric.md, agent/design.md에서 같은 id·시점·항목으로 적혀 있는가. 배치 공식(L/4 + i·(L/2)/N, 책임감 지연 L/12)이 모든 문서에서 같은 수치(120분: 10·30·45·60·70·75·90·110)인가.
- 평가표 항목(요소당 4개)이 "실력이 아닌 태도"만 재는가, 각 항목의 when 조건이 rubric.md 문법으로 계산 가능한가, 기록 원천(메시지·공유·열람·task_events·honesty_facts)이 contracts·data-model에 있는가.
- 문서 주고받기 모델: documents/versions/shares/opens/final_document·보드 task_events가 contracts.md REST/WS, data-model, api/design, mcp 도구(send_document, get_shared_documents), worker collect, frontend 화면 규칙에서 서로 맞는가. 세션 상태 reporting(제출 → 보고 요청 → 5분)이 전이표·스케줄러·화면에 다 있는가.
- 같은 채용 건 공정성: 반대 의견 카드 내용 고정, 주담당 문서 미공유 시 대체 규칙, 미선택 요소 처리, 미션 단위 고정이 지켜지는가.
- 선점 금지 6건과 팀장 DM 규칙(과제 질문 OK, 정답·판단 요청은 돌림)이 페르소나·guard·카드 brief와 충돌하지 않는가.
- 하네스 8요소·MCP 2개·큐·인증 등 평가표 필수 요소가 재설계 뒤에도 빠짐없이 남는가(docs/assignment/evaluation.md).
- plan.md의 트랙 분할(redesign-docs → web-redesign ∥ scenario-redesign → agent-session…)과 소유권이 충돌 없이 병렬 가능한가, 완료 기준이 검증 가능한가.
