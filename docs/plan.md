# 개발 계획

혼자 개발하되 Herdr pane으로 도메인별 Claude 개발 pane을 병렬로 띄우고, 끝난 트랙은 Codex가 리뷰한다. pane마다 git worktree와 브랜치(`track/<이름>`)를 쓰고, 리뷰 통과 후 오케스트레이터가 main에 병합한다. 리뷰 반영(2026-10-20): 공용 기반을 먼저 한 트랙이 만들고, 최소 종단 흐름을 M1에 당긴다.

## 마일스톤

| 단계 | pane | 범위 | 의존 | 완료 기준 |
|---|---|---|---|---|
| M0 | (오케스트레이터) | 문서, 계약, 카탈로그, 회사 문서, 대본, compose, 스키마 | — | 완료 |
| M0.5 | foundation | 서비스 5개의 최소 앱(Dockerfile, `/health`, 의존성·lockfile), api 공용 기반(config, db, models, auth, SessionService, scenario, hub, queue, masking, AgentRunner+Fake), web 기본(Next 앱, 토큰, 공용 컴포넌트 props만, mocks/ 골격), 테스트 픽스처 골격 | M0 | `make up` 전부 healthy(api·MCP `/health`, web `/api/health`, worker heartbeat 파일), `make infra-up` 후 로컬 `app.run`이 8000·8001 둘 다 응답, SessionService 단위 테스트, 조립 결과가 scenario-model.md 수치와 일치, Fake runner로 메시지→내부 저장→hub 브로드캐스트 단위 테스트(WS·rag 검색은 M1 트랙) |
| M1 | prompts | `scenarios/prompts/` 페르소나 프롬프트(카탈로그 persona의 values·must·must_not_preempt 반영), common_rules, guard_patterns.yaml, 카드 brief·label_texts·debrief 문구, 관찰 레이블 예시, 선점 유도 픽스처 문장. 코드 없음 | M0 | 리뷰 통과 |
| M1 | api-admin | /admin, /internal 라우터(리뷰 조정 본문, 산출물·조정 병합, 목록 합계) | foundation | 계약 예시대로, 격리·검증·409 테스트, memo_required·already_reviewed |
| M1 | api-candidate | /s, /sessions, WS, 스케줄러, 공개·만료·재발행 | foundation | 6분 세션 시계대로, 재시작 재실행, ack·재연결 |
| M1 | business-mcp | 도구 10개 | foundation | Inspector, 오류 코드, 멱등 전달 |
| M1 | rag-mcp | 색인·검색·공개 필터 | foundation | 검색 응답, 차단, 재색인 |
| M1 | web-admin | 관리자 5화면(채용 건 생성 시 평가표 항목 미리보기, 리포트 평가표 조정 포함) | foundation(토큰·컴포넌트 props) | mock으로 전 화면, 7상태, draft/final 배지, 조정·메모 |
| M1 | web-office | 지원자 화면과 가상 오피스 | foundation | mock으로 전 화면, ack·진행 표시·재연결 |
| M1 | worker | 리포트 그래프(평가표 규칙 계산 포함), 큐 2종, 재시도·DLQ | foundation | draft 멈춤→approve 재개→final, DLQ, rubric.evaluate 단위 테스트 |
| M1 끝 | agent-min (agent-session 트랙의 1단계) | respond 노드 + MCP 클라이언트 + guard로 최소 종단 흐름 | api-admin, api-candidate, business-mcp, rag-mcp 병합 | 메시지→그래프→rag→post→WS 연결 테스트 |
| M1.5 | redesign-docs | PRD·docs·카탈로그 구조를 2026-10-20 재설계(인성 5요소·카드 7장·문서 주고받기·미션 단위)로 반영 | — | `docs/handoff/reports/redesign-sweep.md` 체크리스트 전부 처리 |
| M1.5 | web-redesign | **UI를 먼저 본다.** mock으로 새 오피스(레일·대화↔열린 문서·내 문서/보드/자료/어시스턴트)와 관리자 생성(요소 5개)·리포트(카드 소섹션)를 구현. 구현이 끝나면 **UI/UX 전문가 페르소나(Claude) 화면 리뷰**(실제 mock 화면·스크린샷·흐름) → 반영 → Codex 코드 리뷰 → 사용자가 mock으로 경험을 확인한 뒤 다음 단계 | redesign-docs(설계 문서), design-direction·design-system | frontend/design.md 완료 기준(mock 전 흐름, 보드 끌어 놓기, break-ui), UI/UX 리뷰 차단 항목 0 |
| M1.5 | scenario-redesign | `scenarios/missions/planning/` 카탈로그(요소→cards[], 5요소 meaning·how_we_see, fixed_opinions, 적응성 카드 새 내용)·프롬프트·대본, `scenarios/version.py`(미션 폴더 전체 해시), schema.sql, api(조립·문서/보드/reporting·SessionService·scheduler·내부 API·관리자 record/regenerate/notes), business-mcp 도구(send_document·get_shared_documents·set_division), rag 색인 키, worker 카드 단위 평가표·summary·facts, 픽스처·테스트 | redesign-docs | make test·lint 통과, 조립 결과가 scenario-model.md 수치와 일치, 최소 테스트 6건(보드만으로 분업 확정, 카드 전 계획, 창 밖 약속 이행, 무관한 편집, 문서 제공 실패, reporting 재접속) 통과 |
| M2 | web-integrate | web-redesign mock을 실 API·WS에 연결. 사용자 mock 확인 뒤 시작 | web-redesign(확인됨), scenario-redesign | 실 API로 문서 공유→열람→통합→제출→보고→리포트→전체 기록까지 한 세션이 화면에서 돈다 |
| M2 | agent-session | 전이표 전체(reporting 포함), observe(규칙·분류·정직 사실 대조), 카드 7장 실행, 복구, 체크포인터 | scenario-redesign, prompts | agent/design.md 완료 기준 |
| M2 | agent-assistant | 어시스턴트 그래프 | agent-min 병합(llm·guard·mcp_client를 import), prompts | 공개 문서만 인용, 한도 |
| M2 | web-polish | web-redesign 뒤 다듬기: 모션(animate·review-animations), break-ui | web-redesign | review-animations·break-ui 통과 |
| M3 | e2e-runner | 러너, 대본 5개, 장애 주입, 근거 정확성 픽스처, 기록. live 테스트 결과를 "모델 상향 판단 자료"(레이블 정확도·규칙 준수·카드 실패율)로 보고 | 전부 | 단언 전부 통과, 기록 커밋, 상향 판단 자료 1장 |
| M3 | fix-* | 실패 영역별 | e2e | 해당 단언 통과 |
| M4 | docs-final | README 실행법, **최종 보고서**(`docs/share/plan-report.html·pdf`: 작업 흐름·변경 이력이 아니라 **최종본 기준**으로 처음부터 다시 씀), **아키텍처 문서 묶음**(`docs/share/architecture/`: 한 장이 아니라 ① 전체 구성도 ② 티어별(배포, Trust Boundary) ③ 레이어별(논리 계층, 책임·금지·인터페이스) ④ 런타임(시퀀스 3개, 동기·비동기 경로) ⑤ 연결(MCP·색인) ⑥ Harness 8요소, `docs/assignment/reference-architecture.md`의 6뷰·범례·번호 표·금지 사항·Layer/Tier 표를 따름. 목차 페이지에서 뷰별로 들어가고 각 뷰는 한 화면에 그림 하나와 표 하나), 평가표 근거 표(증거마다 커밋 해시), 120분 실세션 기록, `scripts/purge.py` | 전부 | 새 환경에서 README만으로 기동. 보고서와 아키텍처 문서에 "이전에는", "변경했다" 같은 이력 표현이 없음 |
| M4 | docs-service | **서비스 설명서·기획서**(`docs/share/service/`, HTML 묶음, docs-final과 병렬). 보고서가 아니라 **서비스 소개 자료**다: 팀원이 "이 서비스가 무엇이고, 어떤 시나리오로 돌아가고, 어떻게 평가하는가"를 이해하고 남에게 설명할 수 있게 쓴다. 성과·일정·작업 이력은 쓰지 않는다. **글보다 그림 중심**: 실제 화면 스크린샷(mock 또는 실 세션)과 흐름도(사용자 흐름·세션 타임라인·요소별 장면)를 먼저 두고 글은 캡션 수준으로. 요소 5개는 각각 "장면 스크린샷 → 동료가 필요로 하는 것 → 지원자 행동 예 → 기록 → 평가표"를 한 화면 그림으로. ① 한 장 요약(문제·초점 "같이 일하기 좋은 사람"·원칙) ② 사용자 흐름(담당자: 가입→채용 건→초대→리포트 검토→면접 / 지원자: 초대→동의→대기→세션→디브리핑) ③ 기능 흐름(화면별, 문서 주고받기·보드·보고) ④ 2시간 세션 타임라인(카드 7장, 120분 시각, 동료·팀장이 하는 말의 골격) ⑤ 인성 요소 5개 각각: 뜻·어떤 장면에서·동료가 무엇을 필요로 하고·지원자의 어떤 행동을·어떤 기록으로·평가표 4항목·미선택 시 ⑥ 리포트 샘플 읽는 법(점수 규칙, 기록 없음, 담당자 조정) ⑦ 원칙과 하지 않는 것(실력 비점수화, 합격·순위 없음, 상황 비공개, 공정성). 최종본 기준으로만 쓰고 이력 표현 없음. 디자인은 design-system.md 토큰 | 전부(최종 카탈로그·PRD) | 팀원이 이 문서만 읽고 세션 시나리오와 평가 방식을 설명할 수 있음. 모든 수치·문구가 카탈로그·PRD 최종본과 일치 |
| M4 | pilot (오케스트레이터+사람) | 지원자 역할 3명·담당자 역할 2명 파일럿: 설문, 근거 대조표, 면접 질문 채택 수, 가격 질문 | docs-final 전 | PRD 11 잠정 기준 대비 결과를 `docs/pilot.md`에 기록 |

