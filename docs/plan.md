# 개발 계획 (토론형 전환)

기준: `docs/handoff/briefs/brief-debate-pivot.md`(D1~D21, D13-1~3, D18·D19 개정 BARS, 리뷰 반영 결정 R1~R7)와 그것을 반영한 설계 문서. 순서는 사용자가 정했다: **1 문서 → 1-1 계획 → 2 아키텍처 HTML → 3 목업 UI → 4 보고서 PDF → 5 나머지 개발**. 보고서는 1차본을 목업 전에 병렬로 쓰고, 목업 캡처는 G-M 뒤 report-fill이 채운다. 단계마다 리뷰 → 수정 → 커밋 → **사용자 확인** 뒤 다음 단계로 간다. 단계 안은 병렬 트랙으로 나눈다. 예외는 R6가 정한 둘이다: 실 LLM 경로를 미리 재는 `agent-spike`(W2~W3)와, G-C만 기다리는 W5-0 기반 트랙(W3와 병렬).

이전 계획(M0~M4, P0~P5, 전환 계획 T0~T3·G0/G1·F1~F12 기반 flow-* 트랙)은 **대체됨**. 원문과 이전 브리프·보고·리뷰는 git 33cfe90에 있다.

## 1. 단계·웨이브·게이트 한눈에

| 단계 | 웨이브 | 동시 트랙 (전체 동시 최대 4) | 병합 대상 | 끝 게이트 | 상태 |
|---|---|---|---|---|---|
| 1·1-1 문서·계획 | W1 | debate-docs | main | **G-D** | 완료(main 4f5de50) |
| 2 아키텍처 HTML | W2 | arch-page | main | **G-A** | 완료(main 2742aa3) |
| 3 목업 UI (준비) | W2 | contracts ∥ web-kit · ux-options | `track/debate`(contracts·web-kit), main(ux-options) | **G-C**, **G-U** | 완료 |
| 5 사전 검증 | W2~W3 | agent-spike | 병합 없음(보고서만) | G-F 동결 입력 | 완료(`track/agent-spike` 7a40d2a, `docs/handoff/reports/agent-spike-report.md`) |
| 4 보고서 | W2 · G-M 뒤 | report · report-fill | main | **G-R** | 완료(1차 과제 제출본 `docs/share/report.*`). 이후 고침은 report-refresh |
| 3 목업 UI (화면) | W3 | mock-candidate ∥ mock-admin | `track/debate` | **G-M** | 병합 완료. UI/UX 리뷰(`docs/handoff/reviews/gm-uiux-review.md`)의 실제 화면 항목은 gm-fix |
| 5 개발 (기반) | W5-0 | be-foundation ∥ scenario-catalog | `track/debate` | **G-F** | 완료 |
| 5 개발 (서비스) · S2 | W5-1 | api ∥ agent ∥ gm-fix ∥ report-worker(리뷰) → 빈 자리에 e2e | `track/debate` | 트랙별 완료 기준 | mcp 병합 완료(`track/debate` e4b91f8). api·agent는 WIP 재개 |
| 5 개발 (연결) · S3 | W5-2 | stage-kit ∥ web-integrate ∥ e2e(러너·대본 + stage-e2e) | `track/debate` | — | api·agent 병합 대기 |
| 5 개발 (검증) · S4 | W5-3 | stage-e2e 전 단계 → playtest → 실 스택 `all_five` 15분 1회 → fix-* | `track/debate` → main | **G-E** | 대기 |
| 후속 · S5 | G-E 뒤 | report-refresh ∥ arch-refresh | main | 사용자 확인 | 대기 |

**남은 순서** (기준 `track/debate` e4b91f8, 동시 개발 최대 4, 작성 모델 ≠ 리뷰 모델):

```
S1  계약·문서 보완 (오케스트레이터 작성, Sonnet 리뷰) → main 커밋 → track/debate에 병합
S2  api(Opus→Sonnet) ∥ agent(Opus→Sonnet) ∥ gm-fix(Sonnet→Opus) ∥ report-worker 리뷰(Opus)
      report-worker 병합 → 빈 자리에 e2e 러너·대본(Sonnet→Opus)
    병합 순서: report-worker → gm-fix → api → agent
S3  (api·agent 병합 뒤) stage-kit ∥ web-integrate ∥ e2e + stage-e2e spec   (모두 Sonnet→Opus)
S4  stage-e2e 전 단계 통과(LLM_FAKE, 영상·trace) → playtest 파일럿 후 확대(실 LLM, GIF)
    → 실 스택 all_five 15분 1회 → fix-* 영역별 병렬(최대 4) → G-E → main 병합(사용자 확인)
S5  report-refresh ∥ arch-refresh   (Sonnet→Opus)
```

- **동시 개발 트랙은 웨이브를 넘어 합쳐서 최대 4개**다. 리뷰 서브에이전트는 개발이 끝난 자리에서 돌리므로 따로 세지 않는다.
- **2단계와 3단계는 서로 독립이라 병렬로 둔다(W2).** arch-page는 문서만 읽고 `docs/share/architecture.html`만 쓰며, 3단계 트랙은 `apps/web`·픽스처만 쓴다. 사용자 확인은 G-A와 G-M을 따로 받는다.
- **W5-0은 G-C만 기다린다**(G-M 불필요). be-foundation은 `apps/web`을 건드리지 않으므로 W3 목업 트랙과 소유 경로가 겹치지 않는다.
- 보고서는 1차본 → report-fill(목업 캡처, G-R)로 1차 과제에 제출했다. G-E 뒤 **report-refresh**가 stage-e2e 스크린샷(실제 스택)과 playtest GIF로 캡처를 바꾸고 달라진 기능 설명을 고친다.
- 순서 의존: S1 → api·agent 브리프 / gm-fix·report-worker 리뷰는 S1과 무관 / e2e 러너·대본은 G-C만 / api·agent 병합 → stage-kit·web-integrate / stage-kit·web-integrate 병합 → stage-e2e 실행·playtest / 서비스 트랙 전부 병합 → W5-3 / G-E → 후속.

### 우선순위 (R6-g)

