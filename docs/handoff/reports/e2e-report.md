# e2e 보고 (S2: 러너·대본·eval 픽스처)

기준: track/debate 38cf9ef 위 track/e2e. 범위는 Python 러너 `tests/e2e/`, 대본 `scenarios/e2e/*.yaml`(`stages/` 제외), eval 픽스처 `tests/eval/`, `scripts/save_eval_fixture.py`, Makefile e2e 타깃. stage-e2e(Playwright)는 S3 몫이라 건드리지 않았다. 실 스택은 돌리지 않았다(api·agent 구현 중).

## 명령과 결과

| 명령 | 결과 |
|---|---|
| `make test-e2e` (mock) | 27 passed, 3 deselected(live) — 약 10초, 3회 연속 통과. 스택·DB·LLM 불필요 |
| `make lint` 중 ruff(`ruff check .`, `ruff format --check .`) | 통과 |
| `uv run --project services/api python tests/e2e/run.py --help` | 정상 (실 스택 `--script`·`--auth`·`--faults`는 실행하지 않음) |
| `make eval-live` | 실행하지 않음(키·agent 필요). `-m live` 3건(의도 분류·BARS·유출 질문) 작성만 |

## 검증 방식 (mock)

계약(`contracts.md`)과 계약 픽스처만으로 만든 가짜 api(`tests/e2e/fake_stack.py`)에 러너를 그대로 붙인다(httpx MockTransport 2개 + WS 연결기 주입). 서비스 코드는 import하지 않는다. 가짜 api는 agent 결정적 LLM 모드(`LLM_FAKE=1`) 규칙(안 라벨이 문장에 있으면 그 안, "좋아요" agree, "아니·반대" oppose, 물음표 question)으로 분류하고, 실제처럼 `started_at`을 앞당겨(테스트 API `advance`) 시간을 흐르게 하며 스케줄러 틱(시간 초과·카드 `card_due`·침묵 초대·자동 제출)을 돌린다.

| 테스트 | 확인 |
|---|---|
| `test_runner.py::test_script_passes[all_five·timeout_all·honesty_claim·restart]` | 대본 4개가 단언 통과, 기록 7파일 생성, transcript 토큰 가림 |
| `test_all_five_flow` | 칸 3개(candidate/p3/p3 consensus), 카드 6장, 검토 병합, 지연 p95 산출 |
| `test_each_assertion_catches_its_violation` ×8 | 입력 중 게시·화자 3명·지원자 없는 AI 채우기·소극형 임의 발언(2), 카드 누락(3), 선점 패턴(4), 마감 어긋남(1), 재조정 200(6)을 심으면 해당 단언이 실패 |
| `test_broken_contract_is_reported` | 근거 없는 수준·총점 필드를 심으면 단언 5 실패 |
| `test_faults_auth.py` | 장애 주입 2종 흐름, 프록시(503 ×N 후 통과·log), 인증 경계 9항목과 `auth.md` |
| `tests/eval/test_eval.py` (mock 9) | 의도 분류 20문장·BARS 5세션·유출 7건의 형태/라벨 규칙, 채점 함수, `save_eval_fixture.save` |

## 만든 것

