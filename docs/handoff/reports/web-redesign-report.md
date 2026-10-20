# web-redesign 보고 (P1, 2026-10-21)

- 브랜치 `track/web-redesign`, 기준 커밋 eeda2a1(main, 계약 고정), 작업 시작 HEAD 2c2342e(브리프 커밋).
- 범위: `docs/frontend/design.md` 전체를 mock(`NEXT_PUBLIC_MOCK=1`)으로 구현. 옛 화면(요소 4개·공유 문서 편집·리드 호칭)은 남기지 않았다. 실제 스택(api·MCP·DB)은 띄우지 않았다.

## 완료 기준 결과

검증 방식은 전부 mock이다. 각 줄을 `NEXT_PUBLIC_MOCK=1 pnpm dev`(3000)에서 Chrome으로 직접 눌러 확인했고(1440px 창), vitest 한 개로 고정했다. 확인 뒤 dev 서버는 껐다.

| 완료 기준 | vitest | 화면 확인 |
|---|---|---|
| 관리자 1: 생성 화면 미션 1개, 요소 5장 기본 전체 선택, 뺐을 때 차이 한 줄, 0개·6개 거부, 샘플 리포트 링크 | `components/admin/position-form.test.tsx` | `/admin/positions/new`에서 책임감 체크 해제 → "빼면: 인터뷰 요약이 시작 시 공유되고…" 확인 |
| 관리자 2: 지원자 목록 상태 묶음·필터·세 수 점수·실패 행동 안내·삭제 예정일 | `components/admin/candidates.test.tsx` | `/admin/positions/pos-1` |
| 리포트: 요약표, 출처 칩·편집 원문 나란히, 주고받은 문서, 접힌 소섹션, 기록/AI 분류 칩, 사유 문장, 정직 주석, 시간순 AI 활용, 검토 완료 확인 창·검토자 이름, final 메모, "기록에서 보기" 하이라이트, 인쇄 때 전부 펼침 | `components/admin/report-view.test.tsx` | `/admin/sessions/sess-1/report` → 카드 펼침 → "기록에서 보기" → `/record#message-m-31` 하이라이트 확인 |
| 지원자: 전 화면·전 상태(만료·완료 안내, 동의 전 시작 불가, 대기 레이아웃 그림, 오피스 4탭과 ?, 보고 대기, 디브리핑 최종본·설문·문의, 재연결 복원, reporting 재입장) | `components/office/flow.test.tsx`, 재연결은 `lib/ws.test.ts` | `/s/demo` 입장→동의→대기→오피스, `/s/live` 재입장, `/s/reporting` 보고→디브리핑 |
| 문서 흐름: 보내기 → 받기(DocCard) → 열기 → 답글(참조 칩) → 최종본 가져오기(출처 칩) → 제출(확인 창) → 보고 대기(5분, 잠금 없음) → 디브리핑 | `components/office/docs-flow.test.ts` | `/s/demo`에서 1번 v1 보내기, `/s/live`에서 4번 열기·답글·가져오기·제출 |
| 보드: 담당 없음 5장 → 채우면 division.confirmed·SystemLine, 끌어 놓기(칸·순서), 상세 패널 "언제까지" 프리셋·의존 배지, 확정 뒤 재배정 | `components/office/board.test.tsx` | `/s/demo` 보드 탭에서 담당 5장 채움 → "분업이 정해졌어요: 1·2 나, 3 같이, 4·5 도현" |
| 개인 알림 보낸 사람·"나에게만"·"공개됨", 편집 중 Toast, 어시스턴트 복사, 접속 끊김 줄, 2분 전 경고, SystemLine 종류 전부 | `components/office/notices.test.tsx` | `/s/live` mock 조작으로 60·70분 장면 → 알림 채널 확인, 편집 중 토스트 확인 |
| `review-animations`·`break-ui` | 아래 "디자인 점검" | `?data=worst` 전환으로 확인 |

명령과 결과(apps/web):

```
pnpm test            # Test Files 10 passed, Tests 10 passed (3회 반복 실행, 흔들림 없음)
pnpm lint            # eslint . && prettier --check . 통과
NEXT_PUBLIC_MOCK=1 npx next build   # 통과(라우트 14개)
```

루트 `make test`·`make lint`의 web 부분은 위 두 명령(`pnpm test --silent`, `pnpm lint`)과 같고 통과했다. Python 부분은 이 트랙 범위가 아니라 돌리지 않았다.

## 디자인 점검

**review-animations** (판정: 승인. 지적 4건은 고쳤다)

| Before | After | Why |
|---|---|---|
| 메시지 줄마다 `.arrive` 페이드 | 화면을 연 뒤 새로 온 줄에만(`Timeline`이 마운트 때 본 id 기억, 채널마다 새로 마운트) | 채널 전환은 하루 수십 번이라 매번 전체가 깜빡였다 |
| `.press { transition: transform }`가 `transition-colors`를 덮음 | transform 100ms + 색 150ms를 함께 지정 | hover 색이 순간 전환됐다 |
| dnd kit 기본 200ms ease | 150ms `cubic-bezier(0.23,1,0.32,1)` | design-system 모션 "카드 이동 150ms" |
| `.arrive`에 reduced-motion 없음 | `prefers-reduced-motion`에서 끔 | 접근성 |

