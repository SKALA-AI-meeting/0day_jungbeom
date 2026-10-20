# 브리프: worker 트랙 (W2)
역할: report-worker 개발.
## 공통 규칙
- worktree는 현재 폴더, 브랜치 track/<트랙>. 커밋은 자기 브랜치에만, main 병합·push 금지.
- 읽을 것: AGENTS.md, docs/plan.md(자기 트랙 행·파일 소유권·병렬 규칙), docs/dev-process.md, docs/common/contracts.md, docs/decisions.md의 2026-10-20 절 전부(foundation·api-admin·prompts 리뷰 반영).
- 앞선 트랙 보고서의 "다른 트랙에 알릴 것"에서 자기 트랙 항목을 읽는다: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report.md, foundation-report-2.md, api-admin-report.md, api-admin-report-2.md, api-candidate-report.md, business-mcp-report.md, rag-mcp-report.md, prompts-report.md, prompts-report-2.md.
- 소유권 밖 파일은 수정하지 않는다. 바꿔야 하면 보고서에 "변경 요청"으로 적고 가능한 범위에서 계속한다.
- TDD, happy path 중심. 완료 기준 한 줄당 테스트 하나. LLM은 mock(FakeLLM), 실제 호출은 live 마커. 통합 스택은 한 번에 하나이므로 `make up`·api 상시 기동 금지. 공용 postgres·rabbitmq는 main에서 `make infra-up`으로 떠 있음(localhost:5432, 5672).
- `infra/.env` 키 값 출력·복사 금지. 커밋 메시지는 한국어 한 문장 + 본문에 테스트 명령.
- 끝나면 완료 기준 각 줄의 명령·결과, 수정 파일, 남은 문제, 변경 요청, 다른 트랙에 알릴 것을 Markdown으로 저장. 마지막 응답은 그 파일 경로 한 줄.
## 추가로 읽을 것
docs/worker-infra/design.md 전체, docs/common/rubric.md(규칙 문법·지표·기록 없음 사유), docs/common/contracts.md(큐 메시지, Report JSON, 내부 API report/draft·final·report_failed), docs/common/harness.md, scenarios/catalog.yaml(rubric·label_texts·rubric_rules), services/api/app/queue.py(토폴로지·attempt=1), services/api/app/routers/internal.py(draft/final 해시 규칙·오류 코드), services/report-worker/ 골격, tests/fixtures/contracts/report.json.
## 범위
`services/report-worker/` 전체. LangGraph `collect → draft → approval[interrupt] → finalize`, PostgresSaver(thread report:{session_id}), 소비자 report.generate·report.approve·report.dlq(prefetch 1, manual ack, 순서: 체크포인트 → draft 저장 → ack), 재시도 백오프 5·15·45초·attempt≥3 → DLQ, `rubric.evaluate` 순수 함수(조건 문법 label_in/metric/all/only_if, 1/0/null + 사유), 리포트 조립(산출물·요소별 섹션·평가표·AI 활용 요약은 FakeLLM), 금지어·타 세션 근거 id 제거, final은 저장된 draft와 같은 정규화 해시, usage 기록(계약에 필드가 없으면 변경 요청). heartbeat는 기존 루프와 함께.
내부 API는 httpx MockTransport로 mock(api-admin 라우터가 main에 있으니 응답 형식은 거기서 확인). RabbitMQ는 공용 인스턴스에 테스트 전용 큐 접두사나 임시 vhost를 써서 다른 트랙과 겹치지 않게 하고 끝나면 정리.
## 완료 기준 (docs/worker-infra/design.md)
draft 멈춤 → approve 재개 → final(동일 해시), 중복 approve 멱등, final 후 ack 전 재전달 200; usage 기록; 금지어·타 세션 근거 제거 테스트; rubric.evaluate 단위 테스트(카드별 픽스처, 기록 없음 포함); api 다운 시 3회 재시도 후 DLQ → 복구 후 report_failed; `uv run pytest`, 루트 `make test`·`make lint`. compose 전체 기동은 하지 않는다(M3).
## 보고서 경로
/private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/worker-report.md
