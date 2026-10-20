# 브리프: agent-assistant 트랙 (P2)

역할: 지원자용 AI 어시스턴트 그래프를 구현한다. worktree `../Day-0_zaeho.worktrees/agent-assistant`(현재 폴더), 브랜치 `track/agent-assistant`. 기준 커밋 main 최신(4b849b8 이후), 계약 커밋 37bed0b, catalog_version `b2cc7dd7baa915ca`.

## 공통 규칙
- 커밋은 자기 브랜치에만. 키 값 출력 금지. TDD happy path. 주석은 역할·알아야 할 로직·예외 의도 수준.
- **`app/agent/{llm,guard,mcp_client}/`는 import만 한다**(공개 함수·반환형 동결, agent-session 소유). 바꿔야 하면 변경 요청. `app/agent/session/`·`observe/`·`app/services/`·라우터·`docs/common/`·`scenarios/missions/` 문구·`tests/fixtures/contracts/` 수정 금지.
- 같은 시각에 agent-session이 `app/agent/session|observe` 등을, web-integrate가 `apps/web/`을 고친다.
- LLM은 FakeLLM, 실제 호출은 `live` 마커(gpt-4o-mini). 실제 스택: 사용 안 함(격리 DB·인메모리 MCP).

## 읽을 것
AGENTS.md, `docs/agent/design.md`의 "어시스턴트 그래프"·페르소나 표 어시스턴트 열·컨텍스트 허용 목록, `docs/common/contracts.md`(`POST /sessions/{id}/assistant`·429·assistant_calls·내부 `assistant_reuse`·rag `search_documents` 허용 목록), `docs/common/harness.md`, `docs/plan.md`(agent-assistant 행·소유권), `docs/dev-process.md`, `scenarios/missions/planning/prompts/assistant.md`·`common_rules.md`·`guard_patterns.yaml`·`fixtures/grounding.yaml`, `docs/handoff/reports/scenario-redesign-report.md`의 agent-assistant 항목(훅 `AppContext.assistant: AssistantRunner`, `answer(session_id, prompt, call_id) -> AssistantResult(content, cited_docs, usage)`; 요청·응답 메시지 저장·assistant_calls·60회 429는 api가 맡으므로 그래프는 중복 저장하지 않음), 기존 코드 `app/agent/runner.py`(AssistantRunner Protocol·FakeAssistantRunner), `app/agent/llm/`·`guard/`·`mcp_client/`의 공개 API, `app/services/context.py`(훅 자리), `app/routers/candidate.py`의 어시스턴트 경로, `services/rag-mcp/`(search_documents 응답·공개 필터), `app/services/reuse.py`(재사용 추정이 cited_docs·applied를 어떻게 쓰는지).

## 허용 파일
`services/api/app/agent/assistant/`(새 패키지), `services/api/tests/test_assistant*.py`(자기 테스트 파일만, `tests/agent/conftest.py`는 쓰지 않음), `app/services/context.py`의 **assistant 훅 연결 한 곳**(환경변수 `ASSISTANT_RUNNER=graph|fake`, 기본 fake 유지), `services/api/pyproject.toml`(의존성 추가 시).

## 범위
LangGraph `retrieve(search_documents top3, 세션 catalog_version·공개 필터) → answer(인용 포함, 어시스턴트 페르소나·공통 규칙·guard_patterns의 assistant_source_line) → guard`. thread `assistant:{session_id}`, 체크포인터 PostgresSaver(세션 그래프와 같은 저장소, 다른 thread). 컨텍스트 허용 목록: 공개된 회사 문서만, 지원자의 **보낸** 문서는 포함 가능하되 동료 미공개 문서·미래 카드·관찰 레이블·세션 대화는 넣지 않음. 응답에 cited_docs(doc_id 목록)·usage. "동료에게 뭐라고 답할까" 같은 요청도 답하되 점수·연출·합격을 말하지 않음(guard). LLM 실패 재시도 2회 → 규칙 폴백 문장(인용 없음). 60회 한도는 api가 429로 막으니 그래프에 없음.

## 완료 기준 (docs/plan.md agent-assistant 행 + agent/design.md)
공개 문서만 인용(미공개 문서 질문 → "아직 공유되지 않은 자료" 문장, grounding 픽스처 기준) 테스트 1, 인용 doc_id가 실제 검색 결과 안인지 1, guard(점수·합격·연출 언급 치환) 1, 폴백 1, `ASSISTANT_RUNNER=graph`일 때 `POST /sessions/{id}/assistant`가 그래프 응답을 돌려주고 assistant_calls에 cited_doc_ids가 남는 연결 테스트 1(인메모리 rag-mcp·FakeLLM). `cd services/api && uv run pytest`, 루트 `make test`·`make lint`. live 1회 결과는 보고에.

## 보고
`docs/handoff/reports/agent-assistant-report.md`: 기준 커밋, 완료 기준 줄별 명령·결과·검증 방식, 수정 파일, 남은 문제, 변경 요청(llm·guard·mcp_client 인터페이스에 필요한 추가), 다른 트랙에 알릴 것(web-integrate: 응답 형태·지연, e2e-runner: assistant_reuse 대본 기대값), live 결과. 마지막 응답은 경로 한 줄.
