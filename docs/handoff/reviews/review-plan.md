# 개발 계획 병렬성 리뷰

2026-10-20 · 판정: **현재 계획 그대로의 병렬 착수는 보류. 계약 기준점·완료 조건·소유권을 먼저 정리해야 한다.**

범위: plan·dev-process·handoff·AGENTS와 공용 계약·아키텍처·재설계 triage, 기존 브리프 및 완료 보고의 변경 요청/인수 사항. 구현 소스 검토나 실행 검증은 하지 않았다. 아래 파도와 소유권은 수정 제안이며, 저장소 계획을 변경한 것은 아니다.

안전한 부분도 있다. web-redesign의 mock 작업과 scenario-redesign의 백엔드 작업은 파일 영역을 분리하면 병렬 가능하다. 사용자 mock 확인이 scenario-redesign을 막지 않는다는 결정도 이미 명시돼 있다(`docs/plan.md:43`, `docs/handoff/reviews/review-redesign-triage.md:26`). 이전 리뷰의 이 문제를 다시 미결정으로 취급할 필요는 없다.

## 1. 반드시 고칠 것 — 병렬 착수 차단

### A1. 두 트랙이 출발할 공용 계약이 최신 결정과 다르고, 변경 전파 절차도 상충한다

- 위치: `docs/common/contracts.md:3`, `docs/common/contracts.md:35`, `docs/common/contracts.md:106`, `docs/common/contracts.md:169`, `docs/handoff/reviews/review-redesign-triage.md:12`, `docs/handoff/reviews/review-redesign-triage.md:20`, `docs/plan.md:72`, `docs/handoff.md:55`.
- 한 줄 근거: triage는 시작 시 보드 생성·division.confirmed·reporting 재접속·채널 잠금 해제를 확정했지만 계약은 분업 확정 후 보드 생성·in_progress만 resume·reporting 팀 채널 제한을 유지하고, 트랙 지침도 “멈춤”과 “계속 진행”으로 갈린다.
- 필요한 조치: redesign-docs의 종료 조건에 **triage→contracts 예시 JSON→공용 픽스처의 일치**를 넣고 그 커밋을 두 트랙의 공통 시작점으로 고정한다. 병렬 중에는 “트랙이 영향 경로·요청/응답 예시를 제출 → 오케스트레이터가 결정 → 지정 문서 pane이 계약 반영 → 영향 트랙이 같은 커밋을 반영하고 재검증”으로 단일화한다. 독립 작업만 계속하고, 미확정 계약을 쓰는 작업과 해당 완료 판정은 대기해야 한다.

### A2. scenario-redesign의 필수 테스트에 후속 agent-session 구현이 들어 있어 완료 의존이 역전된다

- 위치: `docs/plan.md:22`, `docs/plan.md:24`, `docs/plan.md:61`, `docs/agent/design.md:154`, `docs/handoff/reviews/review-redesign-triage.md:14`, `docs/handoff/reviews/review-redesign-triage.md:15`.
- 한 줄 근거: scenario-redesign은 약속 이행 재계산·무관한 편집의 비충족까지 통과해야 끝나는데 그 행동 판정은 후속 agent-session의 observe/finalize 소유이고, agent-session은 scenario-redesign 완료를 기다린다.
- 필요한 조치: scenario 단계는 API·저장·PATCH·워커 계산을 고정 입력으로 증명하고, 실제 Graph가 그 입력을 만드는 검증은 agent-session에 배정한다. 아래 6건 배정표처럼 선행 계약 테스트와 후행 행동 테스트를 분리해야 하며, mock 결과를 실제 에이전트 통과로 보고하면 안 된다.

### A3. 새 트랙과 공용 파일의 쓰기 권한이 소유권 표에서 닫히지 않는다