## 전환 계획 (CX-02·CX-12, 2026-10-21)

PRD와 계약은 문서 턴에서 먼저 바뀌었다. 구현은 아래 게이트를 통과한 뒤에만 시작한다. 세부 근거는 `docs/decisions.md`의 2026-10-21 절과 `docs/prd-change-proposals.md`.

| 트랙 | 범위 | 소유 파일 | 선행 조건 | 완료 기준 |
|---|---|---|---|---|
| flow-docs (오케스트레이터 1명) | PRD·docs/common·decisions·proposals·fixes 정합. PRD.html은 PRD.md와 같은 커밋에서 `sh build/build.sh`로 재생성 | 위 문서 전부 | 없음 | G1 커밋, grep 정합 검사 통과 |
| **G1 계약 기준 커밋** | contracts 예시 JSON(tasks 생성, 섹션 담당, division/share, finish, reporting, session.end_available)을 `tests/fixtures/contracts/`에 반영. TBD 필드는 픽스처에 넣지 않음 | 공용 담당 | flow-docs | 생산자·소비자 양쪽이 같은 픽스처를 읽음 |
| flow-docs-followup (문서 1명, 개발과 병렬) | G1 이후 역할별 상세 설계·테스트 문서를 계약에 맞춘다. 공용 계약은 수정하지 않고 변경요청만 올린다. 아래 "문서 후속 트랙" 참조 | `docs/api/design.md`, `docs/agent/design.md`, `docs/mcp/design.md`, `docs/worker-infra/design.md`, `docs/frontend/{design-direction,design,design-system}.md`, `docs/common/testing.md`, `docs/common/harness.md`, `docs/handoff/change-requests/` | G1 | G2(백엔드 설계 동기화) → G3(프론트·테스트 설계 동기화) 기준 커밋 |
| flow-api | 빈 보드, 할 일 생성·수정, 섹션 담당 PUT, division/share 검사(섹션 담당 5개 + division_min), finish, 완료 시각 기준 5분 자동 종료, 한서윤 DM 보고 kind 분류 | `services/api/app/` 중 routers/candidate·internal, services/session, scheduler | G1, scenario-redesign 병합 뒤(api 쓰기 충돌 회피) | api 단위 테스트, 5분 fallback 재시작 복구 테스트 |
| flow-agent | 한서윤 확인 답장 노드, 01:50 요청의 채널 분기(완료 전 팀 채널·조기 완료 DM), 분업 자극 갱신 | `services/api/app/agent/` 전부 | G1, flow-api의 내부 division·complete 계약 동결 | FakeLLM 단위 테스트, 판정 발언 금지(F-24) 검사 |
| flow-web | 완료 확인 창, 한서윤 DM 이동 안내, 종료 버튼(`end_available`), 빈 보드, 섹션 담당 UI | `apps/web/app/s/`, `components/office/` | G1, web-redesign 사용자 mock 확인 뒤(web 소유권 충돌 회피) | mock 전 흐름, break-ui |
| flow-verify (e2e-runner) | 대본 갱신: DM 보고, 5분 자동 종료, 조기 완료, 빈 보드 분업. 최소 테스트 6건의 reporting 항목 재배정 | `tests/e2e/`, `scenarios/e2e/` | flow-api·flow-agent·flow-web 병합 | e2e mock 통과 |
| **progress-channel (독립)** | active_runs(`/state`)와 WS `agent.progress`의 이름·상태 고정. 흐름 전환과 파일을 공유하지 않음 | 계약(공용 담당), hub·state(api-candidate), `lib/ws.ts`(web-office) | G4 계약 커밋 별도. CX 트랙을 막지 않음 | 계약 픽스처 일치, 재연결 후 active_runs 복원 |
| 개선 후보 required-card-failure (변경 없음) | 필수 카드 3회 실패 → 세션 실패(현행 규칙 유지). 이번 전환에서 바꾸지 않음 | — | 없음 | 별도 제안으로 M3 이후 검토 |

