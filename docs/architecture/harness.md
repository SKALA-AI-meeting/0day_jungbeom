# Harness — 모델 바깥의 코드

모델은 다음 발화나 도구 호출을 **제안**만 합니다. 실행·제한·기록·복구는 `agent/app/harness/`가 합니다(캡스톤 PDF 6장).
작업 하나(= task id = trace id)는 `runtime.TaskContext`(contextvar) 하나를 공유하므로 그래프 노드는 인자를 더 받지 않습니다.

## 1. 8개 구성 요소

| 요소 | 무엇을 하나 | 파일 | 확인 |
|---|---|---|---|
| **Instructions** | 역할·도구 규칙·금지·출력 형식을 `prompts/*.md`에 둔다. 첫 줄 `<!-- version: N -->`, `string.Template`(`$name`) 치환. 코드에 프롬프트를 쓰지 않는다. 사용한 버전은 trace `prompt_versions`에 남는다 | `harness/instructions.py`, `app/prompts/*.md` | `test_units.test_persona_card_from_versioned_prompt` |
| **Tools** | MCP 클라이언트(FastMCP, Streamable HTTP `/mcp`): business·rag·detector·analytics(`URLS`, `*_MCP_URL`). 호출마다 span, 루프 제한 집계, `TOOL_START/TOOL_END` 이벤트(`quiet=True`면 이벤트 없이 span만). 모델에 보일 결과는 PII 마스킹 후 4000자로 자르고, 오류는 예외 대신 텍스트로 모델에 돌려준다(`call_for_model`). 평가 데이터 인자(`REDACTED_ARGS`: observations, dialogue, report, analytics …)는 이벤트에서 크기만 보인다. analytics-mcp 도구는 모델이 아니라 코드만 부른다(아래 §1.1) | `harness/tools.py`, `mcp_servers/*/server.py` | `test_artifacts.test_artifact_tools_round_trip`, `test_units.test_tool_events_never_carry_evaluation_args`, `test_analytics`, `test_report_analytics` |
| **Context** | 대화록 토큰 예산(`BUDGET_CHARS` 6000자): 최근 메시지는 원문, 오래된 것은 요약. 대화 하네스에서는 장부 요약 + 최근 창(`window`, 3000자). RAG 결과는 tool 메시지로, 과제는 `artifacts.context_block`/`render_for_model`로 들어간다 | `harness/context.py`, `harness/dialogue.py`, `app/artifacts.py` | `test_units.test_context_budget_folds_old_messages` |
| **State·Memory** | LangGraph checkpointer: `DATABASE_URL`이 있으면 PostgreSQL(`AsyncPostgresSaver`, DB `agentstate`), 없으면 메모리. 작업마다 thread id(Spring이 정함), 승인 뒤 **같은 thread**로 `Command(resume=…)`. 세션의 장기 기억(대화 장부)은 Spring `sessions.dialogue_json`에 저장 | `harness/memory.py`, `runner.py`, `report_graph.py`, `account_review.py` | `test_account_review.test_ambiguous_account_waits_for_the_admin_and_resumes_on_the_same_thread` |
| **Agent Loop** | 작업당 그래프 8단계(`recursion_limit`), 120초, 같은 도구 3회(business.* 제외, analytics.*도 예외 없음: 리포트는 차트 4개를 `render_charts` 한 번으로 그린다), 모델 호출 16회. 페르소나 한 발화의 도구 라운드는 최대 2회(`llm.MAX_TOOL_ROUNDS`) | `harness/loop.py`, `llm.py` | `test_units.test_loop_limits`, `test_dialogue.test_harness_stays_within_loop_limits` |
| **Guardrails** | 변경 도구 승인: `business.save_report`는 항상, `business.decide_account`는 `auto_clean`/`auto_schema`가 아니면 사람 승인 전 호출 시 `ApprovalRequired`(그래프는 그 앞에서 `interrupt()`). `business.save_analytics`는 다시 계산할 수 있는 파생 데이터라 승인 없이 저장(Spring이 더 오래된 `state_rev`는 버림), analytics.*는 모두 읽기 전용. 도구 결과 PII 마스킹, 페르소나 출력 금지어(점수·합격·시뮬레이션 …). 심어 둔 체크포인트는 business-mcp에서 한 번 더 제거 | `harness/guardrails.py`, `mcp_servers/business/server.py` | `test_runner.test_change_tool_needs_approval_even_when_called_directly`, `test_account_review.test_guardrail_blocks_admin_basis_without_approval` |
| **Recovery** | 모델 429/5xx는 2회 재시도 후 대체 모델(`LLM_FALLBACK_MODEL`), 그래도 안 되면 작업 FAILED. 작업 수준: HTTP 모드는 `run_with_retries`(3회, backoff), RabbitMQ 모드는 `x-attempt`로 다시 발행 후 마지막엔 DLQ. 4xx·`NonRetryable`·`LimitExceeded`는 재시도하지 않는다. 재시도 TOKEN은 `attempt`/`reset`으로 앞선 부분 텍스트를 대체. 장부·감독 호출이 실패해도 턴은 규칙 기반으로 계속 | `harness/recovery.py`, `runner.py`, `queue_consumer.py`, `harness/dialogue.py` | `test_units.test_recovery_retries_then_falls_back`, `test_dialogue.test_failures_in_ledger_and_director_never_break_a_turn` |
| **Observability** | trace id = task id. 노드·모델 호출·도구 span, 토큰, 지연, 재시도·대체 횟수, 프롬프트 버전, 메모(`notes`: 재작성·과제 열람 등). 요약은 DONE/FAILED에 실려 Spring `ai_tasks.trace_json`에 run 단위로 쌓인다. `LANGSMITH_API_KEY`가 있으면 LangSmith에도 | `harness/observability.py`, `graph.traced`, `TaskService.appendTrace` | `GET /api/ai/tasks/{id}` → `trace[]`, `scripts/e2e.py` 마지막 줄 |

