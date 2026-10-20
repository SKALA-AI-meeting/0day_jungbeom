# web-integrate 보고서 (P2, 1라운드)

브리프 `docs/handoff/briefs/brief-web-integrate.md`. 브랜치 `track/web-integrate`, 기준 커밋 main `6334fdb`(web-polish 병합 뒤), 계약 커밋 37bed0b, catalog_version `b2cc7dd7baa915ca`(시드·생성 응답에서 확인). 계약·공용 픽스처·services는 고치지 않았다.

## 완료 기준과 결과

| 기준 | 명령 | 결과 | 검증 방식 |
|---|---|---|---|
| 실 API로 문서 공유 → 열람 → 통합 → 제출 → 보고 → 리포트 → 전체 기록까지 한 세션이 화면에서 돈다(브리프 범위 1~4) | `cd apps/web && node e2e/session.mjs` | 27단계 전부 통과, 검사 82개 전부 ✓(수정 라운드 뒤 마지막 실행 `e2e/shots/2026-10-20T21-03-31-988Z/`, 약 296초) | **실 API**(api 8000·8001, business-mcp 9101, report-worker, web dev 3000, `AGENT_RUNNER=fake`), DB는 아래 "스택" 참고. 리포트 워커만 실 LLM(gpt-4o-mini) |
| 재연결 3종 | 위 스크립트 14·15·17단계(+20·23·24) | 통과 | 실 API. 끊김·4401은 브라우저 WS 경로를 가로채 주입(아래) |
| `pnpm test` | `cd apps/web && pnpm test` | Test Files 11 passed, Tests 12 passed(수정 라운드에서 reducer 테스트 1건 추가) | mock |
| `pnpm lint` | `cd apps/web && pnpm lint` | eslint + prettier --check 통과 | — |
| `npx next build`(MOCK 없이) | `cd apps/web && npx next build` | 통과 | — |
| 루트 `make lint` | `make lint` | ruff check·format, web eslint·prettier 통과 | — |
| 앱 프로세스 종료 | `lsof -ti:8000,8001,9101,3000 -sTCP:LISTEN \| xargs kill`, `pkill -f report_worker` | 네 포트 LISTEN 없음, 워커 없음 | — |

`make test`는 돌리지 않았다(이 트랙은 services를 바꾸지 않았고 web 테스트는 위 `pnpm test`).

## 스택(사용권)

- 인프라는 main의 `make infra-up` 그대로(postgres·rabbitmq·rag-mcp).
- **공용 DB `dayzero`의 스키마가 재설계 전(테이블 19개)이었다.** `DROP SCHEMA public` 후 재적용은 이 세션의 자동 권한 분류기가 막아서, 비파괴로 새 DB **`dayzero_web_integrate`**를 만들고 현재 `infra/db/schema.sql`(27개)을 적용해 api·business-mcp·worker를 거기에 붙였다(`DATABASE_URL`의 DB 이름만 바꿈, 나머지는 `infra/.env.local`). `dayzero`는 그대로다.
- seed: `make seed` → 채용 건 생성 성공, catalog_version `b2cc7dd7baa915ca`. **rag-mcp 재색인은 0건**: rag-mcp 컨테이너가 재설계 전 이미지라 catalog_version을 `6177f98c10fbf4ed`로 계산한다. 1라운드는 Fake 러너라 rag를 쓰지 않아 영향이 없지만 2라운드 전에 rag-mcp 재빌드·재색인이 필요하다(아래 2라운드 목록).
- 실행에 쓴 명령(`<URL>`은 `.env.local`의 DATABASE_URL에서 DB 이름만 `dayzero_web_integrate`로 바꾼 값):
  ```
  DATABASE_URL=<URL> AGENT_RUNNER=fake ENABLE_TEST_API=1 uv run python -m app.run            # services/api
  DATABASE_URL=<URL> uv run python -m business_mcp                                            # services/business-mcp
  DATABASE_URL=<URL> uv run python -m report_worker                                           # services/report-worker
  pnpm dev                                                                                    # apps/web (NEXT_PUBLIC_MOCK 없음)
  ```

## 연결 스크립트

