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
| M4 | docs-final | README 실행법, **최종 보고서**(`docs/share/plan-report.html·pdf`: 작업 흐름·변경 이력이 아니라 **최종본 기준**으로 처음부터 다시 씀), **아키텍처 한 페이지**(`docs/share/architecture.html`, 전환 계획의 arch-page가 만든 것을 최종 구현과 대조해 갱신만), 평가표 근거 표(증거마다 커밋 해시), 120분 실세션 기록, `scripts/purge.py` | 전부 | 새 환경에서 README만으로 기동. 보고서와 아키텍처 문서에 "이전에는", "변경했다" 같은 이력 표현이 없음 |
| M4 | docs-service | **서비스 설명서·기획서**(`docs/share/service/`, HTML 묶음, docs-final과 병렬). 보고서가 아니라 **서비스 소개 자료**다: 팀원이 "이 서비스가 무엇이고, 어떤 시나리오로 돌아가고, 어떻게 평가하는가"를 이해하고 남에게 설명할 수 있게 쓴다. 성과·일정·작업 이력은 쓰지 않는다. **글보다 그림 중심**: 실제 화면 스크린샷(mock 또는 실 세션)과 흐름도(사용자 흐름·세션 타임라인·요소별 장면)를 먼저 두고 글은 캡션 수준으로. 요소 5개는 각각 "장면 스크린샷 → 동료가 필요로 하는 것 → 지원자 행동 예 → 기록 → 평가표"를 한 화면 그림으로. ① 한 장 요약(문제·초점 "같이 일하기 좋은 사람"·원칙) ② 사용자 흐름(담당자: 가입→채용 건→초대→리포트 검토→면접 / 지원자: 초대→동의→대기→세션→디브리핑) ③ 기능 흐름(화면별, 문서 주고받기·보드·보고) ④ 2시간 세션 타임라인(카드 7장, 120분 시각, 동료·팀장이 하는 말의 골격) ⑤ 인성 요소 5개 각각: 뜻·어떤 장면에서·동료가 무엇을 필요로 하고·지원자의 어떤 행동을·어떤 기록으로·평가표 4항목·미선택 시 ⑥ 리포트 샘플 읽는 법(점수 규칙, 기록 없음, 담당자 조정) ⑦ 원칙과 하지 않는 것(실력 비점수화, 합격·순위 없음, 상황 비공개, 공정성). 최종본 기준으로만 쓰고 이력 표현 없음. 디자인은 design-system.md 토큰 | 전부(최종 카탈로그·PRD) | 팀원이 이 문서만 읽고 세션 시나리오와 평가 방식을 설명할 수 있음. 모든 수치·문구가 카탈로그·PRD 최종본과 일치 |
| M4 | pilot (오케스트레이터+사람) | 지원자 역할 3명·담당자 역할 2명 파일럿: 설문, 근거 대조표, 면접 질문 채택 수, 가격 질문 | docs-final 전 | PRD 11 잠정 기준 대비 결과를 `docs/pilot.md`에 기록 |

## 전환 계획 (지원자 흐름 재정의, 2026-10-21)

기준은 `docs/handoff/briefs/brief-flow-docs-2.md`의 확정 결정 F1~F12와 리뷰가 남긴 문제 3건이다. 문서가 먼저 바뀌고(G0), 공용 계약 픽스처가 고정된 뒤(G1) 기능 구현을 시작한다. 계약과 무관한 화면 구조 작업과 CX-10 조사는 지금 바로 병렬로 시작한다.

### 게이트