### 1.1 도구 정책 한눈에 (`harness/guardrails.py` docstring과 같음)

| 구분 | 도구 | 승인 |
|---|---|---|
| 사람 승인 뒤에만 | `business.save_report`, `business.decide_account`(분명한 경우 `auto_clean`/`auto_schema` 제외) | 그래프가 `interrupt()` → 체크리스트 → 같은 thread로 재개 |
| 자동 쓰기 | `business.init_session`, `append_turn`, `save_detection`(대화 기록), `save_analytics`(관리자 분석 스냅숏, 파생 데이터) | 없음. 업무 규칙과 `state_rev` 단조성은 Spring이 다시 검증 |
| 읽기 전용 | 모든 `rag.*`, 모든 `analytics.*`(`session_analytics`, `render_chart`, `render_charts`, `describe_charts`), `detector.describe_rubric`/`get_session_detections`, `business.get_session_state`/`list_conditions`/`get_account`/`list_artifacts`/`get_artifact`/`list_annotations` | 없음 |

analytics-mcp는 Agent 코드가 정해진 순서로 부릅니다(모델이 고르는 도구가 아님): ANALYTICS 작업(`session_analytics → business.save_analytics`),
START/TURN 뒤 조용한 백그라운드 갱신(지원자 스트림에 TOOL 이벤트 없음, 실패는 로그만), REPORT 그래프의 `analyze`(`session_analytics` + `render_charts` 한 번, 두 결과의 `state_rev`가 다르면 한 번 더 읽음; analytics-mcp가 안 되면 수치·차트 없이 초안을 이어 감)와
`save`(리포트 저장으로 `state_rev`가 올라가므로 다시 계산해 저장). 리포트 요약 프롬프트(`summarize*.md` v2)는 번들의 `figures`를 맥락으로 주되 수치를 쓸 때는 그대로만 옮기게 하고(인용을 강제하지는 않음),
디텍터 성향 추정과 κ는 역량 판단의 근거로 쓰지 않게 합니다. 자세한 계약은 [api-contract.md §5](api-contract.md#5-analytics--visualization-through-mcp-v4).

진행 이벤트는 `harness/events.py`(`EventPublisher`)가 묶어서 Spring `/internal/tasks/{id}/events`로 보내고, Spring이 SSE로 중계합니다.
Agent는 어느 화면이 듣는지 모릅니다(publish/subscribe).

### 루프 바깥의 닫힘 (Spring)
Agent가 끝내지 못한 작업은 Spring이 닫습니다: `TaskWatchdog`(진행 없는 QUEUED/RUNNING → FAILED), `TaskHandler.onFinished` 훅,
`InboxContributor`(REVIEW_ERROR, REPORT_FAILED). 자세한 표는 [extending.md §3](extending.md#3-루프-닫기--어떤-작업도-아무도-모르게-멈춘-채-남지-않게).

## 2. 대화 하네스 (item 6, `DIALOGUE_HARNESS=1` 기본)

3자 대화에서 같은 조항 반복, 상대 말 되풀이, 칭찬 맞장구, 회피형 페르소나가 불리지 않았는데 끼어드는 문제를 줄이기 위한 컨텍스트 엔지니어링입니다.
설계·근거는 [dialogue-harness.md](dialogue-harness.md), 전후 비교는 [docs/eval/dialogue_harness.md](../eval/dialogue_harness.md).

```
TURN graph:  observe ─┐
             ledger ──┤ (병렬)           react: 페르소나마다 컨텍스트 조립 + 발화 카드 + 반복 가드
             plan ────┴──► react ──► gate ──► (beat | closing) ──► final.dialogue ─► append_turn(dialogue=…)
             (감독 move 제안 → 코드가 화자 규칙 적용)
```

| 구성 | 하는 일 | 위치 |
|---|---|---|
| 장부(ledger) | 턴마다 구조화 호출 1회(관찰기·감독과 병렬): 오래된 턴 요약, 쟁점(open/agreed/parked), 약속(who/what/due), 입장·양보, 발화 수, 인용 조항, 본 마크업. 코드가 검증(말한 사람만 입장 변경, id 유지, "null" 문자열 제거), 실패 시 규칙 기반 대체 | `harness/dialogue.py`, `prompts/ledger*.md`, `graph.ledger` |
| 화자 규칙 | 불린 페르소나가 먼저, 회피형은 이름이 불릴 때만, 턴당 최대 2줄, 덜 말한 쪽에 차례, 같은 move 3연속 금지, 두 번째 화자는 첫 화자에게 답, 새 마크업은 과제 담당자가 답 | `dialogue.select` |
| 감독 move | `answer · ask_clarify · challenge · propose · concede · build_on · address_markup · summarize` + 대상·요점 | `prompts/director_dialogue*.md`, `llm.direct` |
| 페르소나 컨텍스트 | 요약, 쟁점, 자기 입장, 상대의 마지막 주장, 이미 나온 근거, 과제 블록, 최근 6개 원문. 도구: `search_company_docs`(rag-mcp), `open_shared_artifact`(business-mcp `get_artifact`) | `dialogue.persona_context`, `prompts/persona_dialogue.md`, `prompts/dialogue_move.md` |
| 반복 가드 | 자기 반복, 상대 말 되풀이, 20자 이상 재진술, 같은 조항 재인용, 같은 시작어, 칭찬 → 비스트리밍 재작성 1회(trace `notes`에 기록) | `dialogue.check` · `dialogue.feedback`, `llm.py` |
| 플래그 | `DIALOGUE_HARNESS=0`이면 장부 노드는 빈 동작이고 이전 프롬프트·흐름 | `dialogue.enabled()`, `docker-compose.yml` |

장부는 Spring에 불투명 JSON으로 저장되고(`/internal/sessions/{id}/turn` `dialogue`), 관리자 상세에만 읽기 전용으로 보입니다. 지원자 화면·SSE에는 나가지 않습니다
(`SessionService.candidateView`, `runner._turn`의 `quiet=True`, `tools.REDACTED_ARGS`).