`apps/web/e2e/session.mjs`(Node, `playwright-core 1.63.0` + 시스템 Chrome `channel: "chrome"`, 브라우저 다운로드 없음). 실행: 위 스택을 띄운 뒤 `cd apps/web && node e2e/session.mjs`. 환경변수 `WEB_URL`·`API_URL`·`API_INTERNAL_URL`·`E2E_DB`(기본 `dayzero_web_integrate`)·`INTERNAL_TOKEN`(없으면 `infra/.env.local`에서 읽고 출력하지 않음)·`HEADED=1`. 결과는 `apps/web/e2e/shots/<실행 시각>/`(git 무시)에 단계별 PNG와 `log.json`(steps·checks·api 응답 107건·WS 프레임 64건·픽스처 모양 비교).

스크립트가 그래프 역할을 대신하는 곳(FakeAgentRunner는 메시지에 고정 답장, 카드마다 "[fake] 카드 실행"만 올린다. **브리프의 "FakeAgentRunner가 보내는 고정 문서"는 없다**):
- 동료 문서 보내기: 내부 `POST /internal/sessions/{id}/docs/send {part_no: 4, channel: team, run_id, seq: 40}`(동료 그래프의 send_document와 같은 경로).
- 보고 분류: 내부 `PUT .../messages/{id}/classification {recipient: manager, kind: report}` → `POST .../complete`(그래프가 할 일).
- 테스트 세션의 채용 건을 관리자 회사로 옮김: `POST /internal/test/sessions`가 고정 회사 "e2e 테스트 회사"에 만들어서, 관리자 화면에서 리포트를 보려면 `UPDATE positions SET company_id=…`(docker exec psql, 격리 DB)가 필요하다(변경 요청 1).
- WS 장애 주입: `page.routeWebSocket`으로 브라우저와 api 사이를 중계하면서 서버 쪽·페이지 쪽을 함께 닫거나(끊김), 다음 연결을 서버에 붙이지 않고 4401로 닫거나, 연결을 늦춘다. 서버가 실제로 4401을 주는지는 위조 토큰으로 Node WebSocket을 직접 붙여 따로 확인한다.

### 단계(마지막 실행) — e2e-runner가 참고할 화면 단계와 API 호출 순서

