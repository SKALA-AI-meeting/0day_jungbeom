# agent-assistant 보고 (P2)

- 브랜치 `track/agent-assistant`, 기준 커밋 main `6334fdb`(4b849b8 이후), 계약 커밋 37bed0b, catalog_version `b2cc7dd7baa915ca`
- 범위: `app/agent/assistant/` 새 패키지(LangGraph `retrieve → answer → guard`), `context.py` assistant 훅(`ASSISTANT_RUNNER=graph|fake`, 기본 fake)

## 완료 기준

| 기준 | 명령 | 결과 | 검증 방식 |
|---|---|---|---|
| 공개 문서만 인용(미공개 문서 질문 → "아직 공유되지 않은 자료") | `uv run pytest tests/test_assistant.py::test_unreleased_document_question_gets_fixed_sentence` | 통과 | grounding `g09_assistant_not_released`의 released·question·expected_fact·expected_tools(get_document)·expected_citation([]) 그대로. LLM은 한 번도 불리지 않음 |
| 인용 doc_id ⊂ 실제 검색 결과 | `…::test_cited_docs_stay_within_search_results` | 통과 | FakeLLM이 공개 문서(지표 현황)와 미공개 문서(사용자 인터뷰 요약)를 함께 인용 → cited_docs=`["metrics"]`, 본문의 `[사용자 인터뷰 요약]` 제거, 출처 줄 재작성. LLM 입력에 미공개 문서 본문 없음. 같은 thread 두 번째 호출이 앞 대화를 봄 |
| guard(점수·합격·연출 언급 치환) | `…::test_guard_replaces_verdict_sentences` | 통과 | "이렇게 하시면 합격이에요." → guard_patterns `notices.evaluation` 문장으로 치환, 업무 문장은 유지 |
| 폴백 | `…::test_llm_failure_falls_back_without_citation` | 통과 | 3회 실패(재시도 2) → "잠시 후 다시 시도해 주세요."(harness.md Recovery), cited_docs [] , usage.fallback_used=true |
| `ASSISTANT_RUNNER=graph` 연결 | `…::test_assistant_endpoint_uses_graph_runner` | 통과 | env로 `build_context()` → AssistantGraphRunner 확인 → LLM·rag만 FakeLLM·인메모리 rag로 교체 → 실제 공개 앱 `POST /sessions/{id}/assistant` 응답 content·cited_docs, DB `assistant_calls.cited_doc_ids == ["metrics"]`. 공개 필터는 내부 `GET /internal/sessions/{id}/documents` 값(시작 시 인터뷰 요약 미공개) |
| api 전체 | `cd services/api && uv run pytest` | 96 passed, 2 deselected | |
| 루트 | `make test` | api 96 · 9 · 10 · 27 passed, web 11 passed | |
| 루트 | `make lint` | 통과(ruff check·format, eslint·prettier) | |

## live 1회

`uv run pytest tests/test_assistant.py -m live -s` (gpt-4o-mini, 인메모리 rag, 5개 문서 공개, grounding `g06_main_users`) → 통과.

```
모아런의 주요 사용자는 혼자 뛰기 어려워 모임을 찾는 초보 러너와 정기 모임을 운영하는 러닝 크루 리더입니다. 이들은 러닝 모임을 통해 함께 뛰며 동기부여와 사회적 상호작용을 원하는 사용자들입니다.
출처: 회사·서비스 소개
cited_docs ['company_intro']  usage {llm_calls 1, retries 0, tokens_in 2681, tokens_out 74, latency_ms 1603, tool_calls 1}
```

본문 문장 끝 `[제목]` 표기는 모델이 생략했고 출처 줄만 남았다(assistant.md 형식의 절반). 인용 판정은 출처 줄로 충족.

## 동작 요약