**게이트와 충돌 회피 규칙**
- 계약 변경은 G1 커밋으로만 들어간다. 트랙은 계약 파일을 쓰지 않고 요청만 올린다.
- services/api 쓰기는 flow-api 하나, app/agent 쓰기는 flow-agent 하나. 두 트랙이 같은 파일을 고치면 중단하고 오케스트레이터가 나눈다.
- flow-web과 web-redesign이 겹치면 web-redesign이 끝난 뒤에만 flow-web을 시작한다.
- 검증 순서: 문서 grep(옛 표현 "5행", "보고 메시지 저장 시각", "팀장 보고 요청", "제출 시 보고 요청") → G1 픽스처 → api 단위 → agent FakeLLM → web mock → e2e mock.

**문서 후속 트랙 (flow-docs-followup) 상세**

- **단일 소유 원칙.** 공용 계약 파일(`PRD.md`, `docs/common/contracts.md`, `docs/common/data-model.md`, `docs/common/scenario-model.md`, `docs/common/architecture.md`, `docs/common/rubric.md`, `docs/decisions.md`, `docs/plan.md`, `docs/prd-change-proposals.md`, `docs/candidate-experience-fixes.md`)은 flow-docs 한 담당만 수정한다. flow-docs-followup은 이 파일들을 읽기만 하고 고치지 않는다.
- **변경 범위.** flow-docs-followup은 위 표의 역할별 설계·테스트 문서만 쓴다. `services/`, `apps/`, `scenarios/`, `tests/`(fixtures 포함)는 건드리지 않는다.
- **시작 기준.** G1 커밋(계약 예시 JSON과 `tests/fixtures/contracts/` 반영) 이후. 개발 트랙과 같은 시점에 시작하며 개발 트랙의 시작을 기다리지 않는다.
- **G2 (백엔드 설계 동기화).** `docs/api`, `docs/agent`, `docs/mcp`, `docs/worker-infra`가 G1 계약과 같은 엔드포인트·필드·상태 전이·오류 코드를 쓰도록 맞춘다. 완료 판정: 각 문서 끝의 정합 체크리스트(계약 항목 대응표, 상태 전이 대응, TBD 목록)가 모두 채워지고 다른 담당이 한 번 검토. 완료 시 G2 커밋을 남기고 flow-api·flow-agent 브리프에 적는다.
- **G3 (프론트·테스트 설계 동기화).** `docs/frontend/*`와 `docs/common/testing.md`, `docs/common/harness.md`를 G2와 G1 계약에 맞춘다. 완료 판정: 같은 체크리스트 통과, testing.md의 C1·C6·3d 등 시나리오 단언이 새 흐름(완료 → DM 보고 → 답장 → 종료, 5분 fallback)과 일치. 완료 시 G3 커밋을 남기고 flow-web·flow-verify 브리프에 적는다.
- **변경 요청(CR) 절차.** 구현 중 계약과 다른 사실이 나오면 개발 트랙은 `docs/handoff/change-requests/CR-<날짜>-<트랙>-<번호>.md`에 다음을 적고 멈춘다: 어긋난 항목, 구현된 값, 제안 값, 영향 트랙. 이 파일은 개발 트랙이 쓰는 유일한 문서 산출물이다. flow-docs가 채택·기각을 결정한다. 채택되면 flow-docs가 G1(계약 변경)을 새로 만들고, flow-docs-followup이 G2/G3를 같은 커밋 번호 체계로 다시 맞춘다. 개발 트랙은 새 기준 커밋을 rebase해서 받는다.
- **동기화 규칙.** 개발 트랙은 자기 브랜치에서 설계 문서를 직접 고치지 않는다. 구현이 계약과 맞지 않으면 CR을 올리고, 문서는 기준 커밋(G2/G3)으로만 바뀐다. 구현과 문서가 어긋난 채로 병합하지 않는다.
- **충돌 회피.** flow-docs-followup과 개발 트랙은 파일 소유권이 겹치지 않는다. 같은 문서를 두 담당이 고쳐야 하면 오케스트레이터가 나눈다.
- **검증 순서.** G1 픽스처 확인 → G2 문서 체크리스트 → 개발 트랙 단위 테스트(계약 픽스처 기준) → G3 문서 체크리스트 → web mock → e2e mock.