**MVP 우선 원칙**: P0 완료가 먼저다. 최적화와 정확도 개선은 P0을 막지 않으며 "MVP 이후" 목록(아래)으로 둔다. 트랙 표의 "우선순위" 열은 그 트랙 범위를 아래 등급으로 나눈다. 트랙은 P0 완료 기준을 먼저 통과시키고 P1, P2 순으로 진행한다. 일정이 모자라면 P2부터 미룬다.

| 등급 | 범위 |
|---|---|
| **P0** | 최소 경로(메시지 → 의도 분류 → 턴 → 페르소나 발언 → WS), 칸 확정, 시간 초과 채우기, 기획안 제출(자동 제출 포함), 리포트 큐(평가·draft·review·final), 인증(관리자·초대 링크), 이어하기(재접속) |
| **P1** | 카드 6장, 침묵 초대, AI 합의 채우기, restart(api 재기동 후 세션 복구) |
| **P2** | 관리자 채용 건 생성·초대의 실제 연결, 동시 5세션 |
| **MVP 이후** | 생성 전 입력 중 확인으로 버리는 생성 줄이기, 한 메시지 복수 의도, 대상 라벨이 없을 때 `confidence` low 강제 후처리, 턴 LLM 화자 쏠림 보정, websockets 버전 통일, 의도 분류 정확도(기준선 0.85) 개선(`docs/agent/design.md` "MVP 이후") |

## 2. 게이트

| 게이트 | 내용 | 통과 기준 |
|---|---|---|
| **G-D 문서** | `track/debate-docs`의 PRD·`docs/common/*`·역할별 설계·decisions·plan·handoff | 리뷰 차단 0 → 커밋 → main squash 병합 → 사용자 확인. **grep 정합**(아래 "G-D grep 규칙"): 현행 설명에 폐기 용어 0건. D13-3 필드(`display_name`·`avatar_url`), BARS 평가 계약(`get_session_record`·`save_evaluation`, `evaluations`·`evaluation_runs` 테이블, `prompt_versions` 맵, 차원 단위 `rubric_adjustments`, Report `elements`·`dimensions`·`facts`·`contribution_check`, 총점 없음, 리포트 그래프 `collect → aggregate → evaluate → draft → interrupt → finalize`)와 R1~R5 결정(요소 5개·페르소나 3명 고정, 60분 = 10·18·18·14와 15분 압축, 메일박스·`generation`, 그래프 자극 4종, 칸 `empty | confirmed`, 의도 분류 `confidence`)이 contracts·data-model·scenario-model·rubric에 들어가 있음 |
| **G-A 아키텍처** | arch-page 결과 | 한 페이지가 네 중심(설계 아키텍처 전체 구성도, 에이전트 구성과 역할, 흐름, MCP 역할과 접근 경계)을 담고 같은 정보를 뷰끼리 반복하지 않음(뷰 개수 고정 아님), 기존 구성도 그림 스타일·페이지 디자인 유지, 이름이 G-D 문서와 일치, 외부 의존 없이 열림, 교차 모델 리뷰 차단 0 → main → 사용자 확인 |
| **G-C 계약 픽스처** | contracts 트랙 | `tests/contract_shape.py`가 새 픽스처로 통과, `apps/web/mocks/fixtures/` 복사본이 같은 이름·id, **기대 실패 목록** `tests/expected-failures.txt`(깨지는 기존 테스트 노드 id → 담당 트랙) 작성·승인 |
| **G-U UX 결정** | ux-options 시안을 사용자가 고름 | **완료(2026-10-21, 모두 추천안)**. `docs/frontend/design.md` "UX 결정 (G-U)" 절에 반영(debate-docs). W3 브리프에 결정 커밋 해시를 적음 |
| **G-M 목업** | mock-candidate·mock-admin 병합본 | `docs/frontend/design.md` "완료 기준(목업 UI)" 전부, Opus UI/UX 리뷰 차단 0, 캡처 라이트 6장·다크 1장(`tests/e2e/records/mock-ui-<일시>/`, 15분 데모 모드 기준 화면), 사용자가 mock으로 확인 |
| **G-R 보고서** | report 1차본 + report-fill | A4 쪽 넘침·꼬리 줄 검사 통과, 이력 표현("이전에는"·"변경했다") 0, 기능마다 캡처 1장 이상(G-M 목업 캡처), 교차 모델 리뷰 차단 0 → main → 사용자 확인 |
| **G-F 백엔드 기반** | be-foundation (+scenario-catalog의 catalog_version) | `make up` 8개 서비스 healthy, 옛 테스트는 코드와 함께 삭제됐고 남은 테스트 `make test`·`make lint`가 갱신된 기대 실패 목록 안에서 통과, 교차 인터페이스 stub·`SessionPorts`·`services/api/pyproject.toml` 의존성이 들어가고 시그니처 동결(3절), agent-spike 결과(3절 "agent-spike 결과")의 역할 env 이름(S4)과 의존성 버전(S6)이 동결 내용에 반영됨 |
| **G-E 통합** | `track/debate` 전체 | **기대 실패 0**(`tests/expected-failures.txt` 비어 있음), `make test`·`make lint`·`make test-e2e`(mock) 통과, e2e P0 대본(`all_five`·`timeout_all`·`honesty_claim`)과 장애 주입 2종(큐 DLQ·LLM 타임아웃) 통과, **`make e2e-stages` 전 단계 통과**(`LLM_FAKE=1`, 영상·trace 기록), 실 스택 `all_five` 15분 1회 통과 기록, `make eval-live` 1회 기록 → `track/debate`를 main에 병합 → 사용자 확인 |

### G-D grep 규칙

단순 부분 문자열 검색은 현행 정상 용어(예: "대시보드", "전동킥보드")도 잡으므로 **단어·경로 단위**로 검사한다. 대상은 `PRD.md`·`AGENTS.md`·`docs/**/*.md`(아래 예외 제외).