남은 모션: 문서 열기 160ms·닫기 120ms(motion, transform+opacity, reduced-motion이면 이동 없음), 메뉴 150ms(트리거 기준 scale 0.95+opacity), 대화 상자 200ms(가운데 scale 0.97), 버튼 :active scale 0.97, 타이머 10분 전 색 전환 1회. hover는 Tailwind v4 `hover:`가 이미 `(hover: hover)`로 묶는다.

**break-ui** (`?data=worst`, 화면 위쪽 "Demo data / Worst case" 전환, `mocks/worst.ts`)

| # | 심각도 | 값 | 증상 | 조치 |
|---|---|---|---|---|
| 1 | Broken | 별칭 `Aleksandra Wiśniewska-Kowalczyk`(공백 포함) | 오피스 별칭이 "나"로 떨어짐 | 킥오프 문장 정규식을 `주담당은 (.+?)님입니다`로(고침) |
| 2 | Ugly | 픽스처 재입장(live) | 분업 확정 줄이 킥오프 위로 정렬됨 | mock이 픽스처 절대 시각을 현재 시계로 옮김(고침) |
| 3 | Ugly | 같은 분에 동료 문서 3개 | "보냈어요" 줄 세 개가 카드들과 떨어져 몰림 | 줄을 해당 카드 바로 위에 붙임(고침) |
| 4 | — | 긴 이메일·채용 건 이름·공백 없는 URL·긴 최종본(14문단)·지원자 0명 | 줄바꿈·빈 상태 정상 | 그대로 |

결정이 필요한 것(사용자 몫): 리포트 최종본 섹션이 매우 길 때 접을지(지금은 전부 펼침, 인쇄와 같은 모양).

## 화면별 진입 경로와 mock 조작 순서

공통: `cd apps/web && NEXT_PUBLIC_MOCK=1 pnpm dev`. mock 상태는 브라우저 메모리라 새로고침하면 처음으로 돌아간다. 관리자 로그인은 아무 이메일·비밀번호(비밀번호 `wrong`이면 401, 가입 이메일 `taken@example.com`이면 409).

### 지원자 `/s/<토큰>`

| 토큰 | 보이는 것 |
|---|---|
| `expired` · `cancelled` · 그 밖 | 만료·취소·없는 링크 안내 |
| `demo` | 입장 안내 → 동의(체크 전 버튼 잠김) → 대기(팀 소개·레이아웃 그림) → 오피스 0분, 보드 담당 없음 |
| `live` | 진행 중 47.5분 재입장(끊김 줄 00:31~00:46, 받은 문서 3개, 4번 v1 답글) |
| `reporting` | 보고 대기 재입장(위쪽 5분 카운트) → 팀 채널·팀장 DM에 아무 메시지 → 종료 → 디브리핑 |
| `done` | 디브리핑 다시 보기(최종본 열람·복사, 설문, 문의) |
| `failed` | 세션 중단 안내 |

오피스 왼쪽 아래 **mock 조작**(점선 상자):
- **다음 장면 ▶**: 10분 분업 질문 → 30분 동료 DM 도움 요청(분업이 없으면 동료 기본안 확정) → 45분 중간 점검(동료 담당 파트의 v1 DocCard, "2번 자료 언제쯤?") → 60분 개인 알림(리서치 담당 → 나에게만) → 70분 인터뷰 요약 공개("공개됨" 줄, 자료 탭 잠금 해제) → 75분 팀장 방향 변경 → 90분 리뷰(v2 DocCard와 반대 의견) → 110분 보고 요청과 "최종본은 오른쪽 탭에서 제출" 줄.
- **마감 2분 전으로**: 2분 전 줄과 토스트, 제출 확인 창에 경고 문구.
- **시간 만료(자동 제출)**: 보고 대기로 바뀌고 "시간이 끝나 지금 상태로 제출됐어요…" 줄.
- **연결 끊기(3초 뒤 재연결)**: 레일에 "연결이 끊겼어요", 3초 뒤 재연결하고 /state로 복원, 끊긴 구간 줄이 생김.
- **다른 창에서 접속**: 이 창이 멈춤(4000).
- **보고 5분 지나기**: 보고 없이 종료 → 디브리핑.

추천 순서(문서 흐름 전체): `demo` 시작 → 보드 탭에서 카드마다 동그라미 눌러 담당(1·2 나, 3 둘 다, 4·5 도현) → 분업 확정 줄 → 내 문서 탭 1번에 쓰고 "v1 보내기 → # 재참여-기획" → mock 조작 "다음 장면" 세 번(45분) → 동료 DocCard "열기" → DocViewer에서 "답글 쓰기"(입력창에 참조 칩) → "최종본에 가져오기"로 섹션 선택 → 내 문서 탭 ★ 최종본에서 출처 칩 확인, 편집하면 "+ 편집" → "제출" 확인 창 → 보고 대기 → 팀 채널에 보고 → 디브리핑. 3·4·5번 카드 담당을 4·5 모두 "둘 다"로 채우면 422 문장이 카드 상세에 뜬다.

### 관리자