| 게이트 | 내용 | 통과 기준 |
|---|---|---|
| **G0 문서** | `track/docs-flow`에서 PRD.md(+PRD.html 재생성)·`docs/common/*`·`docs/decisions.md`·`docs/candidate-experience-fixes.md`·역할별 설계 문서(`docs/{api,agent,mcp,worker-infra,frontend}/`, `docs/common/{testing,harness}.md`)·이 계획·handoff를 F1~F12와 리뷰 문제 3건(contracts의 동료 할 일 doing/done 갱신, architecture의 "같은 tasks를 채운다", rubric의 보고 10분·`response_minutes`)에 맞춘다 | 커밋 → herdr의 Codex 리뷰 pane 통과(차단 0) → main 병합. grep 정합 검사: `reporting`, `end_available`, 종료 버튼(`finish`), `5분 fallback`, `response_minutes`, `팀장 보고 요청`, `tasks 5행`이 현행 흐름 설명에 남지 않음 |
| **G1 계약 픽스처** | `contracts` 트랙이 G0 계약대로 `tests/fixtures/contracts/`와 `tests/fixtures/README.md`를 갱신한다: 할 일 생성(섹션 필수), 빈 보드 State, 섹션 담당 draft, 분업안 공유 성공·실패(위반 섹션·할 일 목록), 제출 요청(메시지 선택)·응답(completed), 한서윤 DM `kind=report` 메시지와 고정 답장, 10:50 DM 메시지, 오피스 시각 필드, 정직 사실 입력. 오피스 시각 변환 순수 함수 `services/api/app/services/office_clock.py`(+단위 테스트)도 이 트랙이 만들고 시그니처를 고정한다 | `tests/contract_shape.py` 검사가 새 픽스처로 통과. 새 픽스처 때문에 깨지는 기존 소비자 테스트를 "기대 실패 목록"(테스트 이름 → 담당 기능 트랙)으로 보고. 이 커밋이 `track/flow`의 첫 커밋이 된다 |

- **통합 브랜치 `track/flow`.** G1 커밋은 main이 아니라 통합 브랜치 `track/flow`에 둔다(기대 실패가 있는 상태로 main에 넣지 않는다). 기능 트랙은 `track/flow`에서 갈라지고, 리뷰 통과 후 오케스트레이터가 `track/flow`에 squash 병합한다. 각 병합은 기대 실패를 늘리지 않고 자기 몫을 지운다. 기대 실패 0 + `make test`·`make lint`·`make test-e2e`(mock) 통과 시 `track/flow`를 main에 병합한다.
- 계약 변경은 G0·G1 커밋으로만 들어간다. 구현 중 계약과 어긋나면 `docs/handoff/change-requests/CR-<날짜>-<트랙>-<번호>.md`(어긋난 항목, 구현 값, 제안 값, 영향 트랙)를 쓰고 그 분기만 멈춘다. 문서 담당이 채택하면 계약·픽스처를 같은 커밋으로 고치고 영향 트랙이 rebase한다. 개발 트랙은 설계 문서를 직접 고치지 않는다.

### 지금 시작하는 트랙 (계약 변경과 무관)

| 트랙 | 범위 | 소유 파일 | 선행 조건 | 완료 기준 |
|---|---|---|---|---|
| **ui-layout** | 프론트만, mock 데이터. ① CX-05 자료 Markdown 서식 뷰어(제목·목록·표·강조, 읽기 폭) ② CX-08 메인 영역 탭 전환(대화·내 문서·보드·자료·어시스턴트, 채널 목록·시각 표시 유지, 작업 탭에서 새 메시지 배지) ③ CX-13·CX-06 기본안(보드 상태별 요약·가로 배치, 긴 내용 펼침·접힘, 자료↔내 문서 이동). 데이터 형태(types·mocks의 필드)는 바꾸지 않는다 | `apps/web/components/office/` 중 `office-view.tsx`·`library.tsx`·`doc-viewer.tsx`·`conversation.tsx`·`my-docs.tsx`·`assistant-panel.tsx`·`board.tsx`(배치만)와 새 레이아웃·Markdown 컴포넌트, 관련 테스트. Markdown 라이브러리 추가 시 `apps/web/package.json`·lockfile(사전 승인) | 없음 | mock(`NEXT_PUBLIC_MOCK=1`)으로 세션 전 흐름이 탭 구조에서 동작, 자료 표·목록이 서식으로 보임, `pnpm test`·`pnpm lint` 통과. Claude Opus UI/UX 리뷰 차단 0 → Codex 리뷰 → **main 병합** |
| **investigate-cx10** (완료, `track/investigate-cx10` 5367ba7) | 읽기 전용. 자료 공개 질문에 이도현이 다른 작업 현황으로 답한 원인(질문 분류 경로, 응답 생성에 들어가는 대화·자료·공개 예정 맥락, 프롬프트)을 찾아 수정 범위(프롬프트·컨텍스트 주입·응답 검증)와 계약 변경 필요 여부를 정한다 | `docs/handoff/reports/investigate-cx10.md` 하나 | 없음 | 완료. 원인: LLM 분류기가 자료 공개 질문을 `progress_query`로 분류 → 진행 템플릿 응답, 잘못된 진행 문구가 `work_notes.progress`에 남아 반복. 계약 변경 불필요(`harness.md` Context 허용 목록 한 줄은 G0 문서에서 처리). 수정은 flow-agent·flow-scenario 범위에 넣음 |