| 검사 | 패턴(단어·경로 단위) | 허용 문맥 |
|---|---|---|
| 옛 산출물 | `보드`(단, `대시보드`·`킥보드`·`키보드`의 일부인 경우 제외), `분업`, `파트 문서` | 대체·삭제를 설명하는 문장 |
| 옛 인물·설정 | `한서윤`, `루프랩`, `모아런`, `주담당`, 옛 예시 이름 `민준`·`서연`·`지호` | 대체 설명 |
| 옛 상태·서비스 | `reporting`(세션 상태 값), `business-mcp`·`business_mcp`·`services/business-mcp` | 이름 변경 설명(`business-mcp → debate-mcp`), dev-process의 G-F 전 실행 경로 주석 |
| 옛 평가 계약 | `save_behavior_codes`, `BehaviorCodeUnit`, `/behavior_codes`, `classify_failed`, `total_score`, `auto_total`, `rubric.items` | 대체 설명 |
| R5로 삭제된 것 | `lock_held`, `room_quiet`, `slot.filled`, 칸 상태 `filled`, `PUT .../slots` | 대체 설명 |
| R3 이전 압축 시간 | `6분`(데모·압축·e2e 문맥) | 대체 설명 |

예외 파일·영역: 이 표 자체, `data-model.md` 삭제 표의 "삭제됨" 행, `decisions.md`, `docs/handoff/briefs/brief-debate-pivot.md`. 허용 문맥에 해당하는 검출은 검사 결과에 줄 번호와 사유를 적는다. 삭제·대체 설명이 아닌데 옛 기능을 현행 기능으로 요구하는 문장은 0건이어야 한다.

## 3. 브랜치와 병합

- **docs 트랙**(debate-docs, arch-page, ux-options, report, 후속 refresh)은 main에서 갈라져 main에 squash 병합한다.
- **코드 트랙**은 통합 브랜치 `track/debate`(main 33cfe90에서 생성됨)에서 갈라져 거기에 squash 병합한다. web-kit(G-C 무관)과 contracts(G-C)가 먼저 들어간다. agent-spike는 `track/agent-spike`에만 커밋하고 병합하지 않는다(main에는 보고서 파일만 복사할 수 있다).
- **기대 실패와 병합 규칙**: `track/debate`는 G-C부터 G-E까지 **승인된 기대 실패 목록** `tests/expected-failures.txt`(테스트 노드 id · 담당 트랙 · 사유)를 허용한다. `track/debate` 병합 조건은 "`make test` 실패가 목록 안에만 있고 목록 밖 실패 0"이다. contracts가 목록을 만들고, 각 트랙은 병합 때 자기 몫을 지우기만 하며 늘리려면 오케스트레이터 승인이 필요하다(be-foundation은 G-F에서 옛 테스트를 코드와 함께 삭제하고 목록을 갱신한다). **main 병합(G-E)은 기대 실패 0**이다. 기대 실패가 있는 상태로 main에 넣지 않는다.
- main이 바뀌면(docs 병합) 오케스트레이터가 main을 `track/debate`에 병합하고, 진행 중 트랙은 다음 rebase 때 반영한다.
- 계약 변경은 G-D·G-C 커밋으로만 들어간다. 구현 중 어긋나면 `docs/handoff/change-requests/CR-<날짜>-<트랙>-<번호>.md`(항목, 구현 값, 제안 값, 영향 트랙)를 쓰고 그 분기만 멈춘다. 채택되면 문서 담당 서브에이전트가 contracts·픽스처를 한 커밋으로 고치고 영향 트랙이 rebase한다. 개발 트랙은 설계 문서를 직접 고치지 않는다.

### 교차 인터페이스 (G-F에서 동결)

G-F 전에는 `services/api/app/agent/`도 be-foundation이 stub만 쓴다. **stub 파일은 be-foundation 소유로 만들고 G-F 병합 뒤 생산 트랙(agent 또는 api)에 인계**한다. 인계 뒤 시그니처 변경은 CR로만 한다.

| 인터페이스 | G-F stub 작성 | 인계(생산) | 소비 | 동결 내용 |
|---|---|---|---|---|
| `AgentRunner.run(session_id, stimulus, run_id) -> RunResult` (`app/agent/runner.py`) | be-foundation | agent | api(메일박스) | `docs/agent/design.md` 시그니처, 자극 4종(`message`·`phase_started`·`idle`·`card_due`). `FakeAgentRunner` 유지 |
| 의도 분류 `app/agent/intent` 공개 함수 | be-foundation (`other`·`confidence: low`만 돌려주는 stub) | agent | api `services/debate.py` | 입력(메시지·저장된 `messages.phase`의 카탈로그 안 전체·그 단계의 발언된 안 목록·참여자), 출력은 `contracts.md` "의도 분류 출력 스키마"(`confidence: high|low` 포함), 실패 시 `other` |
| `SessionPorts` (`services/api/app/ports.py`) | be-foundation | api | agent | typing 전송, `sessions.generation` 조회, 자극 enqueue(세션별 메일박스 입구). 메일박스 구현은 api |
| LLM 래퍼 키 선택·역할별 모델 (`app/agent/llm`) | be-foundation(설정·env만) | agent | 어시스턴트, report-worker(사본) | `MODEL_INTENT`·`MODEL_TURN`·`MODEL_PERSONA`·`MODEL_ASSISTANT`·`MODEL_EVALUATOR`(역할 표 `roles.py`), 재시도 2회, 역할별 타임아웃 |
| `services/api/pyproject.toml`·lock 의존성 | be-foundation | api(이후 추가는 오케스트레이터 승인) | api·agent | 아래 "agent-spike 결과" S6 동결 버전 |
| 내부 REST·MCP 도구 입출력 | — | api / 각 MCP | MCP·워커·그래프 | G-C 픽스처 그대로 |

### agent-spike 결과 (be-foundation·agent 입력)

근거는 `docs/handoff/reports/agent-spike-report.md`(`track/agent-spike` 7a40d2a). 오케스트레이터가 be-foundation·agent·mcp 브리프에 옮겨 적는다. S4·S6은 G-F 동결 대상이다.