| # | 화면 단계 | API·WS(실제 응답) | 스크린샷 |
|---|---|---|---|
| 1~2 | 관리자 가입 → 로그아웃 → 로그인 | `POST /admin/auth/signup` 200, `POST /admin/auth/login` 200 | 01, 02 |
| 3 | 채용 건 생성: 요소 5개 기본 선택, 미션 카드에 **회사 문서 5개**(catalog.documents) | `GET /admin/catalog`, `POST /admin/positions` 200(elements 5, catalog_version b2cc7dd7baa915ca) | 03 |
| 4~5 | 초대 링크 만들기 → 링크 입장 화면 | `POST /admin/positions/{id}/invites` 200, `GET /s/{token}` status invited | 04, 05 |
| 6 | 6분 테스트 세션 | 내부 `POST /internal/test/sessions {elements 5, session_minutes 6}` | — |
| 7 | 입장 → 동의 → 대기 → 시작 → 오피스 | `GET /s/{t}` → `POST consent` → `POST start` → `GET state`(alias "지원자E2E", 보드 5행 assignee null) → WS 연결 → `/state` 한 번 더(첫 연결 따라잡기) | 07 |
| 8 | 보드: 1 나·3 둘 다·4·5 도현 → 2번 상세 연 채 2 도현 → **422 문장**이 상세에 표시 → 2 나 | `PUT /tasks/n` 200 ×4, `PUT /tasks/2` 422 `invalid_division` "2번 인터뷰 근거는 … 흐름이 이어져요.", `PUT /tasks/2` 200 → WS `task.updated`·`division.confirmed{decided_by: candidate}` | 08 |
| 9 | 1번 문서 입력 → 1초 뒤 저장(측정 1047ms) → "v1 보내기"(한마디) / 2번 문서 저장만 | `PUT /my-documents/1` {revision 1}, `POST /my-documents/1/share {channel team, note}` {version 1} → WS `message.new{shared_doc}`·`document.shared{by: candidate}` | 09 |
| 10 | 동료 4번 v1 카드 도착 → 열기 → "답글 쓰기" → 보내기 | 내부 docs/send → WS `message.new{shared_doc}`·`document.shared{by: colleague}`, `POST /documents/{uuid}/open {version 1}` 200 → WS `message.ack`·`message.new{reply_to_doc}` → Fake 답장 `agent.progress`·`message.new` | 10 |
| 11 | 최종본: 4 ← 동료 v1, 2 ← 내 문서 현재 저장본, 1 ← 내 문서 → 4번 편집 | `PUT /final/sections/4/import {version 1}`, `…/2/import {version: null}`(source_version null), `…/1/import {version: null}`, `PUT /my-documents/final` 200 | 11 |
| 12 | 저장 ① 최종본 PUT만 500으로 가로챔: 실패 안내 → 재편집 중에도 유지 → 제출 시 "저장되지 않아 제출을(를) 멈췄어요"(submit 요청 없음) → 해제 후 재편집 200 → 안내 해제. ② PUT(내 문서 2·최종본)을 2.5초 늦춤: 첫 PUT 도는 중 추가 입력 → WS 끊김·재동기화(내 문서 최신 본문 유지) → 2번 보내기·최종본 3번 가져오기가 flush를 기다림 | ① `PUT final` 500(주입) → 200. ② 각 PUT 2회, 마지막 요청 본문 = 최신 본문, share·import 요청은 마지막 PUT 완료 뒤, 서버 `GET /my-documents`도 최신 | 12 |
| 13 | 어시스턴트: 응답 표시·복사(클립보드 일치) → 59회 직접 채움 → 화면에서 61번째 → "한도(60회)" 안내 | `POST /assistant` 200 … 429 `assistant_limit` | 13 |
| 14 | 재연결 ①: WS 끊김 → 3061ms 뒤 재접속 → `/state` → 토스트 "연결이 다시 이어졌어요" | `GET /state` connection_gaps `[{0.29→0.34}]` | 14 |
| 15 | 재연결 ②: 서버 4401 확인(위조 토큰) → 다음 연결에 4401 주입 → resume → 새 토큰으로 재접속. 이어서 입력창에 보내지 않은 글을 둔 채 4401 주입 + resume 한 번 503 → 오피스 그대로(링크 재조회 없음, 입력 유지) → 3초 뒤 재발급 200 → 재접속 | `POST resume` 200 / 503(주입) → 200 | — |
| 16 | 지연 공개: 3.5분에 `document.released{interview_summary}` → 자료 탭 "공개됨" 칩 → 열람 | `GET /documents/interview_summary` 200 | 16 |
| 17 | 재연결 ③: 같은 링크를 새 탭에서 → 이전 탭 `session.replaced`+4000 → "다른 창에서 열림" 가림막 | B `POST resume` 200 | 17 |
| 18 | 제출 확인 창 → 제출 → 보고 대기(남은 시간 카운트) | `POST /submit` {status reporting, deadline_at} → WS `session.reporting` | 18 |
| 19 | reporting 재입장(새로고침) | `GET /s/{t}` reporting → `POST resume` → `GET state`(status reporting, deadline_at) | 19 |
| 20 | reporting 중 65초 끊김 → 재접속 → 끊김 줄 "…연결이 끊겼어요" | `GET state` gap 3.58→4.68 | 20 |
| 21 | 팀 채널 보고 메시지 → (분류·complete) → `session.ended{submitted}` → 1.5초 뒤 디브리핑(최종본 포함) | WS ack → 내부 classification·complete → `GET /debrief` | 21 |
| 22 | 설문 2문항 → 보내기 | `POST /debrief/survey` 200 | 22 |
| 23 | 경계 ①: 두 번째 세션, 이 창의 **모든** 새 WS 연결의 상류 연결을 입장 시각+2.5초까지 늦춤 → 최초 snapshot에 대상 메시지 없음 → 내부로 저장 → 상류 연결 성립 → 그 뒤 state에 있음 → 화면 표시 | 연결 2개(개발 모드 재마운트): conn 1 지연 2272ms 뒤 버려짐, conn 2 지연 2271ms 뒤 상류 연결(입장 +2502ms), 대상 메시지를 담은 state는 연결 +16ms. 단계 2640ms | 23 |
| 24 | 경계 ②: 제출(reporting) → 끊김 유지 중 내부 complete → 4401 주입 → resume **409**(`cannot resume from report_ready`) → 링크 재판정 → 디브리핑 | `POST resume` 409 → `GET /s/{t}` report_ready → `GET /debrief` | 24 |
| 25 | 관리자 목록(검토 필요·삭제 예정) → 리포트 draft | `GET /candidates` report_ready, `GET /admin/sessions/{id}/report` stage draft | 25 |
| 26 | 항목 하나 조정+메모 → 검토자 → 검토 완료 확인 → 폴링 → final → 리포트 메모 추가 | `POST /review` {approving} → `GET report` final → `POST /report/notes` 200 | 26 |
| 27 | 근거 "기록에서 보기" → 전체 기록에서 그 행 `aria-current` 하이라이트, 리포트의 모든 record_ref·AI 호출이 기록 목록에 있음 → 목록의 삭제 예정일 | `GET /record`(86~행) | 27 |

