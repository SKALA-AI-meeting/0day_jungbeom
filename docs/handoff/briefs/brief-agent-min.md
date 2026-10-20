# 브리프: agent-session 트랙 1단계 = agent-min (W3)
역할: 세션 에이전트 개발. worktree는 현재 폴더, 브랜치 track/agent-session. 커밋은 자기 브랜치에만, main 병합·push 금지.
이 라운드는 **agent-min**(M1 끝 최소 종단 흐름)까지만. 전이표 전체·observe·카드 실행·복구(M2 agent-session)는 다음 라운드 브리프로 이어진다. 단, 다음 라운드를 염두에 두고 구조(State 16필드, 노드 분리, Lock 규칙)는 설계대로 잡는다.
## 읽을 것
AGENTS.md, docs/plan.md(agent-min·agent-session 행, 소유권: `app/agent/{session,observe,llm,guard,mcp_client}/`), docs/dev-process.md, docs/agent/design.md 전체, docs/common/harness.md, docs/common/contracts.md(MCP 도구·허용 목록·내부 API·WS), docs/common/scenario-model.md, docs/decisions.md 2026-10-20 절 전부, scenarios/prompts/README.md와 프롬프트 전부(조립 블록 규약), scenarios/prompts/guard_patterns.yaml(unless·score 그룹·예문 47건), scenarios/prompts/fixtures/*.yaml, services/api/app/agent/runner.py(Protocol·Stimulus·RunResult·FakeAgentRunner), app/services/{runs,messages,context,session}.py, app/scheduler.py(run_agent lock_held 규칙, 카드 묶음·event_ids·done 판정), services/business-mcp/, services/rag-mcp/(도구·응답 봉투 {ok,data}/{ok:false,error}), services/api/pyproject.toml(mcp 클라이언트 SDK 버전).
앞선 보고서의 "다른 트랙에 알릴 것"(agent-session·agent-min 항목): /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report-2.md, api-admin-report.md, api-admin-report-2.md, api-candidate-report.md, api-candidate-report-2.md, business-mcp-report.md, rag-mcp-report.md, rag-mcp-report-2.md, prompts-report.md, prompts-report-2.md.
## 범위 (agent-min)
- `app/agent/llm/`: gpt-4o-mini 호출 래퍼(temperature, 타임아웃, 재시도 2회 → 규칙 폴백 신호), FakeLLM(고정 응답·스크립트), usage 집계, LangSmith 트레이싱에 run_id 태그.
- `app/agent/guard/`: guard_patterns.yaml 로더(groups·patterns·unless·replacement·notices·sentence_split·max_chars·citation·assistant_source_line), 문장 단위 치환, 예문 47건 단위 테스트 픽스처.
- `app/agent/mcp_client/`: business-mcp·rag-mcp Streamable HTTP 클라이언트, 그래프별 도구 허용 목록(계약 표), session_id 주입(모델이 바꿀 수 없음), {ok:false} 결과를 값으로 처리, upstream_unavailable 폴백.
- `app/agent/session/`: LangGraph 세션 그래프의 **respond 경로만**: 지원자 메시지 자극 → classify(recipient·kind, LLM 또는 규칙) → 컨텍스트 조립(common_rules + colleague.md 또는 manager.md, [최근 대화]·[문서 검색 결과]·[보드·문서 상태]·[작업 기억] 블록) → rag search_documents → 응답 생성 → guard → business-mcp post_message(run_id·seq, meta: 토큰·지연·모델) → RunResult. State는 설계의 16필드로 선언하고 이번에 안 쓰는 필드는 기본값. 체크포인터는 PostgresSaver(thread session:{id}). `SessionAgentRunner`가 AgentRunner Protocol을 구현하고 `context.py`에서 FakeAgentRunner 대신 선택되게(환경 플래그 `AGENT_RUNNER=session|fake`, 기본 fake 유지. context.py 변경은 이번만 허용).
- 이벤트(카드) 자극은 이 라운드에서 "카드 text를 그대로 post(system) 또는 brief로 생성(colleague/manager)"하는 inject 최소 구현까지만 해도 되고, 전이표·observe는 하지 않는다.
## 완료 기준 (plan.md agent-min + agent/design.md M1)
지원자 메시지 1개 → respond → rag 검색 → post_message → WS 노출 연결 테스트(api 안에서 MCP 서버 2개를 테스트 프로세스에 띄우거나 fastmcp 인메모리 클라이언트로 연결, LLM은 FakeLLM): `services/api/tests/`에 테스트 1개. guard 예문 47건 테스트 1개(parametrize). 허용 밖 도구 호출 거부 테스트 1개. 미공개 문서 질문에 "아직 공유되지 않은 자료" 응답(grounding g05) 테스트 1개. `uv run pytest`, 루트 `make test`·`make lint`. 실제 LLM 1회 확인은 `@pytest.mark.live`로 분리(`make test-live`가 있으면 그것으로, 결과를 보고에).
## 규칙
공용 postgres 사용(임시 DB conftest). 통합 스택 하나(api 상시 기동 금지). `infra/.env` 키 값 출력·복사 금지. 소유권 밖 파일(context.py 외)은 변경 요청으로. 커밋 메시지는 한국어 한 문장 + 테스트 명령.
## 보고
완료 기준 각 줄의 명령·결과, 수정 파일, 남은 문제, 변경 요청, 다른 트랙에 알릴 것, 그리고 **다음 라운드(agent-session M2)를 위해 정한 구조 메모**를 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/agent-min-report.md 에 저장. 마지막 응답은 경로 한 줄.