- **ui-layout은 web 기능 트랙보다 먼저 main에 병합한다.** `board.tsx`·`candidate-flow.tsx`·`office-view.tsx` 충돌을 피하기 위해 flow-web은 ui-layout 병합 뒤 `track/flow`를 main 위로 rebase한 다음 시작한다. ui-layout은 `candidate-flow.tsx`의 동작(보드 저장·제출 흐름)을 바꾸지 않는다.

### G0 직후 문서 트랙 (구현과 병렬)

| 트랙 | 범위 | 소유 파일 | 선행 조건 | 완료 기준 |
|---|---|---|---|---|
| **arch-page** | `docs/share/architecture.html`을 **한 페이지**로 다시 만든다. `docs/assignment/reference-architecture.md`의 6뷰(① 전체 구성도 ② 티어별·Trust Boundary ③ 레이어별(책임·금지·인터페이스) ④ 런타임 시퀀스(동기·비동기 경로) ⑤ 연결(MCP·색인) ⑥ Harness 8요소)를 범례·번호 표와 함께 한 페이지 안에 이해하기 쉬운 순서로 담는다. 별도 폴더 `docs/share/architecture/` 묶음은 만들지 않는다. G0 문서(새 흐름) 기준, 이력 표현 없음, 디자인은 design-system.md 토큰 | `docs/share/architecture.html`과 그 자산 | G0 main 병합 | 6뷰가 한 페이지에 모두 있고 구성 요소·흐름·상태 이름이 G0 문서와 일치, 외부 의존 없이 열림, Codex 리뷰 차단 0 → main 병합. M4 docs-final은 최종 구현과 대조해 갱신만 한다 |

### 기능 트랙 (G1 이후)

