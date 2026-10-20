# 브리프: e2e-runner 트랙 (P3, 러너 작성은 지금·실제 스택 실행은 사용권 받은 뒤)

역할: 실제 서비스를 상대로 대본을 끝까지 돌리고 단언·기록을 남기는 러너와 근거 정확성 픽스처를 만든다. worktree `../Day-0_zaeho.worktrees/e2e-runner`(현재 폴더), 브랜치 `track/e2e-runner`. 기준 커밋 main 최신(P1·P2 전부 병합: scenario·web·agent-session·agent-assistant·web-integrate 1라운드), 계약 커밋 537889b, catalog_version `b2cc7dd7baa915ca`.

## 공통 규칙
- 커밋은 자기 브랜치에만. 키 값 출력 금지. 주석은 역할·알아야 할 로직·예외 의도 수준. `docs/common/*`·서비스 코드·`apps/web/` 수정 금지 → 결함은 **변경 요청(재현 대본·로그·기대)**으로 보고서에. 러너는 결함을 가리지 않는다(단언 완화 금지).
- **실제 스택 사용권은 지금 web-integrate(2라운드)가 갖고 있다.** 이 트랙은 ① 러너·단언·기록 포맷·근거 정확성 픽스처를 **인메모리/격리 DB·FakeLLM**으로 먼저 완성하고(`tests/e2e/`의 단위 테스트), ② 오케스트레이터가 "스택 사용권 넘김"을 보내면 그때 실제 스택(`make infra-up` 인프라 + 이 worktree의 api·business-mcp·worker·web, `AGENT_RUNNER=session`·`ASSISTANT_RUNNER=graph`, DB `dayzero`)에서 대본을 돌린다. 끝나면 모든 앱 프로세스 종료. 실 LLM은 gpt-4o-mini(제한 키).
- 같은 시각에 web-integrate가 `apps/web/`, api-fix가 `services/api/app/routers·run.py`를 고친다. 이 폴더는 읽기만.

## 읽을 것
AGENTS.md, `docs/common/testing.md`(**e2e 절 전부가 완료 기준**: 세션 조립·대본·러너·기록·단언 1~9·장애 주입·근거 정확성 픽스처), `docs/common/contracts.md`, `scenario-model.md`, `rubric.md`, `docs/plan.md`(e2e-runner 행·6건 표 "화면·최종 인수" 열·소유권), `scenarios/e2e/*.yaml`·`README.md`(초기본·step 키·6건 인수표), `tests/e2e/README.md`, `docs/handoff/reports/web-integrate-report.md`(e2e-runner에 알릴 것: 화면 단계·API 호출 순서·WS 장애 주입 방법·`apps/web/e2e/session.mjs`), `agent-session-report.md`(대본 step 키·기대값, 두 복구 경계, 선점 금지 live 2/6), `agent-assistant-report.md`(assistant_reuse 대본 방식), `scenario-redesign-report.md`(e2e 항목), `services/api/tests/agent/script_driver.py`(6분 대본 드라이버 — 재사용 가능한 부분), `services/api/app/routers/internal.py`(test/sessions, 장애 주입에 쓸 수 있는 내부 API), `infra/docker-compose*.yml`.

## 허용 파일
`tests/e2e/`(run.py·단언·기록·conftest), `tests/eval/`(근거 정확성 픽스처·실행기), `scenarios/e2e/`(대본 다듬기·기대값 확정, 초기본 소유권 인수), `scripts/make_session.py`(새로 만듦), 루트 `Makefile`의 e2e·eval 타깃(추가만), 루트 `pyproject.toml`·lockfile(러너 의존성 추가 시).

## 범위
1. `scripts/make_session.py`: 관리자 토큰 → 채용 건(요소 선택) → 초대 → 내부 test/sessions(6분, company_id는 api-fix 병합 뒤 사용; 그 전엔 세션의 채용 건을 관리자 회사로 옮기는 내부 경로 또는 SQL은 쓰지 않고 api-fix를 기다린다) → 토큰 출력.
2. `tests/e2e/run.py`: 대본 로드(step 키 전부), WS·REST 진행, 카드 감지(`message.new.event_id`), 제출→reporting→보고→completed, report_ready 대기 → 관리자 draft → review → final → record. 장애 주입 6종(이벤트 fired 직후 종료·변경 도구 성공 직후 종료·문서 보내기 실패·큐 발행 전 종료·final 저장 후 ack 전 종료·리포트 3회 실패→regenerate): 방식은 이 트랙이 정한다(api 테스트 훅이 필요하면 변경 요청). `restart: api`는 로컬 프로세스 재시작으로.
3. 기록 `tests/e2e/records/<일시>-<대본>/`(transcript.jsonl·observations·report_draft/final·record·summary.md: 카드 시각 오차·단언 결과·run_id별 도구 호출·토큰 합·p95·LangSmith URL).
4. 단언 1~9 전부 코드로(testing.md 번호 그대로 함수 이름에).
5. `tests/eval/`: 질문 10건 + 유출 3종 + 선점 3종 픽스처와 실행기(FakeLLM 기본, `-m live`로 실모델).
6. 대본 7개 기대값(`expect.rubric`·labels·evidence_types) 확정은 실 실행 뒤.

## 완료 기준 (docs/plan.md M3 e2e-runner 행)
단언 전부 통과(실 스택, 대본 5개 동시 실행 포함), 기록 커밋(`tests/e2e/records/`), 장애 주입 6건 누락·중복 없음, 근거 정확성 픽스처 통과 + live 1회 기록(`records/eval-live-<일시>.md`), `make test`·`make lint`. **live 결과를 "모델 상향 판단 자료" 1장**(역할별 레이블 정확도·규칙 준수(선점 금지·팀장 DM)·카드 실패율·금지어·근거 검증 실패율)으로 보고서에.

## 보고
`docs/handoff/reports/e2e-runner-report.md`: 1단계(러너 완성, mock) 완료 시 중간 보고 → 경로 한 줄로 멈춰 사용권을 기다린다. 2단계(실 스택) 뒤 최종 보고: 단언별 결과, 실패 단언은 변경 요청(담당 영역 추정: api/agent/worker/web)과 재현 대본, 모델 상향 판단 자료, 파일럿(P4)에 넘길 것(짧은 e2e 통과본·근거 대조표 초안). 마지막 응답은 경로 한 줄.
