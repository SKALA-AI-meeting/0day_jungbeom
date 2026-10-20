# agent-min 보고서 (agent-session 트랙 1단계, W3)

브랜치 `track/agent-session`(worktree `Day-0_zaeho.worktrees/agent-session`). 시작 전 main(aedcc24, 문서만 바뀜)으로 fast-forward함.
커밋은 2개다. `34ecf71`은 1차 구현, `082bc21`은 Codex 리뷰 반영이다. main 병합과 push는 하지 않았다.

## 완료 기준별 명령과 결과

| 완료 기준 | 명령 | 결과 |
|---|---|---|
| 지원자 메시지 1개 → respond → rag 검색 → post_message → WS 노출 연결 테스트 | `cd services/api && uv run pytest -q tests/agent` (`test_candidate_message_flows_through_graph_rag_post_to_ws`) | **통과.** 실제 WS(`/ws/sessions/{id}`)로 message.send를 보냄 → ack → 스케줄러 spawn → SessionAgentRunner → 하위 프로세스로 띄운 실제 business-mcp·rag-mcp(Streamable HTTP) → 내부 앱 → hub → WS message.new(colleague, 같은 run_id). progress 순서는 started → tool_start/tool_end(search_documents) → finished. 모델 입력에 `[문서 검색 결과]`의 `[지표 현황]` 청크가 들어감. 분류가 meta.classification에 저장되고, 응답 meta에 model·토큰·cited_docs가 남음. agent_runs.usage(llm_calls=2)와 체크포인트(thread `session:{id}`, handled_stimuli)도 확인함. LLM은 FakeLLM |
| guard 예문 테스트(parametrize) | 같은 실행 (`test_guard.py`) | **48건 통과.** 원래 47건(hit·miss 44 + 안내문 3)에 리뷰 반영으로 혼합 문장 hit 1건을 더함 |
| 허용 밖 도구 호출 거부 | 같은 실행 (`test_tool_outside_allowlist_is_rejected`) | **통과.** 모델이 고른 post_message(다른 session_id)와 reindex_documents는 서버를 부르지 않고 `forbidden`을 돌려줌. get_board에 다른 session_id를 넣어도 주입값으로 덮어써 `{ok:true, tasks:[]}`가 됨. 상한(3회) 뒤에도 도구를 고르면 루프를 끝내고 폴백 "잠시만요."를 post함(fallback_used=True). 팀장 scope의 search_documents도 `forbidden` |
| 미공개 문서 질문에 "아직 공유되지 않은 자료"(g05) | 같은 실행 (`test_unreleased_document_question_answers_not_shared`) | **통과.** responsibility 채용 건이라 interview_summary가 미공개다. get_document가 `not_released`를 값으로 돌려줌. 검색 결과와 모든 모델 입력에 인터뷰 본문이 없음. 모델 문구와 무관하게 코드가 "사용자 인터뷰 요약 문서는 아직 공유되지 않은 자료예요."를 넣고, grounding.yaml g05의 expected_fact 정규식과 일치함 |
| `uv run pytest` | `cd services/api && uv run pytest -q` | **82 passed, 1 deselected**(live) |
| 루트 `make test` | `make test` | **통과.** api 82, business-mcp 11, rag-mcp 10, report-worker 1, web vitest 9 |
| 루트 `make lint` | `make lint` | **통과.** ruff check·format, eslint·prettier |
| 실제 LLM 1회 확인(live) | `cd services/api && uv run pytest -q -m live tests/agent` | **실패(1회 실행).** 아래 "live 결과" 참고 |

### live 결과 (gpt-4o-mini, 1회)
- run_id `7f120340-6d9b-4793-abf8-67a2922996a5`, usage `{llm_calls: 2, retries: 0, tokens_in: 5165, tokens_out: 137, latency_ms: 6450, tool_calls: 0}`, 모델 meta `gpt-4o-mini`. LANGCHAIN_TRACING_V2가 켜져 있어 이 run_id 태그로 LangSmith trace가 남았을 것이다(trace 화면은 확인하지 않음).
- 실패한 단언: g05 expected_fact(`아직\s*공유되지\s*않은\s*자료`)가 응답에 없음.
- 원인: 모델이 get_document를 부르지 않았다(tool_calls 0). 그래서 `not_released` 결과에 붙인 코드의 고정 문장 경로가 실행되지 않았다. 사전 검색 결과는 공개 문서만 보여 주므로 인터뷰 본문은 새지 않았다. 대신 모델이 "리서치 담당자가 정리해서 공유해 주기로", "사용자 의견이 포함될 거예요"처럼 내용을 짐작해 답했다. common_rules 5절 위반이고, guard 패턴에는 걸리지 않는다.
- 제안(M2 또는 오케스트레이터 결정): 미공개 판정을 모델의 도구 선택에 맡기지 않는다. respond 앞에서 코드가 list_documents(공개 여부)와 citation 별칭으로 질문이 미공개 문서를 가리키는지 확인한다. 해당하면 get_document를 결정적으로 부르거나 `[문서 검색 결과]`에 "미공개: 사용자 인터뷰 요약"을 명시하고, 같은 고정 문장을 넣는다.