| 트랙 | 범위 | 소유 파일 | 선행 조건 | 완료 기준 |
|---|---|---|---|---|
| **flow-scenario** | F7 킥오프·이도현 팀 채널 첫 인사(짧게, 분업 유도 없음)·시작 DM 인사 제거, F11 회의록 한 줄 맥락, F8 팀장·동료 문구의 시각 표현을 오피스 시각("10:00쯤 공유")으로, F4 10:50 DM 고정 문구와 카드 정의(보고 요청 카드 대체), F5 정직 평가표 4항목(시간 항목은 단순 사실 항목), F6 금지 문구 패턴 데이터, F9 행동 유도 문구 제거. CX-10: `prompts/colleague.md` 7·8절(진행 질문 범위 축소, 자료 상태 질문 응답), `prompts/fixtures`에 CX-10 케이스, 킥오프 예정 시각 변수를 오피스 시각 포맷으로. 새 catalog_version 발급 | `scenarios/missions/planning/`(cards·mission·persona·prompts·documents·prompts/fixtures) | G1 | 조립 결과가 scenario-model.md 수치와 일치, 프롬프트 픽스처 검사 통과, 금지 문구가 10:50 카드 밖 문구에 없음, CX-10 픽스처 케이스 통과. **기능 트랙 중 가장 먼저 `track/flow`에 병합**하고 catalog_version을 다른 트랙에 알린다 |
| **flow-api** | F1 `tasks.section_part_no` NOT NULL·`POST /sessions/{id}/tasks` 섹션 필수, F2 빈 보드 시작·섹션 담당 draft·분업안 공유 시 전체 검증(섹션 담당 5개 + division_min, 위반 섹션·할 일 목록 반환), F3 제출(최종본 + 선택 메시지 → 한서윤 DM `kind=report` 저장 → 고정 답장 "받았어요, 수고하셨어요." → 즉시 `completed`), 2시간 자동 제출(메시지 없음 → completed), `reporting`·`finish`·`end_available`·5분 fallback 제거, F8 State에 오피스 시각 필드, 내부 API·business-mcp 도구(get_board·set_division·division share)를 G1에 맞춤 | `infra/db/schema.sql`, `services/api/app/` 중 `routers/`, `services/`(office_clock.py는 import만), `scheduler.py`, `models/`, `services/api/tests/`(`tests/agent/` 제외), `services/business-mcp/` | G1 | api 단위 테스트(빈 보드 → 할 일 생성 → 공유 성공 1건, 위반 공유 422와 위반 목록, 섹션 없는 생성 422, 제출 → DM 저장·고정 답장·completed, 자동 제출 → completed, completed 재접속 → 디브리핑), business-mcp 계약 픽스처 테스트, 기대 실패 목록의 자기 몫 해소 |
| **flow-agent** | F4 10:50 DM 카드 실행(이미 제출했으면 보내지 않음, 팀 채널 재촉 없음), 보고 요청 카드·채널 분기·확인 답장 노드 제거, F6 LLM 생성 팀장·동료 메시지의 결정적 금지 문구 검사(재생성 1회 → 실패 시 안전 문구), F7 채널 역할(시작 DM 인사 없음), F5 정직 관찰 근거를 제출 메시지 + 10:50 DM 이후 한서윤 DM 메시지로 한정, 분업 자극을 섹션 담당·스냅샷 기준으로(할 일 0개 정상 경로), F8 발화의 시각 표현에 office_clock 사용. CX-10: `session/classify.py`에서 문서를 지칭하는 질문은 `progress_query` → `question`으로 강등, `session/nodes.py`에 결정적 '자료 상태' 메모 주입(미공개 문서 제목과 킥오프 예정 시각만, 지연 내용 누설 없음), 프롬프트 조립에서 progress_query 범위 축소, 팀장 페르소나에도 같은 처리 | `services/api/app/agent/` 전부, `services/api/tests/agent/` | G1. 완료 판정 전 flow-scenario 병합본으로 rebase | FakeLLM 단위 테스트(10:50 DM 발송·제출 후 미발송, 금지 문구 재생성 → 안전 문구, 할 일 0개 분업 확정 자극, 정직 근거 메시지 선택, 자료 공개 질문 → question 분류·자료 상태 메모로 응답·`work_notes.progress` 오염 없음), 판정 발언 금지(F-24) 검사 통과 |
| **flow-worker** | F5 정직 평가표 4항목 계산(근거 = 제출 메시지 + 10:50 DM 이후 DM 메시지, 보고 시간 기준 없음), 계획성 지표를 섹션 담당 기준으로, 리포트 문구에서 보고 대기·종료 버튼 흔적 제거 | `services/report-worker/` | G1 + flow-scenario 병합(평가표 항목 정의) | `rubric.evaluate` 단위 테스트(정직 4항목 정상 1건, 제출 메시지 없음 1건), draft→approve→final 기존 테스트 유지 |
| **flow-web** | F2 보드: 빈 보드에서 할 일 생성(섹션 선택 필수)·담당 지정·섹션 담당, 필수 담당 조건 처음부터 표시, 분업안 공유 → 실패 시 실제 위반 섹션·할 일 강조(마지막 편집 카드에 오류 붙이지 않음). F3 완료 → 한서윤에게 보내기 창(최종본 첨부, 선택 메시지 입력란, "보내면 수정할 수 없어요"만, 안내·예시 문구 없음) → 디브리핑, 보고 대기 배너·종료 버튼 제거. F8 상단 "오피스 시각 09:23 · 마감 11:00 · 1시간 37분 남음", 채팅 타임스탬프·자료 공개 예정·마감 경고를 같은 시계로. F9 공지·빈 상태 문구는 기능 설명만. mock 픽스처를 G1에 맞춤 | `apps/web/app/s/`, `apps/web/components/office/`, `apps/web/lib/{api,ws}.ts`, `apps/web/mocks/`, `apps/web/e2e/` | G1 + ui-layout main 병합 | mock 전 흐름(빈 보드 → 할 일 생성 → 공유 실패 강조 → 수정 → 공유 → 문서 → 보내기 → 디브리핑), break-ui, `pnpm test`·`pnpm lint`. Claude Opus UI/UX 리뷰 차단 0 → Codex 리뷰 |
| **flow-verify** | e2e 대본 갱신: 빈 보드 분업(division_refuse 포함), 조기 제출(early_submit, 메시지 유무), 10:50 DM 응답, 자동 제출, 재시작. 최소 테스트 6건 배정 갱신. 실 스택 1회(브라우저 `apps/web/e2e/session.mjs`는 flow-web 소유이므로 실행만) | `tests/e2e/`, `tests/eval/`, `scenarios/e2e/`, `scripts/make_session.py` | flow-scenario·flow-api·flow-agent·flow-worker·flow-web 전부 `track/flow` 병합 | `make test-e2e`(mock) 통과, 실 스택 6분 세션 1회 통과 기록 |