| 번호 | 결과 | 받는 트랙 |
|---|---|---|
| S1 | `message` 자극의 generation은 그 메시지 저장이 올린 값(enqueue 때 다시 읽지 않음). 더 새 메시지가 있으면 턴·발언만 skipped | api, agent |
| S2 | `stance_check`: 페르소나가 자기 계획 안에 `oppose`·반대 발언을 내는 것도 계획 밖 | agent |
| S3 | MCP 도구는 모두 `async def`(FastMCP 4.1.1은 sync 도구를 워커 스레드에서 실행) | mcp, be-foundation(rag-mcp) |
| S4 | 역할 env 이름 `MODEL_INTENT`·`MODEL_TURN`·`MODEL_PERSONA`·`MODEL_ASSISTANT`·`MODEL_EVALUATOR`. be-foundation이 `infra/.env.example`과 `roles.py`를 교체 | be-foundation(G-F 동결) |
| S5 | `message.ack`는 메시지 저장 직후, 의도 분류 전에 보낸다 | api |
| S6 | 동결 의존성: Python 3.12, openai 3.35.1, fastmcp 4.1.1, mcp 2.3.0, pydantic 2.14.1, uvicorn 0.54.0, pytest 9.1.1, pytest-asyncio 1.4.0. langgraph·langchain 계열은 기존 lock 유지 | be-foundation(G-F 동결) |
| S7 | 실측 기준선(gpt-4o-mini, p50/p95): 의도 분류 1.0/1.2초, 페르소나 1.2/1.4초, 턴 1.2/1.5초. 60분 세션 비용 추정 $0.08~0.11, 의도 분류 정확도 0.85. 문서·보고서용 기준선이고 완료 조건이 아니다 | agent, report |

## 4. 트랙

소유 경로는 겹치지 않는다. 표에 없는 경로가 필요하면 멈추고 오케스트레이터에 요청한다.

### 4.1 W1·W2: 문서·아키텍처·목업 준비·사전 검증

| 트랙 | 입력 | 소유 파일 | 산출물·범위 | 완료 기준 | 의존 |
|---|---|---|---|---|---|
| **debate-docs** (3차 리뷰 반영 중) | 브리프 | `PRD.md`·`PRD.html`, `AGENTS.md`, `docs/` 전부(share·review 제외) | 문서 전체 토론형 개편, 시나리오·평가표 초안, R1~R7 반영, 이 계획과 handoff | G-D | — |
| **arch-page** (완료) | G-D 문서, `docs/assignment/reference-architecture.md` | `docs/share/architecture.html`과 그 자산 | 현재 페이지의 **전체 구성도 그림 스타일과 페이지 디자인은 유지**하고 내용만 토론형으로 바꾼다. 중심은 네 가지: ① 설계 아키텍처(전체 구성도) ② 에이전트 구성과 역할(턴 매니저·페르소나 3·의도 분류·어시스턴트(tool-calling)·평가 에이전트) ③ 흐름(세션별 메일박스·토론 세션·단계 전환·api 시간 초과·평가 파이프라인 `collect → aggregate → evaluate → draft → interrupt → finalize`) ④ MCP 역할(debate=손·rag=눈·assessment=기록자, 접근 경계와 assessment 차단). Harness는 이 흐름 안에서 필요한 만큼만. **중복 제거**: 티어·레이어 뷰처럼 구성도와 겹치는 내용은 합치거나 줄인다. 뷰 개수는 고정하지 않는다. 범례·번호 표, design-system 토큰, 이력 표현 없음. G-D 전에 시작했으므로 G-D 병합본으로 rebase한 뒤 이름을 대조한다 | G-A | G-D |
| **contracts** | G-D `contracts.md`·`data-model.md`·`scenario-model.md`·`rubric.md` | `tests/fixtures/contracts/`(전부 교체), `tests/fixtures/README.md`, `tests/contract_shape.py`, `tests/expected-failures.txt`(신규), `apps/web/mocks/fixtures/*.json` 중 계약 복사본만(**`debate_script.json`·`office_script.json` 제외**, 둘은 mock-candidate 소유) | 한 세션 기준(60분, 요소 5개 고정, 자리 p1~p3 = 고집형·소극형·비판형) 계약 예시: entry(`session_id`·초대 이름)·consent·resume(`session_id`)·시작 전 State·State 4단계(칸 `empty | confirmed`)·WS 이벤트(봉투 `seq`)·Proposal·debrief·자료·어시스턴트·관리자(catalog·candidates·reissue·Report BARS·review `reviewer_name`·record)·내부 REST(DebateState·Contributions·observations·SessionRecord·EvaluationSave·evaluations·evaluation_runs)·의도 분류 출력(`confidence`)·MCP 도구 3종 응답·큐. 옛 보드·문서·보고 픽스처 삭제 | G-C | G-D |
| **web-kit** (병합 완료, `track/debate` 1d45d28) | G-D `frontend/design.md`(디자인 컨셉·레이아웃)·`design-system.md`(D13-2) | `apps/web/components/ui/`, `apps/web/app/globals.css`, `apps/web/app/layout.tsx`(폰트), `apps/web/public/brand/`, `apps/web/package.json`·lockfile(Pretendard 등 사전 승인) | Apple식 토큰(라이트·다크), 시스템 폰트 + Pretendard, 자리 틴트 토큰, avatar의 원형 크롭·이니셜 대체·자리 색 props, 기존 ui props 호환 | 토큰 대비 4.5:1 표 확인, `pnpm test`·`pnpm lint`, 기존 화면이 깨지지 않음. 교차 모델 리뷰 차단 0 → `track/debate` | G-D(G-C 불필요) |
| **ux-options** (완료) | G-D `docs/frontend/design.md` UX 항목 10개 | `docs/review/ux-options.html`과 자산 | 항목 10개마다 A·B·C 후보 와이어프레임 | 사용자 선택 **완료(모두 추천안)**. design.md 절 갱신은 debate-docs가 반영함 | G-D |
| **agent-spike** (완료, `track/agent-spike` 7a40d2a, 병합 없음) | G-D `agent/design.md`·`contracts.md`, 실 LLM 키 | `spikes/agent-spike/`(`track/agent-spike` 브랜치에만), `docs/handoff/reports/agent-spike-report.md` | 최소 경로 한 줄: 지원자 메시지 → 의도 분류(실 모델) → 규칙 턴(화자 1명) → 페르소나 1명 발언(실 모델) → 최소 debate-mcp `post_message` → WS 수신. 세션별 메일박스(asyncio Task 1개가 자극 큐 직렬 소비)와 `generation` 폐기 규칙을 같이 시험. 의도 분류 eval 20문장 정확도 기준선(R4) | 보고서에 실 LLM 지연(p50·p95, 역할별), 세션당 예상 비용(달러), 메일박스·generation 동작, 의도 분류 정확도 기준선, 동결 인터페이스·의존성 제안. 오케스트레이터가 그 값을 be-foundation·agent 브리프와 G-F 동결 내용에 옮겨 적음 | G-D |