### 계약 픽스처와 실제 응답(모양 비교)

스크립트가 경로별 첫 성공 응답의 키 구조를 `tests/fixtures/contracts/`와 비교한다(값이 아니라 키, 빈 배열·null로 못 내려간 곳은 제외). 22개 경로 중 차이는 `POST /admin/positions`의 `scenario` 안쪽뿐이다(실제 조립 결과가 축약 예시보다 키가 많음: elements, element_meta, cards[].actor·channel·brief, documents, persona, prompts, rubric_rules 등 21개). 화면은 scenario를 읽지 않으므로 **변경 요청 없음**. 그 밖의 State·share·open·import·task·assistant·submit·debrief·catalog·candidates·report·review·notes·record는 키 구조가 픽스처와 같다.

## 수정 파일

| 파일 | 내용 |
|---|---|
| `components/admin/types.ts` | Catalog `missions[].documents` |
| `components/admin/position-form.tsx` | 미션 카드에 회사 문서 제목 한 줄 |
| `components/admin/review.ts` | `docTitlesOf(catalog, mission_id)` |
| `components/admin/report-view.tsx` | 고정 `DOC_TITLES` 제거, `docTitles` prop(AI 활용 인용 문서 이름) |
| `app/admin/sessions/[id]/report/page.tsx` | 카탈로그를 받아 docTitles 전달 |
| `app/admin/sample-report/page.tsx` | 픽스처 카탈로그로 docTitles |
| `components/office/reducer.ts` | `releasedLater`: `document.released` 프레임과 재동기화 스냅샷(미공개→공개)으로 판정 |
| `components/office/office-view.tsx`, `library.tsx` | 알림 문장 파싱으로 "공개됨"을 정하던 코드 제거, reducer 값 사용 |
| `components/office/candidate-flow.tsx`, `lib/ws.ts` | ① 재동기화를 마운트 수명으로 취소하고 한 번에 하나만(도는 중 다시 불리면 끝난 뒤 한 번 더) ② 첫 WS 연결에서도 `/state` ③ 4401 뒤 resume이 종료 응답(409·410·404)이면 링크 입장부터 다시 판정, 네트워크·5xx면 오피스를 유지한 채 3초 뒤 재발급 재시도, 언마운트 때 saver 중단 ④ 최종본·문서 저장 실패 표시를 재편집·재시도 중에도 유지하고 성공 응답에서만 해제(web-polish B2) |
| `components/admin/position-form.test.tsx` | 뺀 요소 문구 기대값을 픽스처 값으로(공용 카탈로그 문구가 명사형으로 바뀜) |
| `mocks/fixtures/*.json` | 공용 픽스처 9개 다시 복사(admin_candidates·admin_catalog·admin_positions·admin_record·debrief·documents·report·state·state_reporting). 공용과 같은 이름 39개 전부 **값 일치** 확인(prettier 줄바꿈만 다름) |
| `mocks/fixtures/admin_candidates_extra.json`(삭제), `mocks/admin.ts`, `mocks/README.md` | 공용 `admin_candidates.json`이 sess-1~8을 다 가져 중복되는 web 전용 파일을 지움. web 전용은 `office_script.json` 하나 |
| `e2e/session.mjs`(새로) | 연결 스크립트 |
| `package.json`·`pnpm-lock.yaml` | devDependency `playwright-core 1.63.0`(정확 버전, 공개 6주) |
| `.gitignore`·`.prettierignore` | `e2e/shots` |

`components/ui/`·`globals.css`·`public/brand/`는 건드리지 않았다. `mock-controls`·`data-toggle`·`worst`는 원래 MOCK일 때만 렌더되어 그대로 두었다. Next dev가 만든 `apps/web/AGENTS.md`는 지웠다(커밋 안 함).

## 변경 요청(오케스트레이터 판단, api 담당 지정 요청)