**구현 전 결정 항목 (PRD 16과 일치)**
1. 분업 최소 조건 유지 여부(CX-04): 현행 유지, 변경은 별도 승인.
2. 할 일 담당과 섹션 담당 불일치 방지 규칙.
3. 섹션 담당 확정 뒤 재지정 규칙.
4. 한서윤 확인 답장 실패 처리.
5. 5분 자동 종료와 답장 지연의 관계(답장이 늦으면 버튼 없이 종료됨).
6. 01:50 보고 요청 카드 문구. 채널 분기(완료 전 팀 채널, 조기 완료 DM)는 설계 선택으로 decisions 2026-10-21에 기록됐고 사용자 확인 대기.
7. 보고 인정 채널(반영값은 완료 뒤 한서윤 DM만).
8. 기본 작업 흐름 예시(자료 탭)의 MVP 포함 여부.

## 병렬 작업 방식

동시에 띄우는 개발 pane은 **최대 4개**다. 각 파도(wave)는 pane 4개 이하로 띄우고, 끝난 트랙부터 리뷰·병합한 뒤 다음 트랙을 채운다.

| 파도 | 동시 개발 pane | 병합·최종 인수 순서 | 시작 전에 받아야 할 것 |
|---|---|---|---|
| W0~W2, agent-min | 완료 | — | — |
| P0 | redesign-docs 마감·계약 정합화 (1) | 단독. **종료 조건: triage → contracts 예시 JSON → `tests/fixtures/contracts/` 공용 픽스처가 일치**하고 그 커밋이 다음 파도의 공통 기준점 | triage 최종 결정 |
| P1 | web-redesign ∥ scenario-redesign (2) | 각자 리뷰 후 병합. web은 UI/UX 페르소나 → 수정 → Codex → 사용자 mock 확인. scenario는 자기 계약 테스트 통과 후 병합 가능(사용자 확인이 막지 않음) | 같은 계약 기준 커밋, web의 package/lock 수정 사전 허용, scenario의 스키마·API·도구·공용 픽스처 권한, 별도 worktree·env |
| P1 관문 | prompts 인수 (0~1) | scenario 병합 시 7카드 레이블·fixed_opinions·선점/팀장 DM 픽스처·catalog_version·대본 초기본을 인수하고 `scenarios/missions/`·`scenarios/e2e/` 소유권을 prompts·e2e-runner에 반환 | scenario 병합 커밋 |
| P2 | agent-session ∥ agent-assistant ∥ web-integrate ∥ web-polish (최대 4) | agent-session·assistant 병합 → web-integrate "실제 한 세션" 인수. polish는 ui 내부·globals.css·brand만 건드려 독립 병합. 마지막 합본에서 화면 재확인 | scenario 병합, 사용자 mock 확인(session·integrate 착수 조건), assistant 라우터 훅(scenario가 candidate.py에 제공), llm·guard·mcp_client 공개 함수·반환형·허용 도구 동결, 겹치지 않는 파일 목록 |
| P3 | e2e-runner + fix-* (합계 4 이하, 실제 스택 1개) | 러너 작성은 P2 빈 슬롯에서 앞당겨도 됨. **통합 통과·병합은 P2 합본 뒤** | P2 실행 커밋, AGENT_RUNNER=session, 스택 사용권, 6건 인수표 |
| P4 | pilot·120분 실세션 (1, 사람 참여) | 결과 반영 뒤 최종본 기준점 고정 | 짧은 e2e 통과본, 설문·근거 대조표, 스택 시간 예약 |
| P5 | docs-final ∥ docs-service (2) | 경로 분리, 공용 목차·링크는 docs-final만 | 최종 PRD·카탈로그·코드 커밋, 화면 캡처 묶음, 120분·파일럿 기록. docs-service는 캡처 묶음만 있으면 먼저 시작 가능 |