### 4.2 W3: 목업 화면

| 트랙 | 입력 | 소유 파일 | 산출물·범위 | 완료 기준 | 의존 |
|---|---|---|---|---|---|
| **mock-candidate** | G-C 픽스처, web-kit 병합본, G-U 결정 | `apps/web/app/s/`, `apps/web/app/page.tsx`, `apps/web/components/office/` → `components/debate/`(이름 변경·삭제 포함), `components/dev/`, `apps/web/lib/{api,ws}.ts`, `apps/web/mocks/` 중 `index.ts`·`types.ts`·`office.ts`(→`debate.ts`)·`ws-replay.ts`·`worst.ts`·`README.md`·`fixtures/debate_script.json`(web 전용, 옛 `fixtures/office_script.json` 삭제), `apps/web/public/mock-avatars/`, `apps/web/e2e/` | 입장·동의(표시 이름·형식 안내)·대기(참여자 소개)·토론방(iMessage 말풍선, 진행바·남은 시간 중심, 오피스 시각은 메시지 타임스탬프만, 입력 중)·우측 4탭(결정 사항·자료·어시스턴트·기획안)·단계 전환·제출·디브리핑(본인 발언 회고·이의 제기 경로), mock-controls, 15분 데모 모드. 지원자 화면 문구는 지원자 말("정할 항목"·"결정 사항"·"이걸로 정하기"). 보드·분업·파트 문서·팀장·개인 알림 코드와 테스트 삭제. 캡처 스크립트 | design.md 완료 기준의 지원자 항목, 유형·옛 흐름 grep 0건(디브리핑 전 화면 한정), `pnpm test`·`pnpm lint` | G-C, web-kit, G-U |
| **mock-admin** | 위와 같음 | `apps/web/app/admin/`, `apps/web/components/admin/`, `apps/web/mocks/admin.ts`, `apps/web/fixtures/sample-report.json` | 채용 건 생성(**요소 선택 UI 없음**: 5요소 고정 안내와 세션 길이 등만)·지원자 목록(요소별 수준 칩, 정렬 없음)·초대 재발급·리포트(한 열 문서, "설계된 장면" 표시, BARS 차원 수준·근거·확신도·담당자 차원 조정·메모)·전체 기록·샘플 리포트·인쇄 | design.md 완료 기준의 관리자 항목, `pnpm test`·`pnpm lint`. `lib/api.ts` 변경은 mock-candidate에 요청 | G-C, web-kit, G-U |

- 두 트랙 병합 뒤 G-M: Opus UI/UX 리뷰 서브에이전트(실제 mock 화면·스크린샷) → 수정 → 캡처 → 사용자 확인. 캡처는 mock-candidate가 `apps/web/e2e/`의 스크립트로 뜬다.

### 4.3 보고서

| 트랙 | 입력 | 소유 파일 | 산출물·범위 | 완료 기준 | 의존 |
|---|---|---|---|---|---|
| **report** (1차본 작성됨, `track/arch-page`) | PRD, `architecture.html` | `docs/share/report.html`, `docs/share/report.pdf`, `docs/share/report-assets/` | `deliver:report` 스킬. 서비스 간단 설명 → 아키텍처 → 주요 기능(토론 4단계·결정 사항·페르소나 3·자료·어시스턴트·기획안·리포트 BARS) → A4 PDF 14쪽. 구현 결과 캡처는 자리(그림 7-1~7-5: 토론방·결정 사항·기획안·디브리핑·관리자 리포트)만 둔다. 최종본 기준, 이력 표현 없음 | A4 쪽 넘침·꼬리 줄 검사 통과 | G-D 문서 |
| **report-fill** | report 1차본, G-M 캡처 폴더(`track/debate` worktree에서 읽기만), G-A `architecture.html` | report와 같음 | 그림 7-1~7-5 자리에 **목업 캡처**를 넣고 G-D·G-A와 이름을 대조 | G-R | G-A, G-M |
| **report-refresh** (S5) | stage-e2e 스크린샷(`tests/e2e/records/stages/`), playtest GIF·요약, G-E 결과 | report와 같음 | 캡처를 실제 스택 화면으로 교체하고 달라진 기능 설명만 고침. UI/UX 리뷰 B1~B3(캡처 품질)은 여기서 새 캡처로 해소 | G-R 검사 재통과 → 사용자 확인 | G-E |

### 4.4 W5: 나머지 개발