1. **`POST /internal/test/sessions`에 관리자 회사 지정(api, internal.py 담당)**: 지금은 고정 회사 "e2e 테스트 회사"에만 만들어 관리자 화면(목록·리포트·전체 기록)으로 그 세션을 볼 수 없다. 요청 `{..., company_id?}` 또는 `{..., admin_email?}`. 스크립트는 지금 격리 DB에 직접 UPDATE한다. e2e-runner도 같은 필요가 있다.
2. **공용 DB `dayzero` 재적용**: 재설계 전 스키마다. 2라운드·e2e 전에 `schema.sql` 재적용(사용자 승인 필요) 또는 `dayzero_web_integrate`를 계속 쓸지 결정.
3. **rag-mcp 컨테이너 재빌드**: catalog_version을 옛 값(`6177f98c10fbf4ed`)으로 계산해 재색인 0건. 2라운드(어시스턴트 그래프·동료 검색) 전에 `docker compose … build rag-mcp` 후 `make seed`.
4. (선택) **State에 문서 공개 시각**: "공개됨" 칩은 이 창이 공개를 본 경우(프레임·재동기화)만 뜬다. 공개 뒤에 새로 들어오면 칩이 없다. 남기려면 State `documents[].released_at_min` 같은 값이 필요하다. 지금 동작으로 충분하면 요청 없음.

## 남은 문제

- **active_runs 복원**: FakeAgentRunner는 실행이 수 ms에 끝나 `/state.active_runs`가 늘 비어 있었다. reducer의 복원 경로는 실서버로 확인하지 못했다(2라운드).
- 6분 세션은 마감 10분 전 줄이 시작부터 보인다(10분 기준 고정). 테스트 세션 특성이라 고치지 않았다.
- 4401 주입 구간도 connection_gaps에 짧은 끊김으로 남는다(정상 동작).
- 4401 뒤 resume 실패 처리: 종료 응답(409·410·404)만 링크 재판정으로 넘기고, 네트워크·5xx는 오피스와 미저장 상태를 유지하며 3초 간격으로 재발급을 계속 시도한다(재시도 횟수 상한 없음, 그동안 연결 끊김 표시). 이전 판의 "모든 resume 실패 = 세션 종료" 처리는 수정 라운드에서 고쳤다.
- 리포트 근거가 없는 세션이라(Fake 러너, 관찰 없음) 27단계의 기록 링크 대조 60개는 AI 호출뿐이다. 근거 record_ref 대조(섹션·평가표 항목 모두 포함)는 2라운드에서 비지 않은 목록으로 확인한다.
- 1440×900 한 크기에서만 확인했다.

## 다른 트랙에 알릴 것

- **e2e-runner**: 위 단계 표가 화면 단계와 API 호출 순서다. 화면은 입장 시 `/state`를 받고 WS가 열리면 한 번 더 받는다. 제출은 대기 중 저장을 끝낸 뒤 `POST /submit`이고 저장이 실패하면 submit을 보내지 않는다. 보고 감지는 서버 분류뿐(화면은 `session.reporting`·`session.ended`만 본다). 변경 요청 1이 해결되면 SQL 이동을 지운다.
- **agent-session**: 화면이 기대하는 것 — 문서 카드 메시지는 `shared_doc`와 `document.shared`를 함께(본문 "n번 제목 vK"), 받은 문서는 열기 전에 카드로만 보인다. 보고 메시지에 `kind=report` 저장 뒤 `complete`를 불러야 `session.ended`가 와서 디브리핑으로 넘어간다(안 오면 5분 deadline까지 보고 대기 화면). 분업 확정 뒤 동료 카드 상태 변경은 `task.updated{by: colleague}`로 와야 보드 줄이 생긴다. 시작 직후 팀장 킥오프 메시지가 없으면 대화가 비어 보인다(Fake에서는 "[fake] 카드 실행"만).
- **agent-assistant**: 응답의 `cited_docs`는 State `documents`의 doc_id여야 제목 칩이 나온다. 한도는 61번째에 429 `assistant_limit`.

## 2라운드에서 확인할 목록(AGENT_RUNNER=session, ASSISTANT_RUNNER=graph)