**최소 테스트 6건 배정** (늘리지 않고 완료 기준에 나눠 넣는다)

| 사례 | scenario-redesign(고정 입력으로 증명) | agent-session(실제 그래프가 입력을 만듦) | 화면·최종 인수 |
|---|---|---|---|
| 빈 보드 분업 공유 (2026-10-21 기준) | 할 일 0개 → 섹션 담당 draft 5개 PUT → POST division/share → snapshot·division.confirmed·task_events(target=section_owner)·동료 자극 저장. 할 일이 없어도 확정됨 | 보드 자극으로 work_notes·동료 담당 갱신 | web-integrate 실제 보드 조작, e2e |
| 카드 전 계획 | 시작 전후 결정 시각·보드 이력 보존 | 0분부터의 계획 창에 먼저 정한 계획 포함 | e2e 기대 점수 |
| 창 밖 약속 이행 | observations PATCH·멱등, 워커가 갱신값 소비 | finalize에서 실제 메시지로 재계산 | e2e 다음 창 이행 대본 |
| 무관한 편집 | revisions 보존, target_applied=false면 미충족 | FakeLLM으로 편집 사실과 반영 사실 구분 aux | e2e 리포트 항목 |
| 문서 제공 실패 | MCP 오류·이벤트 failed 저장·워커 document_missing | send 재시도·카드 failed·의존 항목 처리 | e2e 장애 주입 |
| reporting 재접속 | resume·JWT·state.deadline_at·허용 채널 | 보고 분류와 종료 연계 | web-integrate 재연결, e2e |