## 수정 파일
신규(소유 폴더):
- `services/api/app/agent/llm/`: `base.py`는 재시도 2회(1·3초) 뒤 `LLMUnavailable`, Usage 집계, Trace(run_id 태그·메타데이터)를 맡는다. `openai.py`는 ChatOpenAI 래퍼(gpt-4o-mini, 타임아웃 30초, SDK 재시도 끔), `fake.py`는 FakeLLM(스크립트·예외 주입·입력 기록)과 `tool_call`이다
- `services/api/app/agent/guard/__init__.py`: yaml 로더(groups·patterns·strict_patterns·unless·replacement·notices·sentence_split·max_chars·citation), 문장 단위 치환, 같은 안내문 중복 제거, 600자 절단, `cited_docs`, scenario 복사본 기준 `guard_for`
- `services/api/app/agent/mcp_client/__init__.py`: McpClient(mcp 2.3 `Client`, Streamable HTTP, legacy 모드), 그래프별·페르소나별 허용 목록, session_id 주입, `{ok:false}`는 값으로, 연결·전송 실패는 `upstream_unavailable`, 도구 결과 2k자 절단, MCP list_tools로 만든 OpenAI 함수 스키마(session_id 제거)
- `services/api/app/agent/session/`: `state.py`(State·기본값), `seq.py`(고정 슬롯), `prompts.py`(system 조립·컨텍스트 블록·brief 치환), `classify.py`(수신자 규칙 + kind LLM JSON, 실패 시 규칙), `store.py`(분류 저장·카드 조회, 프로세스 안 DB), `nodes.py`(route·classify·respond·inject 최소판·close), `graph.py`, `runner.py`(SessionAgentRunner, AsyncPostgresSaver 풀)
- `services/api/tests/agent/`: `conftest.py`(MCP 서버 하위 프로세스, uvicorn 공개·내부 앱, 임시 DB 재색인, 비live 트레이싱 끔), `mcp_server.py`(서비스 가상환경에서 실행하는 기동 스크립트, rag는 2-gram 해시 임베딩), `test_guard.py`, `test_session_flow.py`, `test_live.py`

변경(허용 범위):
- `services/api/app/services/context.py`: `AGENT_RUNNER=session|fake`(기본 fake), session이면 OpenAILLM + MCP URL + DbAgentStore + DATABASE_URL 체크포인터
- `scenarios/prompts/guard_patterns.yaml`: 오케스트레이터가 이번만 허용. score 그룹에 `strict_patterns`(사람에 대한 점수 표현 3개, unless보다 먼저 검사)를 두고 머리말을 고침. 혼합 hit 예문 "리드님 현재 점수는 80점이고 재참여율은 22%예요." 추가. 그 결과 catalog_version이 바뀐다

리뷰 반영(Codex `review-agent-min-raw.txt`, 오케스트레이터 결정대로):
1. 기본 runner fake는 유지했다(결함 아님).
2. 도구 호출 상한 뒤에도 모델이 도구를 고르면 루프를 끝내고 폴백한다(`LoopResult.limit_hit`, error `tool_call_limit`). 루프는 최대 4회로 막았다.
3. guard는 strict_patterns를 unless보다 먼저 검사한다.
4. 동료 도구는 4개, 팀장 도구는 get_board·get_document_state 2개다(`PERSONA_TOOLS`).
5. not_released면 코드가 고정 문장을 넣는다.
6. 테스트 픽스처에서 체크포인터 setup을 미리 해 둔다(아래 남은 문제 1).