- 위치: `docs/plan.md:23`, `docs/plan.md:29`, `docs/plan.md:30`, `docs/plan.md:57`, `docs/plan.md:66`, `docs/plan.md:67`, `docs/plan.md:68`, `docs/plan.md:72`, `docs/frontend/design-system.md:72`.
- 한 줄 근거: web-integrate는 소유권 행이 없고 web-redesign 종료 후 ui만 polish로 이관되며, scenario의 서비스 전체 이관과 foundation 파일 변경 금지가 동시에 남아 package/lock·공용 conftest·infra 변경의 실행 주체가 불명확하다.
- 필요한 조치: 다음을 파일 단위로 명시한다. web-integrate에는 앱·업무 컴포넌트·lib/api.ts·lib/ws.ts·연결 테스트를, polish에는 ui 내부·globals.css·brand만 준다. web-redesign의 새 UI 의존성 추가에 필요한 package.json·pnpm-lock.yaml도 사전 허용한다. scenario에는 재설계 기간의 API conftest·모델·서비스 설정 변경 권한을 명시하되 루트 tests/conftest.py·루트 설정·compose·env.example·Makefile·공용 문서에는 한 명의 변경 담당을 정한다. docs-final/service도 산출 경로·자산·루트 README·purge의 소유권을 표에 넣는다. “재설계 기간 이관”이 일반 금지보다 우선하는 정확한 파일 목록과 종료 시점을 적어야 한다.

### A4. agent-assistant는 선행 조건과 라우터 연결 소유권 없이 시작 가능 상태다

- 위치: `docs/plan.md:25`, `docs/plan.md:43`, `docs/plan.md:61`, `docs/plan.md:62`, `docs/plan.md:67`, `docs/handoff.md:39`, `docs/handoff/reports/agent-min-report.md:64`.
- 한 줄 근거: assistant의 의존은 이미 끝난 agent-min·prompts뿐이어서 scenario의 services/api 전체 소유 기간에도 착수할 수 있고, 실제 assistant 라우터 연결은 assistant 폴더 밖 candidate.py 수정이 필요하다고 핸드오프에 남아 있다.
- 필요한 조치: assistant 착수에 scenario 병합·API 소유권 반환을 추가하고, candidate.py의 assistant 연결 훅은 scenario가 먼저 제공하거나 assistant에 해당 변경만 명시적으로 넘긴다. agent-session이 고칠 llm·guard·mcp_client는 assistant가 import하므로 공개 함수·반환형·허용 도구·비동기 연결 수명을 먼저 동결한다. 공용 `tests/agent/conftest.py`의 쓰기 담당은 하나로 두고 assistant는 자기 테스트/픽스처만 쓴다.

### A5. web-integrate와 e2e의 착수·완료·병합 조건이 구분되지 않아 후속 구현을 기다리며 막힌다

- 위치: `docs/plan.md:23`, `docs/plan.md:26`, `docs/plan.md:27`, `docs/plan.md:43`, `docs/handoff.md:30`, `docs/handoff/reports/agent-min-report.md:50`.
- 한 줄 근거: web-integrate는 scenario만 의존하면서 실제 문서 왕복·보고·리포트 완료를 요구하고, e2e는 “전부” 의존인데 같은 파도에 착수해 polish보다 먼저 병합하도록 되어 있으며, 현재 다음 행동에는 web-integrate가 빠져 있다.
- 필요한 조치: web 연결 코드는 scenario 병합 뒤 병렬 개발하되 **실제 한 세션 완료 판정은 agent-session·assistant 병합 뒤**로 둔다. e2e도 러너 작성과 통합 실행을 분리하고, 최종 통과는 polish를 포함한 실행 대상 커밋을 고정한 뒤 받는다. 현재 agent-min의 최소 inject는 실제 동료 산출물을 만들지 않으므로 이를 완성 에이전트 대용으로 삼으면 안 된다. handoff의 현재 다음 행동·진행 표에도 web-integrate와 이 두 완료 관문을 넣는다.

### A6. 새 대본·프롬프트의 인수 시점과 소유권 반환이 실행 계획에 빠져 있다