규칙:
- **기준 커밋.** 파도마다 "시작 전에 받아야 할 것"의 커밋 해시를 브리프에 적는다. 병렬 중 계약 변경은 "트랙이 영향 경로·요청/응답 예시를 제출 → 오케스트레이터 결정 → 지정 문서 pane이 contracts·픽스처 반영 → 영향 트랙이 같은 커밋을 반영하고 재검증"으로만 한다. 트랙은 미확정 계약에 의존하는 작업과 그 완료 판정만 대기하고 독립 작업은 계속한다.
- **완료 보고의 검증 방식 표시.** mock / 격리 DB / 실 API / 실 LLM 중 무엇으로 검증했는지 적는다. test·lint만으로 실제 연결 완료를 인정하지 않는다. 생산자·소비자가 같은 고정 JSON(`tests/fixtures/contracts/`)을 읽는지 양쪽에서 확인한다.
- **트랙마다 Herdr 탭 하나.** 탭은 그 트랙의 worktree를 cwd로 만들고(`herdr tab create --workspace $HERDR_WORKSPACE_ID --cwd <worktree> --label <트랙>`), 탭 안에 개발 pane(Claude)과 리뷰 pane(Codex)을 좌우로 둔다. 여러 트랙을 한 탭에 몰지 않고, 오케스트레이터 탭에는 작업 pane을 늘리지 않는다. 트랙이 병합되면 탭째 닫는다.
- 한 pane은 트랙 하나, 트랙이 끝나면 pane을 닫는다. 리뷰 pane은 같은 탭 오른쪽에 띄우고 결과는 worktree의 `REVIEW.md`(추적 안 함)에 쓰게 한다.
- 파도 안에서 서로 파일을 공유하지 않는다(소유권 표). 공유 파일이 필요하면 foundation 변경 요청으로 올린다.
- 병합 전 트랙 브랜치를 `main` 위로 rebase한 상태에서 `make test`와 `make lint`가 통과해야 한다.
- 오케스트레이터는 파도마다 "띄움 → 완료 보고 확인 → 리뷰 → 병합 → 다음" 기록을 `docs/handoff.md`의 진행 표에 남긴다.

## 파일 소유권

