# web-polish 보고서

브리프 `docs/handoff/briefs/brief-web-polish.md`. 브랜치 `track/web-polish`, 기준 커밋 main 2019069(브리프 커밋 753ea69 위). 계약 커밋 37bed0b, 계약 변경 없음. 실제 스택은 쓰지 않았다(`NEXT_PUBLIC_MOCK=1`).

## 확인

```
pnpm test    # Test Files 11 passed, Tests 11 passed (새 테스트 없음)
pnpm lint    # eslint + prettier --check 통과
NEXT_PUBLIC_MOCK=1 npx next build   # 실행 못 함: 이 세션의 자동 권한 분류기가 .next 덮어쓰기로 보고 막았다. 병합 전 한 번 돌려야 한다
```

- 타입: `npx tsc --noEmit` 통과.
- 화면: headless Chrome(puppeteer-core, CDP)으로 `NEXT_PUBLIC_MOCK=1 pnpm dev`를 열어 확인했다. 스크린샷 9장 `docs/handoff/reports/web-polish-shots/{office,report,create}-{1280,1440,1920}.png`(`.gitignore`에 추가). 오피스 장은 `/s/live`에서 4번 받은 문서를 가운데에 열고 오른쪽에서 1번 내 문서를 편집하는 상태다.
- dev 서버는 종료했다(포트 3000 비어 있음).

## 항목별 처리

| # | 항목 | 처리 |
|---|---|---|
| 1 | 모션 점검 | 아래 review-animations 표. 고친 것: 버튼 easing을 기본 `ease-out`에서 `var(--ease-out)`로, 보드 카드 드롭 scale 1.02→0.98→1, 보드 이동의 동작 줄이기 처리. 보존: doc-viewer 160/120ms, board 150ms, globals.css의 reduced-motion·인쇄 규칙(손대지 않음) |
| 2 | 반응형 | 1280: 열 폭(232 / 가운데 / 440)을 그대로 두었다. 문서 보기 머리, 보내기 팝오버, 가져오기 메뉴, 제출 확인 창이 1280에서 잘리지 않고 동작함을 확인해 레일 접기는 하지 않았다. ≥1440: 가운데와 작업 패널을 `1fr 1fr`로 나눈다. 받은 문서를 가운데에 연 채 오른쪽에서 내 문서를 고치는 분할 보기가 되고, 1920에서 대화 줄이 1200px까지 늘어나던 문제도 줄었다 |
| 2 | 넓은 보드 | 보드 루트를 `@container`로 두고, 패널 폭이 680px 이상(뷰포트 약 1600 이상)이면 칸 3개를 가로로 놓고 카드 제목은 두 줄까지 보인다. 1440에서는 패널이 604px라 세로 배치를 유지한다 |
| 3 | 브랜드 | `public/brand/wordmark.svg`(파란 둥근 사각 안 "0" 마크 + 단선 글자 "Day Zero", 글꼴 없이 선으로 그림), `public/brand/favicon.svg`(마크만). `components/ui/wordmark.tsx`(새 컴포넌트, next/image)를 입장·동의·대기·링크 안내(`link-screens.tsx` Page), 관리자 로그인·가입(`auth-form.tsx`), 관리자 셸 머리(`shell.tsx`), 디브리핑(`debrief-screen.tsx`)에 적용했다. 파비콘은 `app/layout.tsx` metadata `icons` |
| 4 | R3 카드 묶음 | `conversation.tsx` Timeline: 같은 보낸 사람이 같은 분(시계 표시 기준)에 보낸 문서 카드 메시지가 이어지면 머리를 한 번만 그리고, 한마디는 줄마다, 카드는 작은 카드 2열로 그린다. 메시지·reducer는 그대로이고 표시만 묶는다. 묶음에 새로 붙은 줄·카드만 120ms 페이드 |
| 4 | 최종본 저장 실패 지속 표시 | `my-docs.tsx` FinalDoc 바닥: `save === "failed"`면 다음 저장이 성공할 때까지 danger 색 "저장 실패 · 다음 편집 때 다시 저장"(마감 2분 전 문구보다 우선, 제출 완료보다는 뒤) |
| 4 | "현재 저장본" 문구 | 이미 처리되어 있었다(수정 라운드 2 "vnull 문구": `sourceLabel`, `importChoices`, 리포트 출처). 변경 없음 |
| 4 | 빈 완료 칸 접기 | 완료 칸이 비면 머리 한 줄("완료 0 · 끝난 카드를 여기로")로 접는다. 칸 전체가 놓을 자리라 카드를 끌어 오면 들어가며 펼쳐진다 |
| 5 | break-ui | 아래 표 |

