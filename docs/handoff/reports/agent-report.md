# agent 트랙 보고 (S2, track/agent)

기준 `track/debate` 38cf9ef. WIP 0b4cd1b(테스트 미완)를 이어 완성하고 정리 커밋 2개 + 보고 커밋 1개로 바꿨다(WIP는 원격에 없어 로컬에서만 정리). push 안 함.

| 커밋 | 내용 |
|---|---|
| 987afc2 | `services/api/app/agent/` 구현(토론 그래프·의도 분류·guard·어시스턴트·MCP 클라이언트 분리·`LLM_FAKE`·역할별 temperature·`AGENT_RUNNER` 기본 session) |
| dadec4d | `services/api/tests/agent/` 단위 테스트 67개(+ live 1) |
| (이 커밋) | 이 보고서와 `agent-cr.md` |

## 완료 기준별 결과

| 기준 | 명령 | 결과 |
|---|---|---|
| agent 단위 테스트 | `cd services/api && uv run pytest -q tests/agent -m "not live"` | 67 passed, 1 deselected(live) |
| api 전체 테스트(회귀) | `cd services/api && uv run pytest -q` | 72 passed, 1 deselected |
| 루트 lint | `make lint` | ruff check·format 통과, web eslint·prettier 통과 |
| C5 계약 테스트 | `tests/agent/test_cards.py::test_c5_*` 4개 | 통과(아래) |

검증 방식은 모두 가짜 MCP(`conftest.FakeServer`, 계약의 도구 입출력·409 세부 코드 흉내)·가짜 hub(`FakeSessionPorts`)·`FakeLLM`/`DeterministicLLM`이다. DB·네트워크·실 LLM은 쓰지 않았다.

### design.md 완료 기준 대응