- 위치: `docs/plan.md:22`, `docs/plan.md:24`, `docs/plan.md:60`, `docs/plan.md:67`, `docs/plan.md:69`, `docs/handoff/reviews/review-redesign-triage.md:26`, `docs/handoff/reports/agent-min-report.md:68`.
- 한 줄 근거: scenario 범위에는 대본까지 있고 e2e-runner도 scenarios/e2e를 소유하며, prompts는 scenario 뒤 문구를 다듬지만 새 prompts 단계가 파도에 없어 소비자가 어느 카탈로그·해시·대본을 받아야 하는지 불분명하다.
- 필요한 조치: scenario 종료 때 새 미션·7카드 레이블·고정 의견·선점/팀장 DM 픽스처를 인수한 커밋과 catalog_version을 발급한다. 대본의 초기 변경도 scenario가 한다면 그 병합 시 scenarios/e2e를 e2e-runner에 넘긴다고 명시한다. 후속 prompts 다듬기는 런타임 소비자 착수 전에 끝내거나 별도 변경 요청으로 취급한다. 문구 변경도 해시가 바뀌므로 색인·신규 채용 건·기대 픽스처를 같은 버전으로 다시 만들어야 한다.

### 최소 테스트 6건의 추천 배정

요구 근거: `docs/plan.md:22`, `docs/handoff/reviews/review-redesign-triage.md:26`. 테스트를 늘리기보다 아래 각 정상/실패 사례를 해당 완료 기준에 배정한다.

| 사례 | scenario-redesign이 혼자 증명할 것 | agent-session이 증명할 것 | 화면·최종 인수 |
|---|---|---|---|
| 보드만으로 분업 확정 | 담당 없는 5행→PUT→division/task_events/WS·동료 자극 저장 | 보드 자극으로 work_notes·동료 담당 갱신 | web-integrate의 실제 보드 조작, e2e 확인 |
| 카드 전 계획 | 시작 전후 결정 시각·보드 이력 보존, 평가표 입력 계약 | 0분부터의 계획 창에 먼저 정한 계획 포함 | e2e 기대 점수 확인 |
| 창 밖 약속 이행 | 관찰의 promise_kept PATCH·멱등, 워커가 갱신값 소비 | 종료 finalize에서 실제 메시지로 재계산 | e2e의 다음 창 이행 대본 |
| 무관한 편집 | revisions 보존, target_applied=false 입력이면 점수 미충족 | 편집 사실과 변경 반영 사실을 구분해 aux 생성(FakeLLM) | e2e의 리포트 항목 확인 |
| 문서 제공 실패 | MCP 오류·이벤트 실패 저장·워커 기록 없음 사유 | send 재시도·카드 실패·의존 항목 처리 | e2e 장애 주입 |
| reporting 재접속 | resume·JWT·state.deadline_at·허용 채널 | 보고 분류와 종료 연계 | web-integrate 재연결, e2e 확인 |

## 2. 고치면 좋은 것