## 바뀐 파일

| 파일 | 내용 |
|---|---|
| `apps/web/components/ui/button.tsx` | easing을 `ease-[var(--ease-out)]`로(props 그대로) |
| `apps/web/components/ui/wordmark.tsx`, `index.ts` | 새 컴포넌트 `Wordmark({className})`와 export |
| `apps/web/public/brand/wordmark.svg`, `favicon.svg` | 새 파일 |
| `apps/web/components/office/office-view.tsx` | 그리드 열 한 줄과 주석 |
| `apps/web/components/office/conversation.tsx` | DocCard `small`, DocGroupRow, Timeline 묶음 계산 |
| `apps/web/components/office/my-docs.tsx` | FinalDoc 바닥 문구 분기와 색 |
| `apps/web/components/office/board.tsx` | 드롭 scale, 동작 줄이기, 넓은 보드 container query, 빈 완료 칸 접기 |
| `apps/web/components/office/link-screens.tsx`, `debrief-screen.tsx` | "Day Zero" 글자를 Wordmark로 |
| `apps/web/components/admin/auth-form.tsx`, `shell.tsx`, `apps/web/app/layout.tsx` | Wordmark 적용, 파비콘 |
| `.gitignore` | `docs/handoff/reports/web-polish-shots/` |

**허용 파일 밖을 건드린 것**: 브랜드 적용(범위 3)이 로그인·입장·대기·관리자 셸을 요구하지만 그 화면은 허용 목록(`ui/`·`globals.css`·`brand/`·office 4개 파일) 밖이다. 같은 시각 `apps/web`을 고치는 다른 pane이 없어서(web-integrate는 이 트랙 병합 뒤 시작) 표시만 바꾸는 import 1줄 + 요소 1줄 수준으로 `link-screens.tsx`, `debrief-screen.tsx`, `auth-form.tsx`, `shell.tsx`, `app/layout.tsx`를 고쳤다. 디브리핑은 브리프 목록에 없지만 같은 "Day Zero" 글자 표기라 함께 바꿨다. 되돌려야 하면 이 다섯 파일의 diff만 빼면 된다(워드마크 파일은 남아도 무해).

## review-animations

| Before | After | Why |
|---|---|---|
| `button.tsx:7` `ease-out`(내장) | `ease-[var(--ease-out)]` | 내장 ease-out이 약하다. 누름 피드백은 강한 곡선(cubic-bezier(0.23,1,0.32,1)) |
| `board.tsx` 끄는 카드 `scale-[1.02]`(전환 없음) | 끄는 동안 `scale-[0.98]`, 놓으면 `scale 150ms var(--ease-out)`로 1 | design-system.md "드롭 시 scale 0.98 → 1". `scale` 속성은 dnd-kit의 inline `transform`과 따로 전환돼 끊기지 않는다 |
| `board.tsx` sortable 이동 150ms, reduced-motion 처리 없음 | `useReducedMotion()`이면 `transition: null`, 드래그 scale은 `motion-reduce:scale-100` | 위치 이동은 동작 줄이기에서 뺀다 |

검토하고 그대로 둔 것:

| 대상 | 판단 |
|---|---|
| `doc-viewer.tsx` 열기 160ms·닫기 120ms, translateY 12/8px, reduce면 opacity만 | 기준 안(서랍류 200ms 이하, ease-out, 보존 대상) |
| `menu.tsx`·보내기 팝오버 150ms, scale 0.95, `origin-[var(--transform-origin)]` | 트리거 기준 원점, 드롭다운 기준 안 |
| `confirm-dialog.tsx`·도움말 대화 상자 200ms scale 0.97, 가운데 원점 | 모달은 원점 예외, 기준 안 |
| `.press` 100ms `var(--ease-out)` scale 0.97 | 누름 피드백 기준 안, reduce에서 끔 |
| `.arrive` 120ms 페이드(키프레임) | 메시지마다 새 요소에 한 번만 붙어 되감기 문제가 없다. transform을 넣으면 맨 아래 따라가기 스크롤과 겹쳐 흔들려서 페이드만 둔다(design-system.md) |
| 보드 sortable easing `cubic-bezier(0.23, 1, 0.32, 1)`(강한 ease-out, 150ms) | 끄는 사용자의 입력에 비켜 주는 응답이라 ease-in-out보다 빠르게 시작하는 쪽을 유지 |
| Sonner 토스트 | 라이브러리 기본(transition 기반, reduced-motion 자체 처리). 보존 |
| `office-view.tsx` 타이머 색 300ms | 10분 전 1회 색 전환, 깜빡임 없음 |
| hover | 전부 색 전환뿐이라 pointer 게이팅이 필요한 hover 이동이 없다 |
| 범위 밖 참고: `admin/report-view.tsx:582` 화살표 회전 `duration-150` 내장 easing | web-integrate 소유. 회전 150ms라 체감 문제는 없어 알리기만 한다 |