| 경로 | 보이는 것 |
|---|---|
| `/admin/login`, `/admin/signup` | 새 토큰으로 맞춘 로그인·가입 |
| `/admin/positions` | 채용 건 목록, 샘플 리포트 링크 |
| `/admin/positions/new` | 미션 블록, 요소 5장(체크 해제 → 차이 한 줄, 0개면 버튼 잠김) |
| `/admin/positions/pos-1` | 묶음 5종 필터, 세 수, 실패 안내(재초대·리포트 다시 생성), 중도 종료·초대 취소 확인 창, 초대 폼(중복 별칭 즉시 막음, 링크·안내 문안 복사) |
| `/admin/sessions/sess-1/report` | draft. 항목 값을 바꾸면 메모 필수 → 검토자 이름 → "검토 완료" 확인 창 → 확정 중(2초 폴링) → final, 메모 추가. 검토자 이름에 "지연"을 넣으면 확정이 멈춰 "조정은 저장되어 있습니다. 확정만 다시 시도합니다" + 재시도 |
| `/admin/sessions/sess-6/report` | 검토 완료(final) 리포트, 조정 메모·추가 메모 |
| `/admin/sessions/sess-1/record` | 전체 기록, 종류·채널·주체 필터, `#message-m-31` 같은 앵커 하이라이트 |
| `/admin/sample-report` (+ `/record`) | 픽스처 정적 렌더, 로그인 없이 열림 |
| 인쇄 | 리포트에서 "인쇄" 또는 ⌘P: 소섹션 전부 펼침, 버튼·링크 숨김, 원문 나란히 보기는 접힘 |

break-ui: 아무 화면 위쪽 "Worst case"(또는 주소에 `?data=worst`). `/admin/positions/pos-empty?data=worst`는 지원자 0명.

## 수정 파일

- 추가: `components/office/{board,conversation,doc-viewer,my-docs,library,assistant-panel,lines,mock-controls}.tsx|ts`, `components/admin/record-view.tsx`, `components/ui/{avatar,chip,status-pill,menu,toaster}.tsx`, `components/dev/data-toggle.tsx`, `app/admin/sessions/[id]/record/page.tsx`, `app/admin/sample-report/{page,record/page}.tsx`, `mocks/worst.ts`, `mocks/fixtures/*`(계약 픽스처 복사 39개 + web 전용 `office_script.json`·`admin_candidates_extra.json`), 테스트 7개
- 다시 씀: `components/office/{types,flow,reducer,link-screens,office-view,candidate-flow,debrief-screen}`, `components/admin/{types,client,format,review,report-view,candidates,position-form}`, `mocks/{admin,office,README}`, `lib/ws.test.ts`
- 고침: `app/globals.css`(파트·사람 색 토큰, 모션, 인쇄), `app/layout.tsx`(dev 전환), `app/page.tsx`(주석), `app/admin/**/page.tsx`, `components/admin/{shell,position-list}`, `components/ui/{button,confirm-dialog,status-badge,tabs,index}`, `package.json`·`pnpm-lock.yaml`, `.prettierignore`(`.agents`)
- 삭제: 옛 오피스(`chat`, `plan-doc`, `task-board`, `company-docs`, `part-saver`, `parts`), `components/admin/score.tsx`, 옛 테스트 5개, 옛 `mocks/fixtures/{admin,office}/`
- 의존성 추가(정확 버전): `@dnd-kit/core 6.3.1`, `@dnd-kit/sortable 10.0.0`, `@dnd-kit/utilities 3.2.2`, `sonner 2.0.8`, `motion 13.4.6`(14.4.0은 공개 이틀째라 2주 넘은 13.4.6으로 고정)
- 소유권 밖 파일은 고치지 않았다(`lib/api.ts`, `lib/ws.ts`도 그대로 씀).

## 설계 판단(문서에 없거나 어긋나 내가 정한 것)

1. **보드 칸은 세로로 쌓았다.** 오른쪽 패널 440px에 칸 3개를 가로로 두면 카드 제목이 세 줄로 접혀 읽히지 않아 Linear 목록처럼 상태별 묶음을 세로로 두고 묶음 사이·안에서 끌어 놓는다. ≥1440 넓은 보드는 polish 몫.
2. **담당은 카드의 동그라미 메뉴로 바로 고른다**(상세 패널에서도 가능). 다섯 장을 채우는 동선이 짧아야 해서다.
3. **내 보드 변경 줄은 담당·언제까지만** 남기고 상태·순서는 남기지 않는다(끌 때마다 대화를 덮는다). 동료 변경은 전부 남긴다.
4. **"보냈어요" 줄은 문서 카드 바로 위**에 붙인다. 접속 끊김 줄은 모든 채널에 보인다.
5. **답글 쓰기**는 문서를 닫고 그 문서가 공유된 채널로 돌아가 입력창에 참조 칩을 붙인다(design-direction ④ "보내면 문서가 공유된 채널로").
6. **목록 묶음**: 확정 중(approving)은 data-model.md대로 "검토 필요"에 둔다. design.md는 "완료(확정 중·검토 완료)"라 두 문서가 어긋난다(아래 변경 요청 3).
7. **디브리핑의 "점수" 표기**: 브리프는 동의 화면 밖에서 "점수"를 금지하지만, design.md·contracts는 디브리핑에 "점수를 보여 주지 않는 이유"를 요구하고 픽스처 `scoring_notice`도 "점수"를 쓴다. 서버 문장을 그대로 보이고 내 문구 제목은 "결과를 숫자로 보여 드리지 않는 이유"로 피했다. 오피스·대기·입장 화면에는 "리드·평가·점수"가 없다(테스트로 고정).
8. **샘플 리포트 위치**: contracts는 `apps/web/fixtures/sample-report.json`이라 했지만 이 트랙 허용 경로가 아니고 design.md는 report.json·record.json 픽스처를 그대로 렌더하라고 해서 `mocks/fixtures/report.json`을 직접 읽는다. 샘플은 로그인 없이 연다.

## 남은 문제

