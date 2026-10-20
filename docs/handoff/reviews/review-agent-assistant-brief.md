# 리뷰 브리프: agent-assistant 트랙 (P2)
역할: 읽기 전용 리뷰어. 소스 수정·git 변경·외부 게시 금지. 결과는 `/Users/zaehorang/Projects/Day-0_zaeho.worktrees/agent-assistant/REVIEW.md`(git에 안 올림)에 Markdown, 마지막 응답은 경로 한 줄.
출력: 1) 반드시 고칠 것 2) 고치면 좋은 것 3) 보고서 "남은 문제"·"변경 요청" 의견 4) 다른 트랙(agent-session·web-integrate·e2e-runner) 주의사항. 파일:줄·한 줄 근거, 한국어.
기준: `docs/handoff/briefs/brief-agent-assistant.md`(허용 파일: app/agent/assistant/, tests/test_assistant*.py, context.py 훅 한 곳; llm·guard·mcp_client는 import만), `docs/agent/design.md` 어시스턴트 그래프·컨텍스트 허용 목록·페르소나 표, `docs/common/contracts.md`(assistant 경로·agent.progress·assistant_calls·rag 허용 도구), `docs/common/harness.md`(Guardrails·Recovery), `scenarios/missions/planning/prompts/{assistant.md,common_rules.md,guard_patterns.yaml,fixtures/grounding.yaml}`, 보고서 `docs/handoff/reports/agent-assistant-report.md`(먼저 읽기).
특히: 미공개 문서 본문이 어떤 경로로도 LLM 입력에 들어가지 않는지(get_document 호출 시 응답 본문 처리 포함), cited_docs가 검색 결과 밖을 포함하지 못하는지, 점수·합격·연출 언급 guard, 재시도 2회·폴백, 체크포인터 thread 분리와 setup의 CONCURRENTLY 교착 가능성, 60회 한도가 api에만 있는지(중복 저장 없음), 응답 600자·출처 줄 규칙, 허용 밖 파일 수정 없음, 테스트가 happy path 범위인지, 주석 수준. 실행: `cd services/api && uv run pytest -q`(격리 DB는 공용 postgres), 루트 ruff.
대상: `git diff main...HEAD`.