- 러너 `tests/e2e/run.py`: 관리자 가입 → 채용 건(15분)·초대 → 입장(GET)·동의(표시 이름)·시작 전 `/state`·시작 → WS(typing 5초 갱신 포함)·REST로 대본 진행 → 제출/자동 제출 → `session.ended` → report_ready(120초) → 검토(단언 6)·final·`/record` → 내부 API·DB 수집 → 단언 → 기록. 시계 `--clock real|fake`(fake는 `POST /internal/test/sessions/{id}/advance`).
- 대본 `all_five`·`timeout_all`·`honesty_claim`(P0), `restart`(P1). step 키는 `scenarios/e2e/README.md`.
- 단언 `asserts.py`: 0(step 오류) 1~7 9 R. 8은 `auth.py`, 10은 `faults.py`. 총점 기대값 없음, 금지어는 `prompts/guard_patterns.yaml`의 `evaluator_forbidden`(워커와 같은 목록)을 읽는다.
- 기록 `tests/e2e/records/<일시>-<대본>/`: transcript.jsonl, turn_decisions.json, evaluations.json, report_draft/final.json, record.json, summary.md(단계 표·카드 표·단언·run별 도구 호출·비용·지연·trace).
- 장애 주입 2종 `faults.py`(`make e2e-faults`): 큐 DLQ(draft 저장 3회 503 → failed → regenerate → 같은 평가 run_id 재사용·평가 저장 호출 1회), LLM timeout(페르소나 발언만 생략, 평가는 저장 없이 재시도 뒤 성공).
- 인증 경계 `auth.py`(`make e2e-auth`, `records/<일시>-auth/auth.md`): 타 기업 404 ×3, 타 세션 403, 동의 전 401, 만료 JWT 401, 내부 토큰 없이 401, 공개 포트 `/internal` 404, assessment-mcp 토큰 없이 `forbidden`, 진행 중 `previous_session_id` 422, 재발급 뒤 옛 링크 404.
- eval 픽스처 `tests/eval/`: `intent_cases.yaml`(20문장, 제안 6·동의 3·반대 2·질문 4·기타 5, 이름 4·카탈로그 안 먼저 말하기 4), `bars_sessions.yaml`(요소별 대표 세션 5개 + 사람 라벨 18차원, **초안**: 사용자 검토 필요), `leak_cases.yaml`(7건), `evaluate.py`(채점 순수 함수), live 실행기 3개(`test_intent_live`는 `app.agent.intent.classify`, `test_bars_live`는 `report_worker.evaluate.evaluate_element`, `test_leak_live`는 실 스택에 세션을 열고 WS·어시스턴트로 질문).
- `scripts/save_eval_fixture.py <session_id>`: assessment-mcp `get_session_record` 결과를 `tests/eval/fixtures/sessions/<id>.json`으로 저장.
- Makefile: `e2e`(`SCRIPT=` 선택, 기본 all_five), `test-e2e`(주석만), `eval-live`(주석만), `e2e-auth`(그대로), `e2e-faults`(주석, 새 러너). **`e2e-concurrent` 타깃과 `.PHONY` 항목 삭제**: P2 동시 5세션은 이번 범위 밖이라 새 러너에 `--concurrent`가 없다.

## 삭제한 옛 파일

- `scenarios/e2e/`: `all_five.yaml`(옛 기획형), `assistant_reuse.yaml`, `division_refuse.yaml`, `early_submit.yaml`, `one_element.yaml`, `no_assistant.yaml`(P2, 새로 쓰지 않음), `restart.yaml`(옛), `README.md`(새로 작성)
- `tests/e2e/`: 옛 `asserts.py`·`auth.py`·`client.py`·`conftest.py`·`faults.py`·`records.py`·`run.py`·`script.py`·`stack.py`·`test_runner.py`(같은 이름으로 새로 씀, `conftest.py`는 가짜 api 픽스처)
- `tests/eval/`: 옛 `cases.yaml`·`conftest.py`·`evaluate.py`·`test_eval.py`(새로 씀)
- 옛 러너가 쓰던 `scripts/make_session.py`는 stage-kit 소유라 그대로 두었다(새 러너는 쓰지 않는다).

## api·agent·worker 트랙이 맞춰야 할 것