- 별칭: `GET /s/{token}`과 State가 별칭을 주지 않아 킥오프 메시지에서 읽는다(`aliasOf`). 킥오프가 스냅샷에 없으면(`state_reporting.json`) "나"로 보인다.
- 내 문서 가져오기: 한 번도 보내지 않은 내 문서는 version 0으로 `import`를 부른다. contracts는 "내 문서는 아무 버전"이라 했지만 버전이 없을 때의 값이 정해져 있지 않다(변경 요청 4).
- Next 16 dev가 첫 실행 때 `apps/web/AGENTS.md`를 만든다(`agentRules`). 이 트랙이 만든 파일이 아니라 지웠고, `next.config.ts`는 소유권 밖이라 끄지 않았다.
- mock의 프레임 재생은 스냅샷 중 도착분을 다시 얹는다. 실제 서버에서 같은 message.new가 두 번 와도 id로 거르지만, task.updated 순서가 뒤바뀌는 경우는 확인하지 못했다.
- 화면 확인은 1440×900 한 크기에서 했다. 1280 이하 폭은 오른쪽 패널이 고정 440px이라 가운데가 좁아진다(PC 권장 전제).

## 변경 요청(계약·픽스처, 오케스트레이터 판단)

1. **시작 직후 State 픽스처**: `state.json`은 47.5분(분업 확정 뒤)뿐이라 web mock이 `demo` 시작 상태(보드 assignee 전부 null, 빈 문서, 킥오프만)를 코드로 만든다. `state_start.json`이 있으면 그걸 복사하겠다.
2. **`admin_candidates.json` 묶음 5종**: design.md mock 표는 "묶음 5종 각 1행 이상"인데 계약 픽스처는 3행(대기·검토 필요·문제)이다. web은 `admin_candidates_extra.json`(sess-4 만료, sess-5 진행, sess-6 검토 완료, sess-7 취소, sess-8 리포트 실패)을 계약 형태로 더했다. 공용 픽스처로 올릴지.
3. **묶음 정의 어긋남**: data-model.md "검토 필요(리포트 준비됨·확정 중), 진행(진행 중·보고 중·완료)" vs design.md "완료(확정 중·검토 완료)". 화면은 서버 `display_group`을 그대로 쓰므로 api가 따를 쪽 하나로 정해 주면 된다. mock은 data-model을 따랐다.
4. **보내지 않은 내 문서의 import 버전**: `PUT /final/sections/{n}/import {source_doc_id, version}`에서 내 문서의 현재본(보낸 버전 없음)을 가져올 때 version 값(0? null? 생략?)을 정해 달라.
5. **`report.json`의 기록 없음 사유**: design.md mock 표는 "no_record_reason 6종"인데 픽스처는 no_activity 하나다. 사유 문장 매핑은 함수 테스트로 고정했고, 6종이 들어간 픽스처가 있으면 화면으로도 확인하겠다.
6. **관리자 리포트 근거의 회사 문서 이름**: `ai_usage.events[].cited_doc_ids`와 doc_view 근거에 문서 제목이 없어 web이 미션 문서 이름 표를 들고 있다. Report에 제목을 싣거나 catalog에 문서 목록이 있으면 표를 지우겠다.
7. **mock 픽스처 복사본 서식**: `mocks/fixtures/`의 계약 복사본은 prettier가 줄바꿈만 바꿨다(값은 같음, 확인함). 바이트까지 같게 두려면 `.prettierignore`에 `mocks/fixtures`를 넣는 사전 허용이 필요하다.

## 다른 트랙에 알릴 것

**web-integrate(실 API 연결 때 바꿀 지점)**
- 경로는 전부 `components/office/flow.ts`의 `candidateApi`와 `components/admin/client.ts`의 `adminApi`에 있다. 화면은 이 두 객체만 부른다.
- `lib/ws.ts`는 그대로다. MOCK이면 `mocks/office.ts`의 `createMockSocket`을 쓴다.
- 지울 것: `components/office/mock-controls.tsx`(OfficeContainer의 `devSlot`), `components/dev/data-toggle.tsx`(layout), `mocks/worst.ts`. 모두 MOCK일 때만 렌더된다.
- 확인할 것: 보고 감지는 서버 분류(kind=report)라 mock처럼 "보고 요청 뒤 팀 채널·팀장 DM 아무 메시지"가 아니다. 제출 응답보다 `session.reporting`이 먼저 올 수 있어 화면은 제출 직전 `submitting` 표시로 자동 제출과 구분한다. 422 `invalid_division`의 message를 그대로 보여 주므로 api가 조건 문장을 message에 넣어야 한다. 리포트 확정 폴링은 2초 × 5회 뒤 "확정만 다시 시도"(같은 본문 재전송 = 200 멱등)를 띄운다.
- 저장은 `components/office/saver.ts`(문서별 1초 디바운스·직렬). 제출·공유·가져오기 전에 `flush`가 성공해야 진행하고, 실패하면 멈추고 알린다(수정 라운드 2).
- (Codex 2절) 재동기화 취소·중복 실행 제어: `candidate-flow.tsx`의 `refresh`는 `fetchSnapshot`의 alive가 항상 true라 화면을 떠나도 재시도가 끝나지 않고, 겹친 refresh가 `during` 버퍼 하나를 공유한다. 연결 세대·마운트 수명으로 취소하고 한 번에 하나만 돌린다.
- (Codex 2절) 카탈로그 문서명: 최신 계약의 `missions[].documents`로 `report-view.tsx`의 고정 `DOC_TITLES`와 `admin/types.ts`의 Catalog 타입을 바꾼다(변경 요청 6 종료).
- (Codex 2절) mock의 내 문서 import는 숫자 version을 줘도 현재 본문을 돌려준다(`mocks/office.ts` importSection). 실 API의 과거 버전 불변 동작은 이 mock으로 증명하지 않는다.
- (Codex 4절) 보고 분류(kind=report)·제출 전 보고·제출 응답보다 앞선 session.reporting·reporting 재입장, 첫 WS open 전 변화와 4401 뒤 resume 409, live mock이 비우는 active_runs 복원을 실서버 한 세션에서 확인한다. 공용 픽스처가 갱신되면(alias·window·evidence·보드 summary 새 값) web 복사본을 다시 맞춘다.