- 쓰기 경로는 겹치지 않는다. `services/api/app/agent/`는 flow-agent만, 나머지 `services/api/`·schema·business-mcp는 flow-api만, `scenarios/missions/`는 flow-scenario만 쓴다. 두 트랙이 같은 파일을 고쳐야 하면 멈추고 오케스트레이터가 나눈다.
- 각 트랙의 테스트는 dev-process.md의 happy path 범위(정상 1개 + 계약·평가가 요구하는 실패)만 쓴다. 위 완료 기준 한 줄에 테스트 하나다.

### 플레이테스트 (T3부터, 병합 게이트 아님)

| 트랙 | 범위 | 소유 파일 | 선행 조건 | 완료 기준 |
|---|---|---|---|---|
| **playtest** | 에이전트가 처음 온 지원자(주담당)로 **실제 웹 화면**에 브라우저 자동화로 참가해 UI/UX 어색함·작업 불편·개선점을 직접 겪고 제안한다. **블라인드**: 코드·PRD·설계 문서를 읽지 않고 초대 링크와 화면에 보이는 것만 쓴다. 대본 없이 목표+성향만 준다: 정석형 / 서두름(조기 제출)형 / 헤매는 형(안내를 덜 읽고 질문이 많음). 선택으로 세션 뒤 담당자 성향 에이전트가 리포트 검토 화면을 같은 방식으로 체험. 세션은 `scripts/make_session.py`로 10~15분·요소 2~3개(6분은 에이전트 행동 속도에 비해 촉박). 기록은 성향별 `tests/playtest/records/<시각>-<성향>/`에 불편 로그(오피스 시각, 화면, 하려던 것, 예상 vs 실제, 심각도, 스크린샷, 개선안) → 성향 간 중복을 없앤 요약 1장. CX 항목 후보로 제안만 하고 `docs/candidate-experience-fixes.md` 반영은 사람이 정한다 | `tests/playtest/`(러너 안내·성향 프롬프트·기록 형식·기록) | flow-verify와 같은 시점(`track/flow` 기능 트랙 전부 병합), 실 스택 사용권 | 3성향 각 1회 완주 기록 + 통합 요약. 실행은 Claude 서브에이전트(성향마다 하나, 실 스택은 한 번에 하나) |

- e2e(`tests/e2e/run.py`)는 대본과 단언으로 **정해진 동작이 맞는지** 확인하고, playtest는 대본 없이 **처음 쓰는 사람이 무엇에 막히는지** 찾는다.
- flow-verify와 병렬로 돌리되 `track/flow`의 main 병합을 막지 않는다. 이후 큰 UI 변경마다 다시 돌린다.

### 실행 방식

- **구현과 문서는 Claude 서브에이전트**(오케스트레이터가 Agent 도구로 띄움)가 한다. herdr pane은 **Codex 리뷰에만** 쓴다(`-m gpt-6.1-sol -c model_reasoning_effort=high -s workspace-write -a never -c features.fast_mode=false`, 소스 수정·git 변경 금지, 결과는 worktree의 `REVIEW.md`). UI/UX 리뷰는 Claude Opus 서브에이전트. 이 전환에서는 아래 "병렬 작업 방식"의 개발 pane 규칙 대신 이 방식을 쓴다.
- 트랙마다 자기 worktree·브랜치 `track/<이름>`(`sh scripts/worktree.sh <이름>`, `infra/.env`·`.env.local` 복사). 서브에이전트 브리프에 worktree 절대 경로·기준 커밋·catalog_version·소유 파일·완료 기준을 적는다. 서브에이전트는 자기 브랜치에만 커밋하고 `docs/handoff/reports/<트랙>-report.md`를 남긴다.
- 동시 개발 서브에이전트는 최대 4개. 리뷰 pane은 수에 넣지 않는다.
- 병합: 완료 보고 확인 → Codex 리뷰 → 지적 반영 → 오케스트레이터가 대상 브랜치(main 또는 `track/flow`) 위로 rebase → `make test`·`make lint`(통합 브랜치에서는 기대 실패 목록 대조) → squash 병합 → worktree·브랜치 정리 → `docs/handoff.md` 진행 표 갱신.

### 순서