- **retrieve**: `search_documents(query=prompt, top_k=3)`. 질문이 문서 제목·별칭(guard_patterns `citation`)을 짚었는데 결과에 없으면 `get_document`로 확인한다. 공개 전이면 `not_released`에 doc_id만 남기고(본문 받지 않음), 공개 문서면 앞 1500자를 결과에 더한다. 검색 자체가 실패하면 폴백 문장.
- **answer**: system = `common_rules.md` + `assistant.md`(채용 건 scenario 복사본). 앞선 자기 대화(최대 12개) → 마지막 사람 메시지에 `[문서 검색 결과]`·`[아직 공유되지 않은 자료]`·`[질문]` 블록. 질문이 짚은 문서가 모두 미공개면 LLM 없이 "아직 공유되지 않은 자료라 볼 수 없어요." `LLMUnavailable`(재시도 2회 후) → "잠시 후 다시 시도해 주세요."
- **guard**: 출처 줄(`assistant_source_line`)을 떼고 본문에 `Guard.apply`(치환·600자), 검색 결과 밖 문서의 `[제목]` 표시 제거, cited_docs = 본문·출처 줄에 나온 문서 ∩ 이번 검색 결과, 출처 줄을 cited 제목으로 다시 붙임(600자 안). 고정 문장은 인용 없음.
- 컨텍스트: 자기 대화 + 공개 문서 청크만. 팀 대화·동료 문서·카드·관찰 레이블은 노드가 받지 않는다. 지원자가 보낸 문서는 허용 목록상 넣을 수 있지만 어시스턴트 도구(search_documents·get_document)에 그 경로가 없고 persona 표("자기 대화 + 공개 회사 문서")를 따라 넣지 않았다.
- 체크포인터: `AsyncPostgresSaver`, thread `assistant:{session_id}`(세션 그래프와 같은 DB, 다른 thread). 첫 호출에서 풀을 열고 `setup()`.
- 진행 알림: `agent.progress {run_id: call_id, actor: "assistant", node: retrieve|answer, status: tool_start|tool_end|started|finished|failed, tool?}`를 hub로 보낸다(계약 actor 값 그대로).
- 응답 usage: `{llm_calls, retries, tokens_in, tokens_out, latency_ms, tool_calls, fallback_used}` → 라우터가 응답 메시지 `meta.usage`에 저장.

## 수정 파일

- `services/api/app/agent/assistant/__init__.py`, `graph.py`, `runner.py` (신규)
- `services/api/app/services/context.py` (assistant 훅 한 곳 + `_assistant_runner`)
- `services/api/tests/test_assistant.py` (신규)
- 의존성 추가 없음

## 남은 문제

- `app/run.py`는 `ctx.runner`만 미리 `graph()`·`aclose()` 한다. 어시스턴트 풀은 첫 호출에서 열리고 종료 시 닫히지 않는다(프로세스 종료로 정리됨). run.py는 허용 파일 밖이라 손대지 않았다 → 오케스트레이터 판단: `ctx.assistant`에도 같은 warm-up·aclose를 넣을지.
- 첫 호출의 `setup()`이 `CREATE INDEX CONCURRENTLY`를 쓰므로 다른 열린 트랜잭션이 있으면 기다린다. 세션 그래프가 같은 DB에서 먼저 setup했으면 마이그레이션이 이미 끝나 바로 지나간다. 테스트는 미리 `graph()`를 부른다.
- 모델은 `settings.openai_model`(세션 그래프와 같은 방식). `MODEL_ASSISTANT` 역할별 env와 키 선택 규칙은 llm 래퍼에 아직 없어 쓰지 않았다(llm은 agent-session 소유).
- `checkpoint_conninfo`를 `app.agent.session.runner`에서 import한다. agent-session이 이름을 바꾸면 깨진다.
- 미공개 판정은 질문에 제목·별칭(guard_patterns `citation.aliases`, 예: "인터뷰 요약"·"인터뷰 자료")이 들어간 경우만 잡는다. "첫 참여자 인터뷰 내용"·"사용자 조사 결과"처럼 별칭 밖 표현은 고정 문장으로 가지 않는다. 검색이 공개 문서만 돌려주므로 유출은 없고, 모델이 "공개된 회사 문서에는 그 내용이 없어요"로 답하게 된다.
- 모델이 검색 결과 밖 사실을 지어낸 문장은 `[제목]`만 지우고 문장은 남는다(내용 판정은 하지 않음). 근거 사실의 정확성은 이 트랙 테스트가 보장하지 않으며 e2e grounding 검사로 이어야 한다.
- 문장 끝 `[문서 제목]` 누락은 보정하지 않는다(출처 줄만 있어도 인용으로 인정). 두 형식을 모두 강제할지는 프롬프트 소유자와 정할 일.
- 세션별 Lock은 프로세스 안 dict라 api 프로세스가 여러 개면 직렬화되지 않는다(MVP는 단일 프로세스). 끝난 세션의 Lock 항목은 지우지 않는다.