1. 변경 요청 2·3 처리(DB·rag 재색인) 뒤 `make seed`가 indexed > 0.
2. 스크립트 10단계의 내부 docs/send 대신 동료 그래프가 보낸 실제 문서를 기다리도록 바꾸고(카드 이벤트 시각), 21단계의 내부 classification·complete를 빼고 실제 분류로 `session.ended`가 오는지.
3. 카드 7장이 실제로 나오는지(디브리핑 events), 리포트 근거(evidence·record_ref)가 생기고 27단계의 "모든 record_ref가 기록에 있음" 검사가 비지 않은 목록으로 통과하는지.
4. `active_runs` 복원: 동료 응답 중 새로고침 → "입력 중…" 표시.
5. 어시스턴트 실제 응답·`cited_docs` 제목 칩.
6. 팀장 킥오프·422 뒤 동료 자극(보드만으로 분업 확정 사례).

## 수정 라운드(Codex)

원문 `REVIEW.md`(차단 3, 커밋 안 함). 실 스택(같은 격리 DB `dayzero_web_integrate`, `AGENT_RUNNER=fake`)을 다시 띄워 스크립트 27단계·검사 82개 통과 후 내렸다(`e2e/shots/2026-10-20T21-03-31-988Z/`).

| # | 처리 | 내용·확인 |
|---|---|---|
| B1 | 고침 | `flow` 쪽 `refreshToken`이 resume 오류를 구분한다: 409·410·404만 `null`(세션 종료 → `closed` → 링크 재판정), 그 밖(네트워크·5xx)은 throw. `lib/ws.ts`는 throw면 3초 뒤 재발급부터 다시 시도하고 오피스·dirty·미전송 메시지·저장 상태를 그대로 둔다. OfficeContainer 언마운트 때 `saver.stop()`(개발 모드 즉시 재마운트는 건너뜀). 확인: 15단계(503 한 번 → 오피스·입력 유지 → 재발급 200 → 재접속), 24단계(종료 뒤 409 → 링크 재판정 → 디브리핑) |
| B2 | 고침 | reducer `final_section`이 저장 세대를 올리고 `imported[part] = {section, seq}`를 남긴다. 스냅샷 적용 때 조회 시작 세대(since)보다 뒤에 성공한 가져오기의 본문·출처를 먼저 얹고, 그다음 확정 저장·미저장 편집을 얹는다. 테스트 `docs-flow.test.ts` "가져오기 전에 조회한 state가 늦게 와도…"(지연 state + 가져오기 + 다른 섹션 저장 → 가져온 본문·출처·edited=false와 다른 섹션 유지). 옛 reducer로 돌리면 이 테스트가 실패함을 확인했다 |
| B3 | 고침 | `wsTap.delayUntil`: 그 시각까지 이 창의 **모든** 새 연결을 늦추고, 기다리는 사이 더 새 연결이 생기면 앞 연결은 버린 것으로 기록. 연결마다 id·지연·상류 연결 시각을 `log.json`(frames의 `injected`/`upstream`, 단계의 `connections`)에 남긴다. 23단계 검사를 "최초 snapshot에 없음 → 저장 → 상류 연결(입장 +2.5초 이후) → 그 뒤 state에 있음" 순서로 바꿨다. 이전 실행이 412ms에 끝난 이유는 개발 모드 재마운트로 연결이 둘 생겨 지연을 하나만 받았기 때문(이번 실행 conn 1 버려짐·conn 2 연결) |
| 2절 | 반영 | 12단계에 느린 PUT(2.5초) 중 추가 입력·재연결·flush 겹침을 넣었다: 내 문서 2번과 최종본 각각 마지막 PUT 본문이 최신, share·import 요청이 마지막 PUT 완료 뒤, 재동기화 뒤에도 편집기 본문 유지, 서버 값도 최신 |
| 2절(e2e-runner) | 일부 반영 | 27단계 대조 목록에 `rubric.elements[].cards[].items[].evidence[].record_ref`를 더했다. 비지 않은 근거 목록 확인은 2라운드(위 남은 문제) |
| 2절·3절 나머지 | 넘김 | active_runs·v1 불변·1280px·제출 전 보고·5분 만료는 2라운드·e2e-runner 몫(목록 유지). 2라운드는 내부 docs/send·classification·complete를 실제 그래프 대기로 바꾸고 어시스턴트 59회 채우기의 실행 방법을 따로 정해야 한다 |

```
cd apps/web && pnpm test        # Test Files 11 passed, Tests 12 passed
cd apps/web && pnpm lint        # 통과
cd apps/web && npx next build   # 통과(MOCK 없음)
make lint                        # 통과
node e2e/session.mjs            # 27단계 통과, 검사 82개
```