| design.md 기준 | 테스트 |
|---|---|
| 최소 흐름(메시지 → 의도 분류 → 지명 → respond → guard → stance_check → apply, typing start/stop) | `test_min_path.py::test_named_seat_responds_with_typing_and_stance` |
| 15분 대본: 단계 시작 화자, 문제 상황 카드 전 입장 없음, 합의 3/4 즉시 `fill_slot` 1회(seq 5 공지), 이번 AI 발언으로 3/4면 같은 run, 카드 6장 관찰, 그래프는 시간 초과 채우기 없음 | `test_script.py::test_fifteen_minute_script`(LLM_FAKE 결정적 응답으로 키워드→기획안 전 단계) |
| 합의가 이미 있으면 respond·apply 0회·공지 `post_message` 0건 / `fill_slot` 409면 칸·공지 0 / 합의 전 채우지 않음 / 같은 run_id 재실행 | `test_turn.py::test_existing_consensus_fills_without_respond`, `test_ai_reply_creates_consensus_in_same_run`, `test_fill_slot_conflict_saves_nothing`, `test_no_fill_without_consensus`, `test_same_run_id_rerun_converges` |
| 카드 전달: 버려진 카드 화자가 다음 run(새 run_id card_due)에서 이어 말함·관찰 중복 없음, 고집형 공동 발언 `card_ids` 2개·관찰 2건, 기준안이 지원자 지지 안과 다르게 잠김 | `test_cards.py::test_c5_*` |
| 턴 규칙: 화자 ≤ 2, 지명 우선, 소극형은 불리거나 전체 질문일 때만, 침묵 초대 단계당 1회·비판형·`is_invite`, 턴 LLM은 규칙 0명 + message일 때만, 같은 자리 3연속 금지 | `test_turn.py` 턴 규칙 7개 |
| typing·generation: 입력 중 10초 뒤 게시 0·재enqueue(`deferred`), 게시 직전 generation 변경 시 남은 화자 버림, 낡은 message 자극 skipped | `test_turn.py::test_candidate_typing_defers_and_requeues`, `test_generation_change_drops_remaining`, `test_stale_message_generation_is_skipped`, `test_min_path.py::test_stale_phase_is_skipped` |
| 입장: 설득 가능 규칙(2회에 이동, 1회는 불변), 고집형 불변, 지원자 S2 지지 시 `persuasion_solution`을 강한결이 S1로, 계획 밖 픽스처 5건 → 재생성 1회 → `stance_fallback`·게시 문장과 저장 입장 일치 | `test_cards.py::test_c5_critic_moves_*`, `test_critic_does_not_move_after_one_counter`, `test_persuasion_solution_swaps_actor_not_stance`, `test_persona.py::test_offplan_regenerates_then_fallback[5건]`, `test_offplan_regenerated_ok` |
| 경계: 페르소나 scope에 assessment 없음·호출 거부, 키워드 확정 전 자료 `not_released`, 페르소나 입력 스냅샷(카드 진행·cost_left·카드 id·성향 이름·평가 용어 없음), 표시 이름 호칭 | `test_persona.py::test_persona_scope_has_no_assessment`, `test_material_question_before_keyword_gets_not_released`, `test_persona_context_snapshot` |
| guard: 판정·결론 대리·합격 픽스처 4건 → 재생성 → 안전 문구, `allow_exact` 안내문 통과 | `test_persona.py::test_guard_regenerates_then_safe_phrase[4건]`, `test_guard_allow_exact_notice_passes` |
| 비용 상한: `cost_left ≤ 0`이면 respond LLM 0회·안전 문구 | `test_persona.py::test_cost_cap_uses_safe_phrase_without_llm` |
| 어시스턴트: 모델이 도구 선택(최대 3회), `cited_material_ids`, 잠금 안내, guard notice | `test_assistant.py` 5개 |
| 복구: 페르소나 LLM 재시도 2회 실패 → 발언 생략·`fallback_used`·`error=persona_llm_unavailable:<seat>`, turn LLM 실패 0명 | `test_turn.py::test_persona_llm_failure_skips_speaker`, `test_turn_llm_failure_means_no_speakers` |
| 의도 분류: 픽스처 20문장 스키마 위반 0·`confidence`, 메시지 단계 카탈로그로만 판정, 카탈로그 안 최초 언급은 `scenario_option_key`(행이 있으면 option_id), 실패 4종 → other·fallback | `test_intent.py`(픽스처 `tests/agent/fixtures/intent_keyword_20.jsonl`는 agent-spike 사본). 실 모델 기준선은 `-m live` `test_live_accuracy_baseline`(이번에 실행 안 함, 키 사용 금지) |
| trace `agent_run_id`, 턴 결정 저장 | `test_turn.py::test_trace_and_decision` |
| 결정적 LLM 모드: 같은 입력 두 번 → 게시 문장·안·입장·칸 같음, 실 호출 0, 키 불필요 / `AGENT_RUNNER` 기본 session | `test_llm.py::test_llm_fake_mode_is_deterministic`, `test_llm_fake_needs_no_key`, `test_fake_intent_rules`, `test_agent_runner_default_is_session`, `test_assistant.py::test_llm_fake_mode_assistant` |
| `ROLE_CONFIG.temperature`를 래퍼에 연결 | `test_llm.py::test_role_models_and_temperature`, `test_wrapper_passes_role_temperature` |

평가 에이전트 기준(design.md 마지막 줄)은 report-worker 트랙 범위라 여기서 다루지 않았다.

## 이번에 바꾼 것(WIP 대비)

- `llm/fake.py`: `DeterministicLLM(role)` 추가. 의도 분류는 키워드 규칙, 페르소나는 `[내 입장 계획]` 안을 지지하는 고정 문장(입장 미표명 단계는 중립 문장, 초대는 "OO님은 어떻게 생각하세요?"), 턴은 p3 1명, 어시스턴트는 `search_materials` 1회 뒤 첫 결과 제목 인용. 토큰·비용 0.
- `llm/roles.py`: `make_llm`이 env `LLM_FAKE=1`이면 키·모델 선택 없이 `DeterministicLLM`(역할 temperature 유지).
- `factory.py`: `DEFAULT_AGENT_RUNNER = "session"`, `runner_kind()`.
- `debate/rules.py`·`graph.py`: api 잠금이 없을 때 카드 시작 뒤 기준안을 고집형 현재 지지로 이어 씀(`held_lead`). 비판형 설득 횟수는 비판형의 그 단계 첫 발언 뒤 지원자 메시지만 셈(입장 표명 전 제안 제외).
- 긴 줄 정리(ruff E501)와 미사용 변수 제거.

## 수정 파일