## 변경 요청

llm·guard·mcp_client 공개 API(`BaseLLM.ainvoke`, `LLMUnavailable`, `Usage`, `Trace`, `guard_for`·`Guard.apply/cited_docs/titles/spec`, `McpClient.scope`, `ASSISTANT_TOOLS`, `error_code`) 자체의 변경은 필요 없다. 소유권 밖에서 필요한 것:

- **(a) api(라우터, `routers/candidate.py`)**: 어시스턴트 요청 메시지를 저장하기 전에 `app.masking.mask` 적용(지금은 원문 저장. 그래프 쪽은 마스킹 뒤 값만 LLM·체크포인트에 넣는다). 60회 카운트 조회와 assistant_calls INSERT 사이를 세션 단위로 직렬화(병렬 요청이 61회째를 통과할 수 있음). 그래프에 카운터·저장을 중복 추가하지 않는다.
- **(b) 실행 진입점(`app/run.py`)**: `ctx.assistant`에도 `graph()` 사전 초기화와 종료 시 `aclose()`. 지금은 `AGENT_RUNNER=fake`·`ASSISTANT_RUNNER=graph` 조합에서 첫 어시스턴트 요청이 체크포인터 마이그레이션(`CREATE INDEX CONCURRENTLY`)을 맡고, 다른 열린 트랜잭션이 있으면 그동안 기다린다. 풀도 종료 때 닫히지 않는다.
- **(c) agent-session(llm)**: 역할별 모델 `MODEL_ASSISTANT`와 키 선택 규칙(harness.md 역할별 모델, 고정 요구)을 담은 공용 LLM 생성 함수. 들어오면 `context._assistant_runner`의 `OpenAILLM(settings.openai_api_key, settings.openai_model)`을 그 함수로 바꾼다. 통합 인수 조건으로 관리.

## 다른 트랙에 알릴 것

- **web-integrate**: 응답 형태는 계약 그대로 `{call_id, message_id, content, cited_docs}`. content는 최대 600자, 문서를 근거로 썼으면 마지막 줄이 `출처: 제목1, 제목2`(cited_docs 순서와 같음), 아니면 출처 줄 없음. 지연은 동기 POST 한 번에 검색 1회 + LLM 1회(live 1.6초, LLM 실패 시 재시도 1·3초로 타임아웃 30초×3회 + 대기 4초로 최악 ~94초). 진행 표시가 필요하면 WS `agent.progress`(actor=assistant, run_id=call_id)를 쓸 수 있다. 폴백 응답은 "잠시 후 다시 시도해 주세요."이고 그 호출도 60회에 포함된다(api가 assistant_calls를 먼저 만든다).
- **e2e-runner**: cited_docs는 응답의 출처 줄과 같은 doc_id 목록이고 공개 문서만 들어간다(시작 시 interview_summary 미공개). `assistant_reuse`는 api `record_reuse`가 응답 메시지 본문(출처 줄 포함)과 지원자 문서 revision을 비교한다. 대본에서 applied=true를 기대하려면 그 호출 뒤 지원자 문서 revision에 응답 본문을 그대로 붙여 넣어야 한다(공백·구두점 제거 후 20자 이상 연속 일치 덩어리의 합이 응답 길이의 30% 이상. 출처 줄도 분모에 들어간다). 실제 LLM 응답은 매번 달라지므로 대본은 응답 본문을 받아 그대로 붙이는 방식이어야 한다.

## 수정 라운드(Codex)

`REVIEW.md` 차단 6건·권장 2건 반영. 기준은 이전 커밋 `01f2f18`.