- **B1. scenario-redesign의 크기를 내부 관문으로 관리:** `docs/plan.md:22`는 미션·스키마·API·MCP·RAG·worker를 한 트랙에 묶어 주 경로를 독점한다. 무리하게 여러 작성자로 나누기보다 “미션/스키마 → API/도구 계약 검증 → 워커/픽스처 인수”를 중간 보고로 나누고, 다른 트랙은 확정된 경계만 사용하게 한다.
- **B2. 공용 인프라의 테스트 격리와 통합 사용권을 구분:** `docs/handoff/reports/foundation-report.md:23`은 API 임시 DB, `docs/handoff/reports/worker-report.md:9`·`:15`는 워커 임시 스키마·큐, `docs/handoff/reports/rag-mcp-report.md:41`은 RAG 임시 DB를 이미 보고한다. 따라서 schema.sql 수정만으로 다른 worktree의 격리 테스트가 깨진다고 단정할 수 없다. 이 격리 규칙을 `docs/dev-process.md:29`에 승격하고, 실제 스택에는 사용자·worktree·커밋·DB/schema·큐·카탈로그 버전을 기록한 단일 사용권을 둔다. 공용 스택 재기동·스키마 적용·seed/색인은 사용권 보유 작업에서만 실행한다.
- **B3. 문서 트랙의 “전부”를 구체적 입력으로 바꾸기:** `docs/plan.md:29`·`:30`의 docs-final/service와 `:31`의 파일럿 순서를 확정한다. docs-service는 최종 카탈로그·UI 커밋·승인된 mock/실세션 스크린샷 묶음을 받으면 작성할 수 있고 docs-final 완료를 기다릴 이유는 없다. docs-final의 최종 검증은 파일럿·120분 기록·실행법·purge 결과까지 받아야 한다. 사람의 “설명할 수 있음” 확인은 담당자와 질문 목록을 정하고, 트랙 자체 검증은 수치·문구 대조와 링크/렌더 확인으로 분리한다.
- **B4. 재설계 착수와 인수 완료 상태를 기록:** `docs/handoff.md:26`은 문서 진행 중, `:77`은 리뷰 반영 완료로 되어 있고 `:94`부터의 진행 표에는 web-integrate/docs-service가 없다. 과거 절은 참고로 유지하되 현재 표에는 계약 기준 커밋·인수자·대기 사유를 넣어 이전 4요소 지침을 새 브리프로 재사용하지 않게 한다(`docs/handoff.md:105`).
- **B5. pane 수와 리뷰 슬롯을 구분:** `AGENTS.md:34`·`docs/plan.md:35`는 개발 pane 4개지만 `docs/handoff.md:36`·`:105`는 동시 pane 4개라고 쓴다. 개발 4개와 리뷰용 pane의 계산법을 통일하고 UI/UX→반영→Codex→사용자 확인 순서를 web-redesign의 명시적 관문으로 기록한다. 사용자 확인을 기다리는 동안 scenario는 계속할 수 있다.
- **B6. 새 브리프에는 재현 가능한 입력을 넣기:** `docs/handoff.md:53`의 형식에 기준 커밋·선행 산출물·허용/금지 파일·승인된 공용 변경·계약 변경 요청 형식·테스트 격리명·스택 사용 조건·검증 명령·후속 인수자를 추가한다. 기존 브리프의 머신별 `/private/tmp/...` 절대경로는 예시 형식만 참고하고, 새 브리프에는 저장소 상대 보고 경로를 쓴다(`docs/handoff/briefs/brief-agent-min.md:6`, `:18`).
- **B7. 테스트 통과와 실제 연결 증거를 분리:** 과거에도 worker usage는 워커 전송 테스트만 통과하고 API 저장이 빠졌으며(`docs/handoff/reports/worker-report.md:12`), 화면/worker의 필드 불일치로 수정 라운드가 필요했다(`docs/handoff/reports/web-admin-report.md:37`, `docs/handoff/briefs/brief-worker-fix.md:3`). 완료 보고에는 mock/격리 DB/실 API/실 LLM 중 무엇으로 검증했는지 표시하고, 소비자 입력 대조가 필요한 항목은 고정 JSON을 양쪽에서 확인한다.
- **B8. 모델 대체 규칙을 하나로:** `docs/plan.md:78`·`:79`는 개발 Claude·리뷰 Codex, Codex 한도 때 다른 Claude 리뷰지만 `docs/handoff.md:68`은 Claude 개발 한도 때 Codex 개발로 바꾼다. 같은 모델이 작성·리뷰하지 않는 원칙을 유지하면서 예외의 적용 조건을 하나로 적는다.

## 3. 추천 파도 표

W0~W2와 agent-min은 완료된 것으로 두고 재실행하지 않는다(`docs/handoff.md:7`). 표의 숫자는 **동시 개발 pane 수**이며, 리뷰 pane은 B5에서 정한 별도 규칙을 따른다. 아래는 새 트랙을 크게 늘리지 않고 현재 트랙의 착수와 최종 인수 시점을 구분한 제안이다.