| 트랙 | 소유 | 비고 |
|---|---|---|
| foundation | `services/*/Dockerfile`, `pyproject.toml`·lockfile 전부(pytest 설정 포함), `services/api/app/{main,run,config,db,auth,hub,queue,masking}.py`, `app/models/`, `app/services/`(reuse.py 제외), `app/agent/runner.py`, 각 MCP·worker의 패키지 진입점(`__main__.py`, `/health` 또는 heartbeat만), `apps/web/{Dockerfile,package.json,app/layout.tsx,app/globals.css,app/api/health/route.ts,components/ui/,lib/api.ts}`, `apps/web/mocks/`(admin.ts·office.ts·fixtures/admin·fixtures/office 제외), `scenarios/version.py`, `scripts/seed.py`, `infra/docker-compose.dev.yml`, `tests/conftest.py`, `tests/fixtures/`, `services/api/tests/conftest.py` | 이후 변경은 오케스트레이터 승인. MCP·worker 진입점은 foundation 병합 후 각 트랙 소유로 넘어감 |
| api-admin | `app/routers/{admin,internal}.py`, 해당 테스트 | |
| api-candidate | `app/routers/{candidate,ws}.py`, `app/scheduler.py`, `app/services/reuse.py`(estimate_reuse), 해당 테스트 | `app/services/context.py`의 reuse 훅(`reuse_estimator`) 연결은 이 트랙이 한다 |
| prompts | 재설계 기간에는 `scenarios/missions/`를 prompts 포함 scenario-redesign이 소유. 그 뒤 문구 다듬기(brief·labels·label_texts·debrief·meaning·how_we_see·fixed_opinions)만 prompts 트랙 | 인수 조건: 레이블 7세트·선점 금지·팀장 DM 규칙 검증 픽스처 통과 |
| agent-session | `app/agent/{session,observe,llm,guard,mcp_client}/` | agent-assistant는 llm·guard·mcp_client를 import만 |
| agent-assistant | `app/agent/assistant/` | |
| business-mcp, rag-mcp, worker | 각 `services/<이름>/` | |
| web-admin | `apps/web/app/admin/`, `components/admin/`, `mocks/admin.ts`, `mocks/fixtures/admin/` | ui 컴포넌트 내부는 수정하지 않음 |
| web-office | `apps/web/app/s/`, `components/office/`, `lib/ws.ts`, `mocks/office.ts`, `mocks/fixtures/office/` | |
| web-redesign | `apps/web/app/`, `components/`(ui 포함), `globals.css`, `lib/ws.ts`, `mocks/` 전부 | 재설계 기간 동안 web-admin·web-office·foundation의 web 소유권을 한 트랙이 받는다. 끝나면 web-polish로 ui·globals.css 이관 |
| scenario-redesign | `scenarios/missions/`(prompts 포함), `scenarios/catalog.yaml`(삭제·이관), `scenarios/version.py`, `scenarios/e2e/` 초기 대본, `infra/db/schema.sql`, `services/api/`(조립·라우터·모델·SessionService·scheduler·queue 경계·`services/api/tests/conftest.py`·assistant 라우터 훅), `services/business-mcp/`, `services/rag-mcp/`의 색인 키, `services/report-worker/`, `tests/fixtures/contracts/`, 관련 테스트 | P1 동안 foundation·api-*·business-mcp·rag-mcp·worker 소유권을 한 트랙이 받는다. **종료 시 반환**: `app/agent/`는 agent-session, `scenarios/missions/` 문구는 prompts, `scenarios/e2e/`는 e2e-runner, 나머지는 도메인 트랙. 내부 관문 3개(미션·스키마 → API·도구 계약 검증 → 워커·픽스처 인수)로 중간 보고 |
| 공용 변경 담당(오케스트레이터 지정 1명) | 루트 `tests/conftest.py`, 루트 `pyproject`·lockfile, `Makefile`, `infra/docker-compose*.yml`, `infra/.env.example`, `docs/common/`·`docs/decisions.md`·`docs/plan.md`·`docs/handoff.md` | 파도 안에서 한 pane만 쓴다. 필요한 변경은 P0·P1에서 먼저 반영. 트랙은 요청만 올린다 |
| agent-session | 위에 더해 `tests/agent/conftest.py`, `app/agent/{llm,guard,mcp_client}/`의 공개 함수·반환형 변경 | agent-assistant는 동결된 인터페이스를 import만 하고 자기 테스트 파일만 쓴다 |
| web-integrate | `apps/web/app/`, `components/{admin,office}/`, `lib/api.ts`, `lib/ws.ts`, 연결 테스트, `mocks/` 정리 | P2. web-polish와 파일을 나눈다(polish는 ui 내부·globals.css·brand만). 경계가 어려우면 둘을 직렬화 |
| web-polish | `components/ui/` 내부, `globals.css`, `public/brand/` | web-redesign 병합 후 이관. props 변경 금지 |
| docs-final | `README.md`, `docs/share/plan-report.*`, `docs/share/architecture/`, `scripts/purge.py`, 공용 목차·링크 | P5 |
| docs-service | `docs/share/service/`와 그 캡처·자산 | P5. docs-final과 공용 파일을 동시에 만들지 않음 |
| e2e-runner | `tests/e2e/`, `tests/eval/`, `scenarios/e2e/`, `scripts/make_session.py` | |