**web-polish(넘길 목록)**
- `components/ui/`: 새로 만든 `avatar`, `chip`, `status-pill`, `menu`(DropMenu), `toaster` + 고친 `button`(xs 크기, 누름 모션), `confirm-dialog`(children, 열림 모션), `tabs`(aria-selected 표시), `status-badge`(reporting).
- `app/globals.css`: 파트 5색·사람 4색·`--shadow-float`·`--ease-out` 토큰, `.press`·`.arrive` 모션, 인쇄 규칙.
- brand: `public/brand/`는 비어 있다. 로고 없이 "Day Zero" 글자만 쓴다.
- polish 후보: ≥1440 분할 보기(받은 문서 보며 내 문서 고치기), 넓은 보드, 드롭 때 scale 0.98→1, 1280 이하 폭.
- (Codex 2절) 1280px 작업 폭: `office-view.tsx`의 232px 레일·440px 패널 고정 열에서 편집·제출·팝오버 동선과 ≥1440 배치를 확인한다. 이 파일은 polish 소유 밖이라 web-integrate와 먼저 나눈다.
- (Codex 2절) 같은 시각 문서 카드 묶기(UI/UX R3): `conversation.tsx` 메시지 렌더 변경이 필요해 소유권을 먼저 조정한다.
- (Codex 2절) 최종본 바닥에 저장 실패 지속 표시: `my-docs.tsx` FinalDoc 바닥은 지금 saving만 분기한다(제출은 B1 수정으로 막힌다).
- 보존할 것: `doc-viewer.tsx` 160/120ms 전환, `board.tsx` 150ms 이동, globals.css의 reduced-motion·인쇄 규칙.

**scenario-redesign**: 위 변경 요청 1·2·5. 화면은 `mission.yaml`의 파트 제목·`division_min` 문장·`release_at_min`을 State로만 읽고 하드코드하지 않았다. 단 회사 문서 이름 표(변경 요청 6)와 대기 화면의 팀 소개(한서윤·이도현)는 web에 있다.

## 후속 인수자에게

- 관문 순서: 이 보고 → UI/UX 페르소나 리뷰(위 진입 경로·조작 순서로) → Codex 코드 리뷰(`REVIEW.md`) → 사용자 mock 확인.
- 테스트는 renderToStaticMarkup + mock 라우터·MockSocket + reducer로 돌린다(jsdom 없음). 기능 테스트를 늘릴 때도 같은 방식.
- 브라우저 확인은 Claude in Chrome으로 했다. 스크린샷은 저장하지 않았다.

## 수정 라운드 1 (UI/UX 리뷰 반영, 2026-10-21)

브리프 `docs/handoff/briefs/brief-web-redesign-fix.md`, 리뷰 원문 `docs/handoff/reviews/review-uiux-view.md`(함께 커밋, 스크린샷 폴더는 `.gitignore`). 같은 브랜치에서 이어서 작업했다. 사용자 추가 결정 (a) 긴 최종본 섹션 접기, (b) 제품 UI 말투도 이번 라운드에 넣었다.

### 확인

```
pnpm test   # Test Files 10 passed, Tests 10 passed
pnpm lint   # eslint + prettier --check 통과
NEXT_PUBLIC_MOCK=1 npx next build   # 통과
```

`NEXT_PUBLIC_MOCK=1 pnpm dev`에서 Chrome(1440)으로 동의 화면, 오피스 첫 화면·자료 탭, 보내기 팝오버(카드만 올라감, 보낸 뒤 "바뀐 내용 없음"), mock "마감 2분 전으로"(마감 배너·개인 알림 토스트), "연결 끊기"(상단 배너·"연결되면 전송"), "다른 창에서 접속"(전체 오버레이), 리포트 "도움 요청" 카드(끊김 칩·판정 창 문구)를 직접 확인했다. review-animations는 새 모션(보내기 팝오버 150ms, 트리거 기준 scale 0.95+opacity)만 늘었고 기준 안이다. break-ui는 새 문구 줄에서 `?data=worst` 넘침이 없음을 확인했다.

### 항목별 처리