| 트랙 | 입력 | 소유 파일 | 산출물·범위 | 우선순위 | 완료 기준 | 의존 |
|---|---|---|---|---|---|---|
| **be-foundation** | G-C, G-D 설계, agent-spike 결과(3절, S3·S4·S6) | `infra/db/schema.sql`, `infra/docker-compose*.yml`, `infra/.env.example`, `Makefile`, 루트 `pyproject.toml`·`uv.lock`, `tests/conftest.py`, `tests/expected-failures.txt`(갱신), `services/api/pyproject.toml`·lock, `services/api/tests/conftest.py`, `services/api/app/{main,run,config,ports}.py`·`app/models/`, **G-F stub**(`services/api/app/agent/runner.py`·`app/agent/intent/`·`app/agent/llm/` 설정, G-F 뒤 agent에 인계), `services/rag-mcp/`(정리 흡수), `scenarios/version.py`, `scripts/seed.py`, `scripts/README.md`. 삭제: `services/api/app/services/{board,documents,events,releases,reuse,views}.py`, `app/agent/{session,observe}/`와 **해당 옛 테스트 전부**(코드와 함께). 이동: `services/business-mcp/` → `services/debate-mcp/`(디렉터리·패키지 이름만). 신규 골격: `services/assessment-mcp/`(`/health`·Dockerfile·pyproject·lock) | 토론형 스키마(options·stances·slots `empty|confirmed`·message_intents·proposals·observations·evaluations·evaluation_runs·차원 단위 rubric_adjustments, `sessions.display_name`·`generation`·`ended_at`, 자료 원문 `catalog_version`별 시드), 삭제 테이블 제거, compose 8개 서비스, env(`ASSESSMENT_MCP_TOKEN`, 역할 env 5개로 `.env.example`·`roles.py` 교체, 옛 `MODEL_COLLEAGUE`·`MODEL_MANAGER`·`MODEL_OBSERVE`·`MODEL_REPORT` 삭제), S6 동결 의존성, 교차 인터페이스 stub·`SessionPorts`. rag-mcp: 키워드 키 `material_chunks`·확정 전 차단·버전별 원문 | P0 | G-F | G-C |
| **scenario-catalog** | G-D `scenario-model.md`·`rubric.md`(초안 표시 포함) | `scenarios/missions/debate/` 전부(`mission.yaml`·`keywords.yaml`·`personas.yaml`·`cards.yaml`·`materials/`·`prompts/`·`assets/avatars/`, 평가표·앵커 데이터), 옛 `scenarios/missions/planning/` 삭제 | 키워드 4개와 키워드별 문제 상황 안·해결책 방향 안·자료, 페르소나 고정 3명(강한결·윤하람·서지안)의 이름·말투·단계별 고정 입장(확장용 동조형·발산형은 데이터만, 세션 조립에 쓰지 않음), 카드 6장(`offset_min`), 침묵 초대·시간 초과 고정 문장, 페르소나·턴 매니저·의도 분류·어시스턴트·평가 에이전트 프롬프트, 금지 패턴·안전 문구·프롬프트 픽스처, 임시 아바타 | P0(카드·초대 문장은 P1) | 값이 scenario-model·rubric 표와 일치(대조표 보고), 아바타 파일명에 유형 이름 없음, catalog_version 발급·공지. 사용자 검토 대상 초안은 표시 유지 | G-D |
| **api** | G-F, catalog_version, G-C | `services/api/` 중 `app/agent/`·foundation 소유 제외 전부(`routers/`, `services/`, `scheduler.py`, `hub.py`, `mailbox.py`, `auth.py`, `queue.py`, `masking.py`, `README.md`, G-F 뒤 인계받은 `ports.py`·진입점), `services/api/tests/`(`tests/agent/` 제외) | 조립(5요소 고정 → 자리 3·카드 6), 세션·단계·누적 마감·타이머(가짜 시계 주입)·마감 임박, 세션별 메일박스·`generation`, 스케줄러의 `idle`·`card_due` enqueue와 `invite_delivered` 재평가, **시간 초과는 api가 결정적으로 채움**(선택 규칙 + 고정 문장), 칸 confirm(합의 판정 `consensus.py`, 정규화 일치 연결), 메시지·`origin`·메일박스 안 의도 분류 반영(낡은 자극도 분류·반영, high만 지지, 참여자당 지지 하나, 같은 안 oppose는 철회), typing 만료, WS `seq`·단일 송신 큐, 기획안·제출·자동 제출, 자료 잠금, 디브리핑, 사실 지표, 내부 REST, 입장·시작 전 `/state`, 재발급, 관리자(채용 건 생성·초대), `/assets` 아바타 | P0: 최소 경로·확정·시간 초과·제출·리포트 큐 투입·인증·이어하기, 테스트 API(`/internal/test/sessions` `start_at`·`advance`, `services/test_sessions.py`), `LLM_FAKE`가 api 쪽 설정에 들어감 / P1: 카드 스케줄·초대 재평가·restart / P2: 관리자 생성 연결·동시 5세션 | `docs/api/design.md` 완료 기준(시간 로직은 가짜 시계 단위 테스트), 계약 테스트 C1~C4·C6·C8·C9·C10. WIP(`track/api` c84f337)에는 토론형 테스트가 없으므로 위 테스트를 새로 쓴다 | G-F, scenario-catalog |
| **agent** | G-F(인계 stub), catalog prompts, G-C, agent-spike 결과(3절, S1·S2·S7) | `services/api/app/agent/` 전부(debate·assistant·intent·guard·llm·mcp_client·runner), `services/api/tests/agent/` | 턴 매니저(결정적 노드 + 규칙 0명·`message`일 때만 LLM 화자 선택) + 페르소나 3(DebateState 선주입, 계획 밖 입장이면 재생성 1회 → 고정 문구), 카드 전달(`delivered` 뒤 `record_observation`, 미전달 화자 이어 말하기, 기준안 잠금), AI 합의 채우기(3/4 즉시, 턴 결정 `fill = {option_id, seat}`, fill 노드 전용 분기의 `fill_slot` 한 번에 칸과 공지), 침묵 초대, typing 대기 상한(10초 뒤 재enqueue는 `SessionPorts`), guard, 의도 분류(`confidence`), **어시스턴트 tool-calling 루프**(`search_materials`·`get_material`, 최대 3회, 인용), 비용 관측·하드 상한, assessment 차단(허용 목록·클라이언트 분리), 결정적 LLM 모드(`LLM_FAKE=1`, `FakeLLM` 고정 응답), `AGENT_RUNNER` 기본값 `session` 통일, `ROLE_CONFIG.temperature`를 LLM 래퍼에 연결 | P0: 최소 경로·의도 분류·guard·어시스턴트·`LLM_FAKE` / P1: 카드·초대·합의 채우기 | `docs/agent/design.md` 완료 기준 중 **가짜 MCP·가짜 hub 단위 기준만**(FakeLLM), 계약 테스트 C5. WS·재시작 확인은 web-integrate·e2e | G-F, scenario-catalog |
| **mcp** (debate + assessment) | G-F, G-C, agent-spike 결과(S3) | `services/debate-mcp/`, `services/assessment-mcp/` | debate: 도구 7개(get_debate_state·get_transcript·get_draft·post_message·propose_option·set_stance·fill_slot), 모든 도구 `async def`, 409 코드 전달, `fill_slot{session_id, option_id, seat, content, run_id}` → `{slot, phase, message}`(내부 `POST /slots/fill`, 칸과 공지를 api가 한 트랜잭션으로 저장), 옛 도구 삭제. assessment: record_observation·get_rubric·`get_session_record`·get_transcript_span(앞 5·뒤 3)·get_contributions·`save_evaluation`(멱등 `(session_id, run_id)`, `prompt_versions`·`elements` 포함), 토큰 검사 | P0 | `docs/mcp/design.md` debate·assessment 항목, 픽스처 테스트 | G-F |
| **report-worker** | G-C, catalog 평가표·앵커·평가 프롬프트 | `services/report-worker/` | 리포트 그래프 `collect → aggregate → evaluate → draft → interrupt → finalize`. 평가 에이전트(BARS: 요소별 별도 호출, 차원별 수준·근거 참조·rationale·확신도, 근거 없으면 기록 없음, 형식 오류·근거 부재면 요소 단위 1회 재요청 후 `evaluate_failed`, 확신도 상한은 clamp), 사실 지표 소비, 기여 대조(`contribution_check`), 총점 없음, final은 draft content 그대로, 재시도·DLQ, assessment 클라이언트, thread_id `report:{session_id}:{eval_round}`(`report.approve` 본문에 `eval_round`) | P0 | `docs/worker-infra/design.md` 완료 기준, 계약 테스트 C7, `LLM_FAKE=1`에서 평가 고정 출력 | G-F, scenario-catalog |
| **web-integrate** | G-M 목업, api·agent 병합본 | `apps/web/` 전부 | mock 데이터 원천을 실 REST·WS로 교체(`seq` 공백 시 `/state` 재조회, typing 5초 갱신), 관리자 화면 연결, 15분 데모, State `keyword_options`로 키워드 버튼. WS 재연결·이어하기 확인. 기대 실패 목록의 mock-admin·mock-candidate 줄 정리. `apps/web/e2e/stages/`·`playwright.config.ts`는 e2e 소유 | P0: 지원자 흐름 / P2: 관리자 생성 연결 | design.md 완료 기준을 `NEXT_PUBLIC_MOCK=0`에서 stage-e2e(`LLM_FAKE=1`) 통과로 재확인. 15분 실 스택은 W5-3 `all_five` 1회 | api·agent 병합 |
| **stage-kit** (S3) | api 테스트 API(`start_at`·`advance`), `LLM_FAKE`, 대본 문법(`testing.md`) | `scenarios/e2e/stages/`, `scripts/make_session.py`(`--start-at`), Makefile 타깃 `stage`·`stage-advance`(사전 승인), `scripts/README.md` 해당 줄 | 단계 시드 5개(keyword·problem·solution·proposal·ended), `make stage STAGE= [MIN=15] [LLM=fake\|live]`가 초대 링크·세션 id 출력, `make stage-advance SID= TO=`. 옛 `make_session.py`(요소 선택) 교체. 그래프·워커 단독 실행기는 두지 않는다 | P0 | 단계마다 `make stage`로 만든 세션의 `/state`가 그 단계 시작 상태, `stage-advance TO=deadline` 뒤 시간 초과 채우기 확인(격리 DB·실 스택 `LLM_FAKE`) | api·agent 병합 |
| **e2e** | 계약, 대본 초안(`testing.md`), stage-kit | `tests/e2e/`, `tests/eval/`, `scenarios/e2e/`(`stages/` 제외), `scripts/save_eval_fixture.py`, `tests/playtest/`, **stage-e2e**: `apps/web/e2e/stages/`, `apps/web/playwright.config.ts`, `apps/web/package.json`의 `@playwright/test`(사전 승인), Makefile 타깃 `e2e-stages`·`e2e-stack-up/seed/down`과 `infra/docker-compose.e2e.yml`(사전 승인) | Python 러너(세션 전체·리포트·인증·장애 주입·동시)와 `testing.md` 대본·단언, eval 픽스처(의도 분류 20문장·평가 에이전트·유출 질문)와 세션 기록 저장 스크립트, 옛 대본 삭제. **P0 대본은 `all_five`·`timeout_all`·`honesty_claim`**, 장애 주입 2종(큐 DLQ·LLM 타임아웃), `restart`는 P1, `no_assistant`·동시 실행은 P2. **stage-e2e** spec 7개(entry·keyword·problem·solution·proposal·debrief·admin-report, `silent`·`solo_confirm` 포함)와 영상·trace·스크린샷·HTML 리포트. 러너·대본은 S2 빈 자리부터, stage-e2e는 S3, 실 실행은 S4 | P0: 위 대본 3개·장애 주입 2종·stage-e2e 7개 / P1: `restart` / P2: `no_assistant`·동시 5세션 | `make test-e2e`(mock), `make e2e-stages`(`LLM_FAKE`), 실 스택 `all_five` 15분 1회, `make eval-live` 기록 | 작성: G-C(stage-e2e는 stage-kit). 실행: 서비스 트랙 전부 병합 |
| **fix-\*** | e2e 실패 목록 | 실패 영역 트랙의 소유 경로 | 실패 단언 수정 | — | 해당 단언 통과 | W5-3 |
| **gm-fix** (S2) | `docs/handoff/reviews/gm-uiux-review.md` | `apps/web/components/debate/`, `apps/web/components/admin/`, `apps/web/components/ui/tabs.tsx`, `apps/web/app/globals.css`(인쇄 규칙만) | 실제 화면에도 보이는 항목만: B4~B7, N1·N3·N4·N5·N11·N12·N13. 캡처·mock 전용(B1~B3, N6·N10)은 제외(B1~B3은 report-refresh의 새 캡처로 해소). 재캡처 없음 | P0 | `pnpm test`·`pnpm lint`·빌드, 항목별 확인 | G-M |
| **playtest** (S4, 게이트 아님) | stage-kit 시드(`LLM=live`), 실 스택 | `tests/playtest/records/` | 블라인드 페르소나 4종(지원자 정석·서두름·헤매는, 관리자 채용 담당자)이 단계별로 Claude in Chrome으로 조작, GIF·불편 로그·개선 제안, 요약 표(`testing.md` "playtest"). keyword 정석형 파일럿 1회 뒤 확대 | — | 단계 × 페르소나 기록 + 요약. 반영은 사람이 정함 | stage-kit·web-integrate 병합 |