| # | 지적 | 반영 | 검증 |
|---|---|---|---|
| 1 | 질문·history·검색 query 원문 전달 | runner가 그래프에 넣기 전 `app.masking.mask` → 체크포인트·LLM·검색 query 모두 마스킹 뒤 값. history를 다시 보낼 때도 `mask` 한 번 더(옛 체크포인트 대비) | `test_cited_docs_stay_within_search_results`에 이메일 질문 추가: 1·2번째 LLM 입력과 search query에 원문 없음 |
| 2 | 같은 세션 동시 요청이 history 덮어씀 | `AssistantGraphRunner`에 세션별 `asyncio.Lock`(세션 그래프 Lock과 별개) | 일회성 스크립트: 첫 LLM 호출을 0.2초 지연시킨 동시 2호출 → history 4건(질문A·답1·질문B·답2) |
| 3 | 별칭 포함 검사로 인용 생성 | 인용은 본문의 정확한 `[문서 제목]`과 유효한 마지막 출처 줄의 제목만. 별칭 검사는 질문의 문서명 탐지에만 | 새 테스트에서 본문 "회의록 이야기는…"(괄호 없는 별칭)은 인용 안 됨 |
| 4 | get_document 결과가 허용 집합에 섞임 | 오케스트레이터 결정대로 허용 집합 = `searched`(검색 결과) ∪ `fetched`(get_document로 읽은 공개 문서), State에 따로 둔다. 그 밖의 `[제목]`·출처는 제거 | `test_citations_allow_searched_or_fetched_docs_only`: 검색은 metrics만, get_document로 company_intro·policy → cited `[company_intro, metrics, policy]`, 출처 줄의 "지난주 회의록" 제거 |
| 5 | 도구 호출 상한 없음 | `MAX_TOOL_CALLS=3`(검색 포함). 넘는 문서 이름은 확인하지 않음 | 같은 테스트: 문서 3개를 짚은 질문 → `search_documents, get_document, get_document` 3회 |
| 6 | 입력 예산 없음 | 글자 수 근사 예산 `INPUT_CHARS=9000`(live 측정 약 0.56토큰/자 → 약 5k 토큰). 질문은 2000자로 자르고 응답 첫 줄에 "질문이 길어서 앞부분 2000자까지만 보고 답했어요." 안내. history는 자른 질문으로 저장. system·검색 블록·질문을 먼저 넣고 남는 만큼 최근 대화, 안 들어가는 오래된 대화는 질문 앞 40자 한 줄씩 `[이전 대화 요약]`으로 접음. get_document 본문은 800자 | 일회성 스크립트: `'가'*30000` 질문과 1900자 질문 5회 → 모델 입력 최대 8561자, 안내 문장 확인 |
| 권장 | get_document progress 없음 | `retrieve` 노드 `tool_start/tool_end`(tool=get_document) 추가 | 코드 확인 |
| 권장 | setup 실패 시 풀 누수 | `pool.open()`·`setup()` 실패·취소 시 풀을 닫고 다시 올림 | 코드 확인 |

보고서 정정: "인터뷰 자료"는 이미 별칭이라 예시를 별칭 밖 표현으로 바꿈, 변경 요청 (a)(b)(c) 명시, 근거 사실 정확성·`[제목]` 누락·Lock 범위를 남은 문제에 추가.

web-integrate 추가 안내: 94초는 LLM 재시도 부분의 최악 추정이고 MCP·첫 초기화·DB 대기를 포함한 POST 전체 상한이 아니다. 같은 세션의 동시 POST는 이제 순서대로 처리된다(뒤 요청은 앞 요청이 끝날 때까지 대기). 응답 첫 줄에 긴 질문 안내가 붙을 수 있다.

명령: `cd services/api && uv run pytest` → 97 passed, 2 deselected. 루트 `uv run ruff check .` → All checks passed, `uv run ruff format --check .` → 122 files already formatted. live는 이번 라운드에 다시 돌리지 않았다.

재확인 반영(차단 6): 입력 예산을 글자 수 근사에서 실제 토큰으로 바꿈. `tiktoken`(gpt-4o-mini 인코딩, `o200k_base`)으로 system·검색 블록·질문·history·접힌 요약과 메시지별 형식 오버헤드(4 + 응답 시작 3)를 더해 6,000토큰 이내로 맞춤(질문 1,500토큰 상한, 검색 블록은 남는 만큼 자름). `pyproject.toml`에 tiktoken을 직접 의존성으로 추가함(이전에는 langchain-openai를 거쳐 설치됨). 인코딩 파일은 처음 쓸 때 내려받으므로 오프라인 이미지에서는 캐시가 필요함. 새 테스트 `test_model_input_stays_within_token_budget`: '힣'*2000(4,000토큰) 질문 4회 → 매 호출 입력이 6k 이하이고 긴 질문 안내가 붙음. `uv run pytest` 98 passed, 2 deselected, ruff check·format 통과.