| 파도 | 트랙·동시 개발 pane | 병합/최종 인수 순서 | 시작 전에 받아야 할 것 |
|---|---|---|---|
| P0 | redesign-docs 마감·계약 정합화 (1) | 단독 | triage 최종 결정, 현재 plan/계약 차이 목록, 공용 JSON 예시·변경 담당 |
| P1 | web-redesign ∥ scenario-redesign (2) | docs 기준점 위에서 각각 리뷰; web은 UI/UX→수정→Codex→사용자 확인, scenario는 자기 계약 테스트 통과 후 병합 가능 | 같은 계약 커밋, web 의존성/lock 수정 권한, scenario의 스키마·API·도구·공용 fixture 권한, 별도 worktree/env |
| P1 종료 관문 | prompts 인수 및 소유권 반환; 필요시 문구 다듬기 (0~1) | 미션·도구·워커 산출과 프롬프트 검증 완료 후 다음 파도 | 7카드/레이블·fixed_opinions·선점/DM 픽스처, catalog_version·색인, 대본 초기본, API/WS 실 응답 예시, 공통 helper 인터페이스 |
| P2 | agent-session ∥ agent-assistant ∥ web-integrate ∥ web-polish (최대 4) | agent-session·assistant 병합 → web-integrate 실제 세션 인수; polish는 props 불변·파일 분리하에 독립 병합, 마지막 합친 상태에서 화면 재확인 | scenario 병합, 사용자 mock 확인(최소 session/integrate), assistant 라우터 훅, helper 시그니처·테스트 픽스처 쓰기 담당, web-integrate/polish의 겹치지 않는 파일 목록 |
| P3 | e2e-runner 및 필요한 fix-* (합계 4 이하, 실제 스택은 1개) | 러너 준비 → P2 합본의 단언 실행 → 도메인 소유자의 수정·재검증 → 최종 기록 | P2 실행 커밋, AGENT_RUNNER=session, env/포트·스택 사용권, 6건 인수표, 새 대본·live/장애 검증 범위 |
| P4 | pilot·120분 실세션 증거 수집 (1, 사람 참여) | 결과/필요 수정 확정 후 최종본 기준점 고정 | 짧은 e2e 통과본, 설문·근거 대조표, 실세션 실행 담당·기록 경로·스택 시간 예약 |
| P5 | docs-final ∥ docs-service (2) | 경로가 분리되면 순서 무관; 공용 목차/링크는 한 트랙만 작성 | 최종 PRD·미션/계약·코드 커밋, 화면 캡처 묶음, 120분/파일럿 기록, 평가 증거, 문서별 산출/자산 경로 |

P2에서 web-integrate와 polish를 병렬로 두려면 전자는 업무 화면·연결 로직, 후자는 ui 내부·CSS·brand만 수정해야 한다. 이 경계를 지키기 어렵다면 둘만 직렬화한다. e2e 러너의 계약 기반 작성은 P2의 빈 슬롯에서 앞당길 수 있으나, **통합 통과와 병합 완료는 P2 합본 뒤**로 유지한다. 문서 초안도 먼저 준비할 수 있지만 최종본 인수와 구분한다.

### 인수 때 명시할 공용 파일 담당

| 파일/영역 | 추천 쓰기 담당·이관 |
|---|---|
| contracts·공통 설계·decisions·plan·handoff | 오케스트레이터가 요청을 모으고 지정 문서 pane 하나가 작성; 영향 트랙에 같은 기준 커밋 전달 |
| schema.sql·API models/services/routers/scheduler·business-mcp·RAG 색인 키·worker | P1 scenario; 종료 후 도메인별로 명시 반환, app/agent는 P2 agent 담당 |
| 루트 tests/conftest.py·루트 설정·Makefile·compose·env.example | 지정 공용 변경 담당 한 명; 필요한 변경을 P0/P1에서 먼저 반영, 동시 예외 수정 금지 |
| API 공용 conftest·tests/fixtures/contracts | P1 scenario가 새 계약에 맞춰 갱신 후 동결; P2는 읽기, 변경 필요 시 담당자에게 요청 |
| tests/agent/conftest.py·llm/guard/mcp_client | P2 agent-session 한 명; assistant는 동결 인터페이스를 import하고 별도 테스트 파일 사용 |
| scenarios/e2e·tests/e2e·tests/eval·make_session.py | 초기 대본을 넘겨받은 뒤 e2e-runner; 다른 트랙은 자기 서비스 테스트에 사례를 둠 |
| web package/lock·UI props | P1 web-redesign 사전 허용; P2 전에 확정, polish는 props 변경 금지 |
| README·docs/share/plan-report.*·docs/share/architecture/·purge | docs-final; purge는 코드 산출물이므로 자체 검증 범위를 브리프에 명시 |
| docs/share/service/와 그 캡처/자산 | docs-service; docs-final과 공용 파일을 동시에 만들지 않음 |