1. **api**: 러너가 의존하는 계약 필드 — `GET /s/{token}`의 `failed_stage`(DLQ 흐름), `/state`의 `active_runs`·`typing`(러너가 응답 완료를 기다리는 데 씀), 내부 `messages`의 `card_ids`·`meta.kind`·`origin`·`intent.addressed_to`·`intent.latency_ms`, 내부 `observations[].delivered`, 내부 `evaluations`의 `run_id`·`dimensions[].no_record_reason`, `GET /internal/sessions/{id}`의 `t_min_now`, 내부 테스트 API `advance`(`seconds`/`to: deadline|idle|card:<id>`). 시작 직후 `phase.changed{reason:start}`는 WS 연결 전에 나갈 수 있어 러너는 `start` 응답으로 첫 단계를 본다.
2. **agent**: 대본 문장은 `LLM_FAKE=1` 규칙(`agent/design.md` 표)에 맞춘 것이다. 라벨이 문장에 전부 있으면 그 안, "좋아요" agree, "아니·반대" oppose, 물음표 question. 실제 FakeLLM의 세부가 다르면 대본 문장을 고쳐야 한다. 특히 `honesty_claim`은 "해결책은 다른 분들 의견부터…"(기타 의도) 뒤에 비판형(p3)이 해결책 S2를 먼저 낸다고 가정(`at: msg:p3`)하고, `all_five`는 서지안이 반대·대안 2회에 지원자 안으로 옮기고 그 순간 지원자 포함 3/4로 합의 채우기(p3)가 된다고 가정한다.
3. **LLM 타임아웃 주입 훅(신규 약속)**: 공용 LLM 래퍼(`app/agent/llm`)와 워커 사본(`report_worker/llm.py`)이 env `LLM_FAULT=<role>:timeout:<N>`(역할 `persona`·`evaluator`)을 읽어 그 역할의 다음 N회 호출을 타임아웃으로 만들어야 한다. 러너는 페르소나 3회(최초+재시도 2회 = 발언 1개), 평가 1회로 주입하고 해당 서비스를 `LLM_FAULT`로 재기동한다. 계약·하네스에 없는 훅이라 오케스트레이터 승인이 필요하다.
4. **worker**: `API_INTERNAL_URL`을 러너 프록시로 돌려도 동작해야 한다(DLQ 흐름). 평가 LLM 타임아웃 뒤 큐 재시도 백오프(5·15·45초)가 있어 `llm_timeout` 흐름은 최소 5초 더 걸리고 러너는 리포트를 300초까지 기다린다.
5. **forbidden 패턴**: `prompts/guard_patterns.yaml`의 `evaluator_forbidden`은 "우선순위"를 허용한다. 워커 검증과 러너 단언이 같은 파일을 읽으므로 다른 구현(단순 부분 문자열)이 생기면 불일치가 난다.

## 알려진 한계·가정

- 실 스택 실행은 하지 않았다. `stack.py`의 서비스 기동 모듈(`app.run`, `debate_mcp`, `assessment_mcp`, `report_worker`)·health 주소는 현재 코드 기준 추정이고, assessment-mcp 접속(`mcp.client.streamable_http.streamablehttp_client`)과 `save_eval_fixture`·`auth`의 MCP 호출은 mock 대체로만 확인했다.
- 단언 3의 "예정 시각 뒤" 허용 오차는 0.05분(3초), 단언 2의 입력 중 게시 허용은 시작 후 0.25초다. 실 스택에서 흔들리면 상수(`asserts.py`)만 조정한다.
- 단언 2의 "침묵 초대 단계당 ≤ 1"과 "소극형 임의 발언"은 내부 `messages`(`is_invite`·`intent`)로 계산하고, "화자 ≤ 2"·"queued/started 잔존"은 DB `agent_runs`가 있을 때만 본다(없으면 건너뜀).
- 단언 4 선점 금지는 prompts 트랙 `fixtures/preemption.yaml`의 `must_not_regex`를 카드 창 안 해당 자리 발언에 적용한다. 새 카드 문구가 정규식에 안 걸리면 거짓 통과가 될 수 있다.
- 단언 9의 목표(비용 $0.5·지연 8초·의도 분류 3초)는 summary에 나란히 적고, DB·지연 값이 없을 때만 실패로 본다(목표 초과는 판정에 넣지 않음).
- `restart` 대본은 `E2E_RESTART_CMD`(예: `docker compose restart api`)가 필요하다. `--faults` 흐름에서는 `LocalStack`이 재기동한다.
- `fake_stack.py`는 서식 규칙(ruff, 줄 길이 100) 때문에 길다(약 1900줄). 가짜 api의 내용은 계약 표를 옮긴 것이라 계약이 바뀌면 같이 고친다.