| # | 처리 | 내용 |
|---|---|---|
| B1 | 고침 | 접속 교체(4000)·접속 불가(4403)는 화면 전체 오버레이 + 입력 잠금 + "이 창에서 다시 열기"(새로고침). 끊김은 가운데 위 배너 "연결 끊김 · 다시 연결 중", 대기 메시지는 "연결되면 전송", 레일의 작은 빨간 글자는 지움 |
| B2 | 고침 | 자료 탭 미공개 문서는 "공유 예정"만(시각 없음). 세션 중 공개된 문서는 "공개됨" 칩(개인 알림의 "공개됐어요" 줄로 판정) |
| B3 | 고침 | 동의 화면: 기록(원문 + "세션 종료 후 90일 보관, 이후 삭제"), 점수 산정(+ "관찰 요소: …" `elements_names`), 판정하지 않는 것(+ "어시스턴트 사용 여부는 점수와 무관") |
| B4 | 고침 | 남은 시간은 `remainText`("1분 42초"). 10분 전부터 가운데 위 마감 배너, 보고 대기 배너도 "4분 12초 남음". 마감·제출 줄은 맨 아래가 아니어도 끝까지 스크롤. 2분 전 토스트 확인 |
| B5 | 고침 | dev 전환은 오른쪽 아래 접힘 칩("data ◂"). 오피스(/s/)에서는 칩을 숨기고 "mock 조작" 패널 첫 줄에 같은 전환 |
| B6 | 고침 | mock `report.json` 카드에 `window {start_min,end_min}`, label 항목은 판정 창 지원자 메시지를 evidence로(resp_proposed_alternative ← m-31, adapt_raised_scope ← m-36). 카드 머리에 "이 구간 연결 끊김 00:31~00:46", label 항목 근거가 비면 "판정 창 00:30~00:45 지원자 메시지 없음", 카드 본문에 판정 창 행 |
| B7 | 고침 | 보내기 팝오버: 채널 두 개 + "한마디(선택)". `share {channel, note?}`, 카드 본문은 note뿐(없으면 빈 문자열). mock 동료 보내기 문구도 짧은 한마디("방향 봐 주세요." / "지시 반영했어요.") |
| B8 | scenario로 | 서버 문장(`scoring_notice`·`persona_note`)을 그대로 보인다. web 수정 없음 |
| R1 | 고침 | 분업 전 내 문서 탭 위 "먼저 보드에서 카드 5장의 담당 정하기 [보드로 →]", 도움말·대기 화면에 "진행 순서 ①②③"(① 보드에서 나누기) |
| R2 | 고침(설계 판단 4 뒤집음) | 대화 채널의 "○○님이 「…」을 보냈어요" 줄을 없앴다. 카드 메타(주인·버전)로 충분하고 기록 화면에 share 행이 남는다 |
| R3 | polish로 | 같은 분에 온 동료 문서 카드 묶음 |
| R4 | 고침 | 분업 확정 전의 내 담당 지정 줄은 남기지 않고 "분업이 정해졌어요" 한 줄로. 문구는 "1번 담당 → 나", "3번 → 진행 중 (도현)", "1번 언제까지 → 00:40" |
| R5 | 고침 | 개인 알림은 편집 여부와 무관하게 토스트 |
| R6 | 고침 | 제출 확인 창에 "비어 있는 섹션: 1·2·3·5번", 빈 섹션이 있으면 제출 버튼을 보조 스타일로, 바닥에 "빈 섹션 N개" |
| R7 | 고침 | 마지막으로 보낸 뒤 저장된 편집이 없으면 보내기 비활성 + "바뀐 내용 없음" |
| R8 | 고침 | 저장 표시는 "방금 저장"/"N분 전 저장". 리포트·전체 기록의 세션 시각은 오피스와 같은 00:45(`sessionClock`). 응답 시간 같은 길이 값은 "2분" 그대로 |
| R9 | 고침 | 1분 미만 끊김은 줄 없이 재연결 토스트("연결이 다시 이어졌어요")만, 끊김 줄 색은 muted |
| R10 | 고침(줄 삭제로 해소) | 보낸 줄이 없어졌고, 보내기 토스트는 "을(를)" |
| R11 | 고침 | 카드 상세 의존 행에 "3번이 이 카드를 기다림"(역방향) |
| R12 | 고침 | 빈 담당은 점선 알약 "+ 담당" |
| R13 | scenario로 | 422 문장은 api message 그대로 |
| R14 | 고침 | 지금 가운데에 보이는 채널의 메시지는 토스트 생략(문서를 열어 대화가 가려졌으면 띄움) |
| R15 | 고침 | 최종본 섹션 "가져오기" 목록은 같은 파트를 맨 위에 "같은 파트" 꼬리표. 내 문서는 "현재 저장본"(`version: null`) |
| R16 | 고침 | 디브리핑 머리에 "아래 장면은 모두 미리 준비된 연출입니다." 한 번, 카드에서는 뺐다 |
| R17 | 고침 | 세션 실패 화면은 서버 문장 하나 + 연락처(디브리핑에 없으면 입장 정보 `contact_email`). 만료(410)는 응답에 연락처가 없어 기존 안내 문장 그대로 |
| R18 | 고침(값은 scenario) | `session.alias`를 쓰고 킥오프 파싱은 폴백. mock `state*.json`에 `alias: "지원자A"` |
| R19 | scenario로 | mock 대본 상태 무시는 데모 한계로 둠 |
| R20 | 고침 | "기록에서 보기"가 `?card=<카드>`를 달고, 기록 화면의 "리포트로 돌아가기"가 `#card-<카드>`로 돌아가 그 카드를 펼치고 스크롤. 기록 화면 머리(돌아가기·필터) 고정 |
| R21 | 고침(일부) | "1번 카드 assignee 변경(12분)" → "1번 담당 변경 · 00:12", 알림 주체 "리서치 담당". 바뀐 값(누구로·언제까지)은 기록 응답에 없어 못 보인다(변경 요청 8) |
| R22 | 고침 | draft에서 값을 바꾸면 칩이 "미충족 → 충족(조정)" |
| R23 | 고침 | 머리 문구를 두 줄로, draft에 "조정: 카드 펼침 → 항목 값 변경(메모 필수) → 맨 아래 검토 완료", 요약표 행 hover·↓ |
| R24 | 고침 | 주고받은 문서 표에서 한 번도 쓰거나 보내지 않은 주담당 문서 행 숨김 |
| R25 | 고침 | 샘플은 조정 select를 비활성으로 보이고 "실제 리포트: 항목 값 변경·메모 입력(샘플은 비활성)", 삭제 예정일 숨김 |
| R26 | 고침 | 초대 성공 시 폼을 비움(key 교체), 지원자 카드 머리에 "지원자 초대" 버튼(폼으로 이동) |
| R27 | scenario로 | 픽스처 candidate_count |
| R28 | 고침 | 끝난 세션은 "… 종료"(진행·보고 중만 "종료 예정"), 시작 뒤 취소는 "중도 종료됨", 확인 창 버튼 "돌아가기 / 세션 끝내기" |
| R29 | 고침 | 요소별 칩 앞에 "요소별 충족·미충족·기록 없음" 범례 |
| R30 | 사용자 결정 | 카탈로그 문구는 scenario. 화면 라벨은 아래 (b)로 바꿈 |
| R31 | 고침(문구) | "리포트 메모"(리포트 전체 메모 · 점수는 그대로) |
| 계약: approving 묶음 | 고침 | mock에서 확정 중은 "완료" 묶음(설계 판단 6 뒤집음) |
| 사용자 (a) | 고침 | 리포트 최종본 섹션이 360자를 넘으면 5줄로 접고 "더 보기/접기", 인쇄는 전부 펼침 |
| 사용자 (b) | 고침 | 생성 화면 요소 카드 라벨을 "한 줄 설명 / 관찰 기준 / 미선택 시"(명사형 dl)로. 머리 "관찰 요소 n/5 선택 · 체크 해제로 제외". 오피스·동의·대기·디브리핑·리포트·목록의 안내 문구를 명사형·짧은 문장으로(예: "2시간 연속 · 중간 휴식 없음 · PC 권장", "제출 후 수정 불가", "받기 전용 채널"). 오류·토스트는 짧은 문장 유지 |