## 남은 문제
1. **체크포인터 setup의 CREATE INDEX CONCURRENTLY**: AsyncPostgresSaver.setup()은 첫 실행 때 인덱스를 CONCURRENTLY로 만든다. 그래서 다른 연결에 열린 트랜잭션이 있으면 끝날 때까지 기다린다. live 테스트가 메시지 조회 트랜잭션을 연 채 첫 실행을 부르다 멈춘 사례가 있었다(테스트는 세션을 분리했고, 픽스처는 setup을 미리 한다). 운영에서도 첫 실행이 idle-in-transaction 연결 때문에 지연될 수 있다. 앱 기동 시 `await runner.graph()`로 미리 초기화하는 것을 권한다(`app/run.py`는 foundation 소유라 변경 요청 2).
2. **live g05 실패**: 위 "live 결과". 모델이 도구를 고르지 않으면 미공개 고정 문장이 나가지 않고, 짐작 답변이 guard를 통과한다.
3. **design.md State 필드 수**: 본문은 "(16필드)"인데 나열된 이름은 17개다(`seq` 포함). 나열된 17개를 모두 선언했다. 문서 정합화가 필요하다.
4. **guard strict_patterns의 과잉 치환 가능성**: `(지금|현재|제|…)\s*.{0,10}점수`는 "제 생각엔 만족도 점수를 지표로" 같은 업무 문장도 치환한다(예전에는 unless가 보존했다). 지금 예문은 전부 통과한다.
5. **inject는 최소판이다**: system 카드는 text를 그대로 post한다. colleague·manager 카드는 brief로 한 메시지를 생성한다. 그래서 kickoff의 동료 인사, 분업 확정, review의 완성본 작성, respect의 위반 삽입, draft_part, current_element·window_start 갱신이 없다. review 카드는 실제로 쓰지 않은 파트를 "올렸다"고 말할 수 있다. M2 범위다. texture는 분업이 없을 때 "초안을 쓴 척하지 않는다"는 지시만 brief에 덧붙인다.
6. **분류기 지시문이 코드에 있다**: `classify.py`의 CLASSIFY_SYSTEM. prompts 트랙 파일이 없어서다. 버전 해시에 들어가지 않는다.
7. **팀장 respond에는 rag 사전 검색이 없다**: README 블록 규약(문서 검색 결과는 동료·어시스턴트만)을 따랐다. 그런데 manager.md는 회의록 인용을 요구한다. 어느 쪽이 맞는지 결정이 필요하다.
8. 응답당 도구 3회는 모델이 고른 호출만 센다. 코드의 사전 검색·보드·문서 조회는 따로다. usage.tool_calls도 모델 호출만 센다.
9. 예산 소진 안내문 `BUDGET_TEXT`는 프롬프트에 정해진 문구가 없어 코드에 임시로 둔 문장이다.

## 변경 요청
1. **business-mcp 분류 저장 도구**: 계약의 `PUT /internal/.../messages/{id}/classification`에 대응하는 MCP 도구가 없다. 지금은 프로세스 안 DB로 직접 저장한다(`session/store.py`). 계약 표에 도구를 추가하든지, 직접 저장을 인정한다고 명시해 달라. 카드 event_id → card_id 조회도 같다(내부 GET /sessions/{id}에 이벤트 행이 없다).
2. **`app/run.py`(foundation)**: 기동 시 runner 초기화(`getattr(ctx.runner, "graph", None)`가 있으면 await)와 종료 시 `aclose()`. 남은 문제 1 참고.
3. **`infra/.env.example`(foundation)**: `AGENT_RUNNER=fake`(session으로 전환) 항목 추가.
4. **harness.md Tools**: `langchain-mcp-adapters`를 쓴다고 적혀 있지만 의존성에 없다. 직접 만든 McpClient(mcp 2.3 SDK)를 썼으니 문서를 바꾸거나 의존성 추가를 결정해 달라.
5. **contracts.md 허용 목록 표**: 세션 그래프 respond를 페르소나별로 나눴다(팀장은 get_board·get_document_state만). 계약 표에 반영해 달라.