**결정: Approve.** `transition: all`, `scale(0)`, `ease-in`, 300ms 초과, 레이아웃 속성 애니메이션 없음. 느낌 확인(2~5배 느리게)은 드롭 scale 하나만 남는다.

## break-ui

`?data=worst`(긴 별칭 "Aleksandra Wiśniewska-Kowalczyk", 긴 이메일, 긴 채용 건 이름, 공백 없는 URL이 든 긴 메시지, 14문단 문서)로 1280에서 오피스(대화 위·아래, 내 문서 편집, 최종본, 보드, 알림 채널, 어시스턴트)와 관리자(목록, 리포트)를 보고, 1440·1920은 일반 데이터로 봤다.

| # | 등급 | 필드 | 값 | 결과 | 처리 |
|---|---|---|---|---|---|
| 1 | Fragile | 저장 시각 | mock `updated_at`(고정 픽스처 시각) | 편집기 바닥이 "947분 전 저장"으로 보인다. 실제 서버 시각이면 정상 | 표시 로직은 맞다. mock 픽스처 한계로 둔다(web-integrate가 실서버에서 확인) |
| 2 | Fragile | 문서 묶음 | 같은 분에 한마디가 비어 있는 카드 여러 장 | 한마디 줄 없이 카드 2열만 보이도록 처리(빈 `content`는 줄을 그리지 않음) | 고침(묶음 구현 안에서) |

버티는 것: 긴 별칭은 레일에서 두 줄로 감기고 메시지 머리·리포트 제목에서 넘치지 않는다. 공백 없는 URL은 `break-words`로 감긴다. 긴 문서는 편집기·문서 보기·리포트 접기에서 스크롤·더 보기로 처리된다. 빈 알림 채널은 시스템 줄만, 빈 대화는 "아직 대화 없음". 요소 5개 카드(번호 칩·제목·의존 칩·언제까지 칩·담당 2명)는 칩 줄이 감기고 아바타가 `shrink-0`이라 겹치지 않는다(넓은 보드 2열 제목에서도). 긴 채용 건 이름은 목록 카드에서 한 줄 안, 리포트 머리에서 감긴다. 1280에서 보내기 팝오버(w-72, end 정렬)·가져오기 메뉴·제출 확인 창이 패널 안에 들어온다.

## 남은 문제

- `next build`를 이 세션에서 실행하지 못했다(권한 분류기 차단). lint·test·tsc는 통과했다. 병합 전 `cd apps/web && NEXT_PUBLIC_MOCK=1 npx next build`를 한 번 돌려야 한다.
- Next 16 dev가 첫 실행에 `apps/web/AGENTS.md`를 다시 만들었다. 이 트랙 파일이 아니라 커밋하지 않았고, 삭제도 권한 분류기가 막아 작업 폴더에 남아 있다.
- 1920 분할 보기에서 오른쪽 편집기 줄이 840px까지 길다. 본문 최대 폭을 둘지는 판단이 필요하다(지금은 그대로).
- 저장 실패 바닥 표시는 mock에서 실패를 만들 조작이 없어 화면으로는 보지 못했고 코드로만 확인했다.

## web-integrate에 알릴 것(office 파일에서 이 트랙이 바꾼 줄)

상태 로직·API·reducer·saver는 건드리지 않았다. 아래는 모두 표시용이다.