### 바뀐 설계 판단

- 판단 4(보냈어요 줄을 카드 위에) → **대화에서 줄을 없앰**(R2). SystemLine 종류에서 "문서 보냄"은 전체 기록에만 남는다.
- 판단 6(확정 중을 검토 필요에) → **"완료" 묶음**(계약 결정).
- 판단 7(디브리핑 "점수" 회피 제목)은 유지. 본문은 서버 문장(B8 scenario 몫).
- 새 판단: 오피스에서 dev 전환은 칩이 아니라 mock 조작 패널 안(최종본 "제출" 버튼과 오른쪽 아래 자리가 겹쳐서).
- 새 판단: 자료 탭의 "공개됨" 칩은 개인 알림 채널의 공개 줄로 판정한다(State에 "세션 중 공개" 표시가 없어서).

### 진입 경로·조작 변경점

- 입장 화면 버튼 이름이 "안내 확인하고 다음" → "다음"으로 바뀌었다(동의 화면 "동의하고 계속"은 그대로).
- dev 데이터 전환: 관리자 화면은 오른쪽 아래 "data ◂" 칩, 오피스는 "mock 조작" 패널 첫 줄.
- 보내기: 내 문서 편집기 "vN 보내기" → 팝오버에서 채널·한마디 → "vN 보내기".
- 리포트 → "기록에서 보기" → "리포트로 돌아가기"가 그 카드로 돌아온다.
- 오버레이 확인: `/s/live` → mock 조작 "다른 창에서 접속". 끊김 배너: "연결 끊기". 마감 배너: "마감 2분 전으로"(10분 전부터 보임).

### 변경 요청(추가)

8. **전체 기록의 보드 행에 바뀐 값**: `GET /admin/sessions/{id}/record`의 task_event `summary`가 필드 이름만 준다. 계획성 근거로 쓰려면 `old_value·new_value`(또는 사람 말 요약 "1번 담당 → 지원자")가 필요하다. web은 지금 필드 이름만 한국어로 바꾼다.
9. **mock 픽스처 복사본 차이**: 계약 변경에 맞춰 web 복사본 `state.json`·`state_reporting.json`(session.alias), `report.json`(카드 window, label 항목 evidence)을 직접 고쳤다. 공용 `tests/fixtures/contracts/`가 같은 값으로 갱신되면 다시 복사한다.

## 수정 라운드 2 (Codex 코드 리뷰 반영, 2026-10-21)

원문 `REVIEW.md`(저장소 루트, 커밋하지 않음). 차단 B1~B6 전부 고쳤고 2절의 "가져오기 전 원본 저장 flush"·"vnull 문구"도 함께 고쳤다. 나머지 2절 항목은 위 "다른 트랙에 알릴 것"에 web-integrate/web-polish로 적었다.

### 확인

```
pnpm test   # Test Files 11 passed, Tests 11 passed (saver.test.ts 추가)
pnpm lint   # eslint + prettier --check 통과
NEXT_PUBLIC_MOCK=1 npx next build   # 통과
```

브라우저(1440): `/s/live`에서 메시지 입력창에 포커스를 둔 채 mock "다른 창에서 접속" → 포커스가 대화 상자 버튼("이 창에서 다시 열기")으로 옮겨지고 Escape로 닫히지 않음을 확인했다.

### 항목별 처리