| 파도 | 동시 진행 | 병합 대상 | 시작 조건 |
|---|---|---|---|
| T0 | docs-flow(G0) ∥ ui-layout ∥ investigate-cx10(완료) | docs-flow → main, ui-layout → main, cx10 보고서 → main | 없음 |
| T1 | contracts(G1) ∥ arch-page ∥ ui-layout(계속) | `track/flow` 생성(G1 커밋), arch-page → main | G0 main 병합(investigate-cx10은 완료, 계약 변경 없음) |
| T2 | flow-scenario ∥ flow-api ∥ flow-agent ∥ flow-web (최대 4) | `track/flow`. flow-scenario 먼저 | G1. flow-web은 추가로 ui-layout main 병합 + `track/flow` rebase |
| T2' | flow-worker (flow-scenario가 비운 자리) | `track/flow` | flow-scenario 병합 |
| T3 | flow-verify ∥ playtest(게이트 아님) | flow-verify 통과 시 `track/flow` → main. playtest 기록은 별도 병합 | T2·T2' 전부 병합 |

### 범위 밖

- 자료 탭 '기본 작업 흐름 예시'(D4, F12).
- 한서윤 답장 LLM 생성과 답장 실패 처리, `reporting` 상태, 종료 버튼, 5분 fallback, 보고 요청 채널 분기(F3로 제거).
- active_runs·`agent.progress` 채널 계약(별도 진행, 이 전환을 막지 않음), 필수 카드 3회 실패 규칙 변경(현행 유지), 6k 토큰 요약 접기.
- CX-10은 계약 변경 없이 flow-agent·flow-scenario에서 고친다.

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
| 빈 보드 분업 공유 | 할 일 0개 → 섹션 담당 draft 5개 PUT → POST division/share → snapshot·division.confirmed·task_events(target=section_owner)·동료 자극 저장. 할 일이 없어도 확정됨. 위반 시 위반 섹션·할 일 목록 | 섹션 담당·스냅샷 기준 자극으로 work_notes 갱신(존재하는 할 일만) | flow-web 보드 조작·위반 강조, e2e |
| 카드 전 계획 | 시작 전후 결정 시각·보드 이력 보존 | 0분부터의 계획 창에 먼저 정한 계획 포함 | e2e 기대 점수 |
| 창 밖 약속 이행 | observations PATCH·멱등, 워커가 갱신값 소비 | finalize에서 실제 메시지로 재계산 | e2e 다음 창 이행 대본 |
| 무관한 편집 | revisions 보존, target_applied=false면 미충족 | FakeLLM으로 편집 사실과 반영 사실 구분 aux | e2e 리포트 항목 |
| 문서 제공 실패 | MCP 오류·이벤트 failed 저장·워커 document_missing | send 재시도·카드 failed·의존 항목 처리 | e2e 장애 주입 |
| 제출 후 종료·재접속 | 제출 → 한서윤 DM `kind=report`·고정 답장·completed, completed 세션 resume → 디브리핑 | 10:50 DM 이후 DM 메시지와 제출 메시지만 정직 근거 | flow-web 보내기 창, e2e |

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
| docs-final | `README.md`, `docs/share/plan-report.*`, `docs/share/architecture.html`(최종 구현 대조 갱신), `scripts/purge.py`, 공용 목차·링크 | P5 |
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
F-06 회사 문서 관리·승인, F-07 면접 질문 제안, F-25 무응답 확인, 회사당 둘째 계정, 기업 약관·위탁 안내, 생성 화면의 평가표·타임라인 미리보기, 받은 문서 버전 비교, 최종본 append, 세션 길이 선택 UI, 타임라인 미리보기, LLM 페르소나 지원자 e2e, 리치 에디터, 공유 문서 동시 편집·인라인 코멘트(문서는 주고받기 모델), 파일 업로드, 두 번째 미션(개발), 색인 도구의 임의 경로·업로드, 복수 디자인안 비교, 다크 모드, 자료 탭 '기본 작업 흐름 예시'(D4). (MVP에 들어온 것: F-05 근거→전체 기록 링크, 전체 기록 읽기 전용 화면, 샘플 리포트, 인쇄·PDF 내보내기, 리포트 재생성, 종료 설문 2문항)

## 확장 후보 (M3 이후, 시간이 남으면)
- 세션 내 승인: 동료가 문서를 보내기 전에 주담당 확인을 구함(`send_document` 앞 interrupt, 수락·거절로 같은 thread 재개). 리포트 승인이 끝난 뒤에만 고려한다.
- 두 번째 미션(개발, 산출물은 설계 문서형): `scenarios/missions/<id>/` 폴더 하나 추가로 붙는다.

## worktree
```
sh scripts/worktree.sh api-admin      # ../Day-0_zaeho.worktrees/api-admin 에 track/api-admin
sh scripts/worktree.sh --remove api-admin
```