`services/api/app/agent/{assistant/runner.py, debate/graph.py, debate/persona.py, debate/rules.py, debate/runner.py, factory.py, guard/__init__.py, intent/__init__.py, llm/__init__.py, llm/base.py, llm/fake.py, llm/roles.py, mcp_client/__init__.py, catalog.py, debate/__init__.py, assistant/__init__.py}` (WIP 포함 기준 38cf9ef 대비, 삭제: `assistant/graph.py`·`assistant/tokens.py`), `services/api/tests/agent/{conftest.py, test_min_path.py, test_cards.py, test_turn.py, test_persona.py, test_intent.py, test_assistant.py, test_llm.py, test_script.py, fixtures/intent_keyword_20.jsonl}`, `docs/handoff/reports/agent-{report,cr}.md`.

## api 트랙에 알릴 것(api-dev에 메시지로도 보냄)

1. 조립 입구는 `app/agent/factory.py`의 `db_scenario`·`build_debate_runner(settings, scenario, ports_for, checkpointer=None)`·`build_assistant_runner(settings, scenario)`. 현재 `services/context.py`는 삭제된 `app.agent.session.*`·`BUSINESS`를 import한다(호출 전까지는 터지지 않음).
2. `config.py` `AGENT_RUNNER` 기본값이 아직 `"fake"`다. `"session"`(`factory.DEFAULT_AGENT_RUNNER`)으로 맞춰야 완료 기준 "config와 runner 선택이 같은 기본값"이 성립한다.
3. `LLM_FAKE`는 agent가 os.environ(또는 `.env`)에서 직접 읽는다.
4. `intent.classify` 선택 인자 `message_id`(그래프가 같은 메시지를 다시 분류하지 않게 결과를 기억)·`instructions`(positions.scenario `prompts["intent.md"]`)를 메일박스가 넘겨 주면 좋다. 의도 결과 캐시는 프로세스 메모리라 재시작 뒤에는 그래프가 필요할 때 다시 분류한다(저장 없음).
5. 페르소나 LLM 실패 신호는 RunResult `fallback_used=True` + `error` 접두 `persona_llm_unavailable:`. 연속 3회 세션 failed 카운터는 api `SessionService`.
6. RunResult `status`는 `finished|deferred|skipped|failed`. `deferred`면 그래프가 이미 `SessionPorts.enqueue`로 같은 자극을 다시 넣었다(새 run_id 발급은 api).
7. 기준안 잠금은 CR-A1(아래) 참고. api가 `card_due` 처리 때 `session_cards.locked_option_id`를 잠그면 그래프는 그 값을 우선 쓴다.

## 남은 문제

- CR-A1: 해결됨. api 메일박스가 그래프 실행 전에 잠근다(track/api 8135002, `agent-cr.md` 처리 항목).
- design.md "변경 도구 전에 같은 (run_id, seq) 메시지가 있으면 LLM 생성 없이 재사용"은 구현하지 않았다. 재실행 게시는 api (run_id, seq) 멱등으로 기존 행이 돌아오지만, 재실행에서 다시 만든 초안의 입장이 원 게시와 다를 수 있다(LLM_FAKE에서는 같음).
- load의 "이 run_id가 이미 finished면 END"는 그래프가 `agent_runs`를 볼 수 없어 메일박스(api)의 status 검사에 맡겼다.
- `LLM_FAKE=1`에서 LLM 호출 trace는 남지 않지만, `LANGCHAIN_TRACING_V2`가 켜져 있으면 LangGraph 그래프 실행 trace는 남는다. 운영 compose에서 둘을 함께 켜지 않는 것으로 정리하거나 api가 fake 모드에서 tracing env를 끄면 된다.
- `common_rules.md`(시스템 프롬프트)에 금지 문구로 "고집형·소극형·비판형" 단어가 들어 있다. 페르소나 사용자 컨텍스트에는 없음을 검사했고, 시스템 쪽은 영문 유형 id가 없는지만 본다. 카탈로그 문구를 바꿀지는 prompts 소유자 판단.
- 의도 분류 실 모델 정확도(`-m live`)는 키 사용 금지라 이번에 재지 않았다(기준선 0.85는 agent-spike 값).
- 평가 에이전트용 결정적 고정 출력은 report-worker 사본 LLM 래퍼 몫이다(`DeterministicLLM`은 evaluator 역할에 `{}`만 낸다).

## CR

- CR-A1 기준안 잠금의 주체와 경로 — `docs/handoff/reports/agent-cr.md`. 그 분기만 대체 규칙으로 진행했다.