## 병렬 작업 규칙
- 트랙은 `docs/common/contracts.md`와 foundation 소유 파일을 바꾸지 않는다. 필요하면 보고하고 멈춘다.
- 다른 트랙 폴더를 수정하지 않는다. 필요한 것이 없으면 mock을 자기 폴더에 둔다.
- 완료 시 자기 완료 기준을 직접 실행하고 명령과 결과를 보고한다. 연결 테스트는 M1 끝에 한다.
- 커밋은 자기 브랜치에만. main 병합은 오케스트레이터.

## 모델 운영
- 개발 Claude, 리뷰 Codex(gpt-6.1-sol). 같은 모델이 만들고 검토하지 않는다. 오케스트레이터가 Agent 도구로 띄우는 Claude 리뷰 서브에이전트(사용자 관점·UI/UX 페르소나)는 Opus로 띄운다(작업 에이전트는 기본 모델).
- 한도 소진 규칙 하나: Codex 한도면 리뷰를 개발과 다른 Claude 모델로, Claude 한도면 개발을 Codex(편집 모드)로 바꾸고 리뷰를 다른 모델(gpt-6-astra 또는 복구된 Claude)로 바꾼다. 어느 경우든 작성 모델 ≠ 리뷰 모델.
- "동시 pane 4개"는 **개발 pane** 수다. 리뷰 pane은 트랙 탭 안에 별도로 두고 수에 넣지 않는다. UI/UX 페르소나 리뷰·사용자 mock 확인은 web-redesign의 관문이며 그동안 scenario-redesign은 계속한다.
- 끝난 pane은 바로 닫는다. 맥락이 바뀌면 새 pane. 오케스트레이터는 브리프·기동·병합·판단만 한다.

## 운영 제약
- api는 단일 프로세스(세션 Lock이 메모리). 수평 확장은 범위 밖, 향후 분리 지점은 AgentRunner 경계.

## MVP 제외
F-06 회사 문서 관리·승인, F-07 면접 질문 제안, F-25 무응답 확인, 회사당 둘째 계정, 기업 약관·위탁 안내, 생성 화면의 평가표·타임라인 미리보기, 받은 문서 버전 비교, 최종본 append, 세션 길이 선택 UI, 타임라인 미리보기, LLM 페르소나 지원자 e2e, 리치 에디터, 공유 문서 동시 편집·인라인 코멘트(문서는 주고받기 모델), 파일 업로드, 두 번째 미션(개발), 색인 도구의 임의 경로·업로드, 복수 디자인안 비교, 다크 모드. (MVP에 들어온 것: F-05 근거→전체 기록 링크, 전체 기록 읽기 전용 화면, 샘플 리포트, 인쇄·PDF 내보내기, 리포트 재생성, 종료 설문 2문항)

## 확장 후보 (M3 이후, 시간이 남으면)
- 세션 내 승인: 동료가 문서를 보내기 전에 주담당 확인을 구함(`send_document` 앞 interrupt, 수락·거절로 같은 thread 재개). 리포트 승인이 끝난 뒤에만 고려한다.
- 두 번째 미션(개발, 산출물은 설계 문서형): `scenarios/missions/<id>/` 폴더 하나 추가로 붙는다.

## worktree
```
sh scripts/worktree.sh api-admin      # ../Day-0_zaeho.worktrees/api-admin 에 track/api-admin
sh scripts/worktree.sh --remove api-admin
```