- `office-view.tsx`: 최상위 `<div className="grid … min-[1440px]:grid-cols-[232px_minmax(0,1fr)_minmax(0,1fr)]">`와 그 위 주석 한 줄(248행 근처).
- `conversation.tsx`: `DocCard`의 `small` prop과 분기, 새 `DocGroupRow`, `Timeline` 안의 `groups`/`grouped` 계산과 map 맨 앞 분기. 묶음은 `items`에서 매번 다시 계산하며 메시지 id·`seen`(페이드 판정)을 그대로 쓴다.
- `my-docs.tsx`: FinalDoc 바닥 `<span>`의 className과 문구 삼항(`save === "failed"` 분기 추가, 344~362행).
- `board.tsx`: BoardCard의 `useReducedMotion`·`style.transition`·드래그 scale 클래스, 제목 span의 `@min-[680px]` 클래스, `Column`의 `folded`, Board 루트 `@container`와 칸 감싸는 div. `onDragOver`·`onDragEnd`·`dropIndex`·`moveTask`는 그대로다.
- 브랜드: `link-screens.tsx`·`debrief-screen.tsx`·`admin/auth-form.tsx`·`admin/shell.tsx`·`app/layout.tsx`에서 Wordmark·파비콘 줄만 바꿨다.
- **최종본 저장 실패 표시가 재편집만으로 사라진다(Codex B2, web-integrate 몫).** `my-docs.tsx` FinalDoc 바닥은 `save === "failed"`일 때만 실패를 보이는데, `candidate-flow.tsx`의 schedule이 다음 입력 즉시 `saving`으로 바꿔 성공 응답 전에 실패 안내가 "저장 중…"이나 마감 문구로 바뀐다. 디바운스가 밀리는 동안에도 안내가 없다. 지금 props로는 `saving`이 첫 저장인지 실패 뒤 재시도인지 알 수 없으므로, flow·saver 쪽에서 "진행 중"과 "해결되지 않은 실패"를 나눠 넘기고 성공 응답에서만 실패를 지워야 한다. 완료 확인: 실패 뒤 재편집·재시도 중에도 안내 유지, 성공 뒤 해제, 제출 잠금·flush 차단 유지. 실제 API 지연·실패·복구에서 제출 전 flush와 함께 확인한다.
- 문서 카드 메시지는 한 장일 때부터 `DocGroupRow`로 그린다(아래 수정 라운드 B1). 묶음 계산을 바꾸거나 단일 카드를 `MessageRow`로 되돌리면 두 번째 카드 도착 때 첫 카드가 다시 마운트되어 포커스가 사라진다. 개별 `message.new`로 카드가 늘어나는 경로에서 확인한다.

## 수정 라운드(Codex)

리뷰 원문 `REVIEW.md`(저장소 루트, 커밋하지 않음). 판정 "수정 후 승인", Block 사유 B1.

| # | 처리 | 내용 |
|---|---|---|
| B1 | 고침 | `conversation.tsx`: 알림 채널이 아닌 문서 카드 메시지는 한 장이어도 `DocGroupRow`로 그린다(key = 첫 메시지 id). 두 번째 카드가 오면 같은 행·같은 카드 칸(`key = message id`)에 붙고, 바뀌는 것은 칸의 열 수(`max-w-md` → `grid-cols-2 max-w-2xl`)와 카드의 `small` prop뿐이라 첫 카드 버튼 DOM과 포커스가 유지된다. 페이드는 화면을 연 뒤 온 행에 한 번, 뒤늦게 붙은 줄·카드에만 붙는다. 첫 카드 칸에는 `arrive`를 붙이지 않고 행 클래스는 바뀌지 않아 다시 재생되지 않는다. `DocCard`의 바깥 여백·최대 폭은 호출부로 옮겼다(`MessageRow`는 `mt-1.5 max-w-md` 감싸개) |
| B2 | web-integrate로 | 위 "web-integrate에 알릴 것"에 적었다. flow·saver는 건드리지 않았다 |
| P3 button | 고침 | `button.tsx` 전환 대상 `transition-[background-color,transform,scale]`. Tailwind v4의 `active:scale-[0.97]`는 개별 `scale` 속성이라 이전에는 누름 크기가 전환되지 않았다 |
| P3 wordmark | 고침 | `wordmark.tsx` 기본 `h-6`을 빼고 높이는 호출부(`h-5`·`h-6`)만 정한다. `cn`이 clsx라 기본값이 호출부 `h-5`를 덮던 문제 |
| 보고서 | 고침 | review-animations "그대로 둔 것" 표의 보드 easing을 실제 값 `cubic-bezier(0.23, 1, 0.32, 1)`로 바로잡음 |

### B1 확인

실제 `Timeline`을 import해 esbuild로 묶은 임시 브라우저 화면(headless Chrome, 저장소 밖 scratchpad)에서 빈 타임라인 → `m-20`(3번 카드) 수신 → 첫 카드에 포커스 → 같은 사람·같은 분 `m-21`(4번 카드) 수신:

```
sameNode: true, connected: true, focus: true, cards: 2
첫 카드 칸 class "min-w-0"(애니메이션 없음), 행 애니메이션 재생 없음
새 카드 칸 class "min-w-0 arrive", 애니메이션 arrive 재생 중
```

### 확인

```
pnpm test    # Test Files 11 passed, Tests 11 passed
pnpm lint    # eslint + prettier --check 통과
NEXT_PUBLIC_MOCK=1 npx next build   # 통과(첫 라운드에서 못 돌린 빌드도 이번에 통과)
```

dev 서버는 종료했다. `apps/web/AGENTS.md`(Next dev가 만든 파일)는 여전히 커밋하지 않고 남겨 두었다.