## 다른 트랙에 알릴 것
- **agent-assistant**: `from app.agent.llm import OpenAILLM, FakeLLM, Usage, Trace, LLMUnavailable`, `from app.agent.guard import guard_for`(scenario 복사본 기준, `apply(text).text`, `cited_docs`, `titles`), `from app.agent.mcp_client import McpClient, ASSISTANT_TOOLS, for_model, error_code`를 쓰면 된다. McpClient는 실행 task 안에서 `async with`로 열고 닫는다(anyio 제약). `scope(ASSISTANT_TOOLS).call(name, args)`는 session_id를 주입하고 `{ok:false}`를 값으로 준다. 연결 테스트 픽스처(`tests/agent/conftest.py`의 servers·stack)를 재사용할 수 있다.
- **e2e-runner**: 실제 그래프는 `AGENT_RUNNER=session`이어야 돈다(기본 fake). 응답 meta에 `model, node, tokens_in, tokens_out, latency_ms, llm_calls, tool_calls, cited_docs, guard_hits, fallback`이 있다. 폴백 응답은 seq 9 "잠시만요."다. 미공개 문서는 사용자 인터뷰 요약 등 문서 제목 뒤에 "문서는 아직 공유되지 않은 자료예요."가 붙는다.
- **api-candidate / foundation**: 운영에서 첫 실행 때 checkpoint 테이블이 생긴다(public 스키마의 checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations). 기존 테스트 conftest의 TRUNCATE에 함께 잡히고, 다음 실행 때 다시 setup된다.
- **prompts**: guard_patterns.yaml에 `strict_patterns` 키가 생겼다(score 그룹). 예문은 48건이다. live에서 동료가 미공개 문서를 짐작한 사례(리서치 담당자 언급)가 나왔다.
- **오케스트레이터**: guard_patterns.yaml 변경으로 catalog_version이 바뀐다. 이미 만든 채용 건은 옛 복사본을 계속 쓴다.

## 다음 라운드(agent-session M2)를 위해 정한 구조
- **State**: `app/agent/session/state.py`의 17필드(설계 나열 그대로)다. `defaults()`는 route가 thread의 첫 실행에서 채운다. scenario는 회사 문서 본문을 빼고 담는다(rag가 가짐). recent_messages는 team·dm만 최대 80개 담고, 페르소나별로 30개로 다시 거른다(notice·assistant는 State에도 넣지 않음). 메시지는 마지막 t_min−0.02부터 이어 읽고 id로 중복을 거른다(50개 페이지, 최대 5페이지). summary 접기는 아직 없다.
- **자극 처리**: 그래프 입력은 `{session_id, run_id, stimulus}`이고 나머지는 체크포인트에서 이어진다. `handled_stimuli`에 message_id·event_id·`end:<run_id>`를 둔다. route가 전부 handled면 END로 보낸다(재실행 멱등). classify 결과는 `stimulus.classification`에 넣어 respond로 넘긴다.
- **노드 분리**: route(Command goto) → classify → respond / inject / close. M2는 route에 phase 전이표를 넣고, negotiate·ask_division·kickoff·draft_part·review·request_report·observe 노드를 더하면 된다. 결정적 노드의 코드 도구 호출은 `deps.code`(SESSION_CODE_TOOLS)로, 모델 도구는 `deps.mcp.scope(PERSONA_TOOLS[persona])`로 한다.
- **실행별 의존성**: `RunDeps`(LangGraph Runtime context)에 llm, mcp(열린 연결), store, usage, progress, outcome(ok·fallback_used·error)를 둔다. 체크포인트되지 않는다. runner가 outcome·usage로 RunResult를 만든다.
- **멱등**: seq 슬롯은 `session/seq.py`(설계 표)에 있다. respond는 같은 run_id의 페르소나 메시지가 recent에 있으면 생성을 건너뛴다. inject는 event_id 메시지가 있으면 handled로 처리한다. post_message는 (run_id, seq)로 서버가 멱등이다.
- **Lock 규칙**: runner는 Lock을 잡지 않는다. 메시지는 scheduler.run_message → run_agent(lock_held=False)이고, 카드는 스케줄러가 Lock을 잡고 run_agent(lock_held=True)를 부른다. 카드 묶음의 seq는 `INJECT + 카드 순번`이고, done 판정은 행마다 event_id 메시지가 있는지로 한다.
- **체크포인터**: AsyncPostgresSaver와 psycopg 풀(max 4, autocommit, prepare_threshold 0)을 runner가 첫 실행에서 연다. thread는 `session:{id}`, recursion_limit 20이다. trace 설정은 tags `run_id:<id>`, metadata `{run_id, session_id}`다.
- **폴백**: LLM 실패, 빈 응답, 도구 상한 초과면 "잠시만요."(seq 9)를 post하고 fallback_used=True로 둔다. 실패 카운터와 세션 failed 전이는 api SessionService가 맡는다(M2에서 llm_failures 연결). 카드 생성이 실패하면 outcome.ok=False가 되고 스케줄러가 3회 재실행한다.