| # | 처리 | 내용 |
|---|---|---|
| B1 | 고침 | `components/office/saver.ts` 새로 만듦: 문서별 디바운스 + 진행 중 Promise 직렬화, `flush`는 예약·진행 중 저장을 끝까지 기다려 성공 여부를 돌려주고 직전 실패는 다시 시도. 저장 작업은 실패하면 throw. 제출·보내기·가져오기는 `flush`가 false면 멈추고 "저장되지 않아 …을(를) 멈췄어요" 토스트. 테스트 1건 `saver.test.ts`(느린 저장 중 제출은 저장 뒤에, 저장 실패면 제출 차단) |
| B2 | 고침 | reducer에 `dirty {parts, final}`: `doc_edit`·`final_edit`가 기록하고 저장 성공(`doc_saved`·`final_saved`에 저장한 본문)과 같은 본문일 때만 지운다. 스냅샷은 진행 중이면 dirty를 다시 얹는다(제출 뒤 스냅샷은 서버 값 그대로). 가져오기 결과는 서버 값이 정본이라 그 섹션의 dirty를 지운다. `docs-flow.test.ts`에 파트·최종본 각각 복원 확인 추가 |
| B3 | 고침 | `locked()`에 `replaced` 포함, WS 상태 4000·4403과 `session.replaced` 프레임에서 `stopped` 액션 + `saver.stop()`(예약 저장 폐기, 새 저장 거부), 보드·저장 진입점도 replaced면 무시. 가림막은 base-ui 모달 Dialog(포커스 가둠·배경 입력 차단·닫기 없음)로 바꿈 |
| B4 | 고침 | 정직 사실 표의 최종본 출처 작성자를 `facts.shares[].owner`와 `deliverable.documents[].owner`의 doc_id → owner로 정한다(없으면 "출처 미상"). id 모양 추측 제거 |
| B5 | 고침 | `dropIndex()`: 같은 칸에서는 원래 칸의 over 위치(arrayMove와 같은 결과), 칸에 놓으면 맨 끝. `board.test.tsx`에 아래·맨 끝·위 이동 확인 추가 |
| B6 | 고침 | `reviewBodyFrom(report)`: 서버 리포트의 조정 항목(reviewer·memo)·전체 메모·검토자 이름으로 같은 본문을 만든다. 재진입 뒤 "확정 다시 시도"가 이 본문을 보내고, 재시도 오류는 확정 중 안내 안에 보인다. mock의 본문 비교는 항목 순서와 무관하게 바꿈. `report-view.test.tsx`에 멈춘 확정 → 복원 본문 재전송 → final 확인 추가 |
| 2절: 가져오기 전 원본 저장 | 고침 | 가져오기 전에 최종본과, 출처가 내 문서면 그 파트의 저장도 flush하고 실패하면 멈춘다 |
| 2절: vnull 문구 | 고침 | 출처 version이 null이면 "내 문서 현재 저장본에서"(지원자 최종본 칩), "주담당 문서 현재 저장본에서"(리포트 출처 칩), 정직 표 "현재 저장본" |
| 2절 나머지 | web-integrate·web-polish로 | 위 "다른 트랙에 알릴 것"에 적음 |

### 바뀐 구조

- 저장 경계가 `saver.ts` 하나로 모였다. OfficeContainer는 `schedule`(디바운스)·`ensureSaved`(flush + 실패 안내)만 쓴다.
- 접속 교체 화면은 일반 div가 아니라 모달 Dialog다. 닫을 수 없고 새로고침으로만 다시 연다.

### 재확인 반영 (REVIEW.md "## 재확인" R2-1~R2-3)

| # | 처리 | 내용 |
|---|---|---|
| R2-1 | 고침 | `saver.flush`가 한 바퀴로 끝나지 않고, 기다리는 사이 새로 예약된 저장·진행 중 저장이 없을 때까지 반복한다(직전 실패분은 바퀴마다 한 번씩만 재시도). 제출은 준비 시작부터 `submitting`으로 편집을 잠그고, 저장 확인이 실패하면 잠금을 푼다 |
| R2-2 | 고침 | reducer에 저장 세대 `saveSeq`와 마지막 저장 본문 `confirmed {parts, final}`. 재동기화는 조회 시작 시점의 `since`를 함께 넘기고, 스냅샷 적용 때 since보다 뒤에 저장된 본문을 먼저, 그다음 미저장 편집을 얹는다. 가져오기는 서버 값이 정본이라 그 섹션의 confirmed도 버린다 |
| R2-3 | 고침 | `flush`는 매 바퀴와 끝에서 stop 여부를 다시 보고 멈췄으면 false. `ensureSaved`는 flush 뒤 `replaced`를 다시 확인해 후속 REST 쓰기(공유·가져오기·제출)를 하지 않는다 |
| lint | 고침 | `candidate-flow.tsx` 소켓 effect 의존성에 `saver`(마운트 동안 같은 객체) 추가. `eslint --max-warnings 0` 통과 |

테스트: `saver.test.ts`에 "느린 저장 중 추가 입력도 저장 뒤 제출"·"기다리는 사이 stop이면 제출 안 함", `docs-flow.test.ts`에 "저장 뒤 도착한 옛 스냅샷이 최신 본문을 덮지 않음" 확인을 더했다(파일 수는 그대로).

```
pnpm test   # Test Files 11 passed, Tests 11 passed
pnpm lint   # eslint(경고 0) + prettier --check 통과
NEXT_PUBLIC_MOCK=1 npx next build   # 통과
```