## 4. 오케스트레이터 체크리스트

### 기동 전

- [ ] 해당 트랙의 선행 **병합 커밋**·계약 커밋·catalog_version·실제 받아야 할 파일을 적고, 이전 보고의 미처리 요청을 반영/보류/폐기로 분류한다. `docs/handoff.md:44`의 과거 요청을 그대로 새 요구로 복제하지 않는다.
- [ ] 현재 활성 트랙끼리 쓰기 경로를 대조한다. 공용 conftest·package/lock·schema·infra·문서·스크린샷 자산까지 포함하고, 재설계 이관의 우선순위를 브리프에 적는다.
- [ ] worktree·브랜치·Herdr 탭·역할 모델을 확인하고, worktree에 env 두 파일과 필요한 로컬 스킬을 준비한다. 비밀값은 출력하지 않고 포트/호스트 설정만 확인한다(`docs/handoff.md:14`, `:18`, `:28`).
- [ ] 일반 테스트는 임시 DB/스키마/큐로 격리되고 LLM은 mock인지 확인한다. 실제 스택 작업에는 사용자·커밋·시간을 배정하고, 다른 worktree에서 seed·스키마 변경·스택 재기동을 하지 않게 알린다.
- [ ] 완료 기준마다 자기 소유 코드로 가능한 검사와 후속 통합 인수를 구분하고, 막힌 계약에 의존하지 않는 작업만 계속하도록 한다.

### 완료 보고 확인

- [ ] 기준 커밋·수정 파일·실행 명령/결과·검증 방식(mock/실 API/live)·재현 가능한 기록 경로가 있다. test/lint만으로 실제 연결 완료를 인정하지 않는다.
- [ ] 변경 요청마다 요청자·담당자·영향 소비자·해결 커밋 또는 대기 사유가 있다. API/WS 예시와 공유 fixture를 소비자가 같은 형태로 읽는지 확인한다.
- [ ] 6건의 테스트 배정표와 트랙별 계약/행동/화면 인수가 채워져 있고, 미래 에이전트 구현을 가짜 결과로 대체한 항목이 없다.
- [ ] web-redesign은 실제 mock 화면 UI/UX 리뷰→수정→Codex→사용자 피드백 반영이 기록됐다. 사용자 확인 대기 중 scenario는 계속할 수 있으나 session/integrate는 정해진 관문을 지킨다.
- [ ] 임시 DB·스키마·큐·백그라운드 앱을 정리했고, 후속 인수자에게 새 API·대본·프롬프트·helper·변경된 catalog_version을 전달했다.

### 병합 전

- [ ] 최신 main 위로 rebase한 **그 트랙 브랜치에서** make test·make lint와 해당 트랙의 추가 계약 검증을 실행했다(`docs/dev-process.md:42`). 이후 새 변경이 생겼으면 영향 검증을 다시 한다.
- [ ] 소유권 밖 수정·미승인 공용 변경·env/키·임시 산출물이 없고, squash 대상과 리뷰된 최종 변경이 일치한다. REVIEW 파일은 로컬 결과로만 둔다.
- [ ] 생산자와 소비자의 조합이 필요한 경우 실제 인수 검사를 마쳤다. P2 합본 뒤 web 세션, polish 뒤 최종 e2e, 최종 코드 뒤 실세션/캡처 순서를 지킨다.
- [ ] main의 스키마·카탈로그·실행 스택 버전 전환이 필요하면 단일 사용권 안에서 수행하고, 아직 실행 중인 다른 작업이 없는지 확인한다. 새 해시의 색인·신규 채용 건을 준비한다.
- [ ] 진행 표에 병합 커밋·검증 증거·소유권 반환·다음 트랙 입력을 기록한 뒤 worktree·브랜치·탭을 정리한다. docs-final/service에는 같은 최종 기준점과 별도 산출 경로를 전달한다.