- W5-1(S2)은 api ∥ agent ∥ gm-fix ∥ report-worker(리뷰)로 돌고, 자리가 비면 e2e 러너·대본을 넣는다. mcp는 병합됐고 rag-mcp 정리는 be-foundation에 흡수됐다.
- 계약 테스트 C1~C10(`docs/common/testing.md`) 배정은 위 완료 기준 열과 같다. 테스트는 happy path 범위(정상 1개 + 계약·평가가 요구하는 실패)만 쓴다.
- 완료 보고에는 검증 방식(mock / 격리 DB / 실 API / 실 LLM)을 적는다. test·lint만으로 실제 연결 완료를 인정하지 않는다.

## 5. 기존 코드·브랜치 정리

| 순서 | 대상 | 처리 | 담당 |
|---|---|---|---|
| C0 (G-D 직후) | 남은 worktree: flow·ui-layout(arch-page·web-kit은 W2 트랙으로 사용 중이라 제외) | ui-layout이 main에 반영됐는지 확인 뒤 `sh scripts/worktree.sh --remove <이름>`, 브랜치 삭제 | 오케스트레이터 |
| C0 | `track/flow`(G1 픽스처, 미병합 4커밋, origin에도 있음) | 대체됨. **사용자 확인 뒤** 로컬·원격 삭제 | 오케스트레이터 |
| C1 | 옛 픽스처(보드·문서·보고·정직 사실) | 삭제·교체 | contracts |
| C2 | web 보드·파트 문서·개인 알림·분업 reducer, `office/` 이름 | 삭제·`debate/`로 이동 | mock-candidate |
| C3 | api 보드·문서·이벤트·자료 지연·재사용·열람 서비스, `agent/session`·`agent/observe`, business-mcp 이름, **해당 옛 테스트** | 코드와 테스트를 함께 삭제·이동 | be-foundation |
| C4 | business-mcp 도구(get_board·send_document·set_division 등) | 삭제·교체 | mcp |
| C5 | 워커의 관찰 레이블·카드 7장·산출물·정직 사실 로직 | 삭제·재작성 | report-worker |
| C6 | `scenarios/missions/planning/`, 옛 e2e 대본(division_refuse·early_submit·assistant_reuse) | 삭제 | scenario-catalog, e2e |
| C7 | `apps/web/mocks/fixtures/office_script.json` | 삭제(`debate_script.json`으로 대체) | mock-candidate |
| C8 | `scripts/README.md` | 토론형 스크립트(seed·make_session·worktree)와 서비스 이름으로 갱신 | be-foundation |
| C9 | `services/api/README.md` | 옛 흐름(보드·문서·reporting) 설명 정리, 토론형 실행법으로 | api |
| C10 | 옛 e2e 기록 `tests/e2e/records/20261021-0711-all_five/`·`20261021-0723-division_refuse/` | 삭제. **완료(debate-docs)** | debate-docs |
| C11 | `docs/review/design-review.html`·`.pdf`, `docs/share/plan-report.html`·`.pdf` | 삭제. **완료(debate-docs)** | debate-docs |

살리는 것: 인증, WS 허브, 큐·report-worker 골격, rag 색인·검색, 채팅 UI·탭·Markdown 뷰어(D20).

## 6. 작업 방식

오케스트레이터는 조율만 하고 개발·리뷰 모두 Claude 서브에이전트다(개발 동시 최대 4, 작성 모델 ≠ 리뷰 모델: api·agent는 Opus 개발 → Sonnet 리뷰, 나머지는 Sonnet 개발 → Opus 리뷰, 오케스트레이터 문서는 Sonnet 리뷰). 트랙은 완료 기준 실행 결과로 보고하고, 리뷰 → 차단 반영 → squash 병합 → 단계 끝 사용자 확인 순으로 간다. 상세는 `docs/dev-process.md` "작업 방식".

## 7. 운영 제약과 범위

- api는 단일 프로세스(세션별 메일박스·WS 송신 큐·스케줄러가 메모리). 실행 중 통합 스택은 한 번에 하나(사용권은 `docs/dev-process.md`).
- 시간: 60분 = 키워드 10 · 문제 상황 18 · 해결책 18 · 기획안 작성 14(이월 유지). 데모·e2e 압축은 **15분**(같은 비율, 시각 오프셋 최소 20초). 시간 로직은 가짜 시계 단위 테스트로 검증하고, 실 스택은 단계 시드·시간 당기기로 단계별로 보며, 처음부터 끝까지 도는 15분 실 스택은 `all_five` 1회다.
- MVP 제외: 기업의 요소 선택(1~5개)과 요소 → 페르소나 결정 규칙, 동조형·발산형 페르소나의 세션 투입(R2, 문서에만 확장으로 남김), 페르소나 입장 즉흥 생성(D3 고도화), 독립 비동기 에이전트(D10 고도화), DM, 웹 검색·scenario·가드 MCP, 두 번째 미션, 리치 에디터·파일 업로드, F-06 회사 문서 관리, F-07 면접 질문 제안, 회사당 둘째 계정, 기업 약관·위탁 안내, 토큰 스트리밍. 현행 F-25 침묵 초대는 MVP에 포함한다(P1).
- 2순위(D21, P2): 기업 채용 건 생성(요소 선택 없음, 세션 길이 등)·초대의 실제 연결, 동시 5세션. api·web-integrate가 P0 완료 기준을 마친 뒤 한다. 15분 데모 모드는 목업(W3)부터 들어간다.
- 후속(G-E 뒤, S5): report-refresh(stage-e2e 스크린샷·playtest GIF로 교체), arch-refresh(arch-page를 최종 구현과 대조해 갱신), 파일럿(사람 참여, PRD 11 기준)은 사용자 일정.
