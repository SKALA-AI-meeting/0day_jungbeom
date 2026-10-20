# web-office 트랙 보고서 (W2)

브랜치 `track/web-office`, 커밋 `c4b017b`. main 병합·push는 하지 않았다.

## 완료 기준별 명령과 결과

| 완료 기준 | 테스트(파일 › 이름) | 결과 |
|---|---|---|
| 만료·완료 링크 안내 | `components/office/flow.test.tsx` › 링크 입장: 만료·취소·없는 링크는 안내만, 완료된 링크는 디브리핑을 다시 보여 준다 | 통과 |
| 동의 전 시작 불가 | 같은 파일 › 안내·동의: 동의 전에는 시작 버튼이 잠기고, 동의하면 세션 토큰으로 시작한다 | 통과 |
| 오피스 4탭·타이머 | 같은 파일 › 오피스: 상단 회사명·남은 시간 mm:ss·제출, 채널 안 읽음, 탭 4개, notice는 알림 띠 | 통과 |
| 진행 표시(ack 포함) | 같은 파일 › 진행 표시: client_msg_id로 보내고 ack로 확정, agent.progress로 입력 중·자료 찾는 중 (foundation `ws_events.json` 재생) | 통과 |
| 제출 | 같은 파일 › 제출: 기획안은 1초 디바운스로 저장하고, 제출 전 남은 저장을 끝낸 뒤 submit을 부른다 | 통과 |
| 디브리핑 | 같은 파일 › 디브리핑: 실제 상황·평가표 항목·페르소나 설명, 세션 실패면 중단 안내만 | 통과 |
| 재연결 후 상태 복원 | `lib/ws.test.ts` › 재연결: 3초 뒤 다시 붙어 /state로 메시지와 진행 중 실행을 복원하고, 4401은 재발급, 4000은 멈춘다 | 통과 |

명령:
- `cd apps/web && pnpm test`: Test Files 3 passed, Tests 8 passed (기존 health 1개 포함)
- `cd apps/web && pnpm lint`: eslint 오류 없음, prettier "All matched files use Prettier code style!"
- `npx tsc --noEmit -p apps/web`: 오류 없음
- 루트 `make test`: exit 0 (api 23 passed, business-mcp 11 passed, rag-mcp 10 passed, worker 1 passed, web 8 passed)
- 루트 `make lint`: exit 0

## `NEXT_PUBLIC_MOCK=1 pnpm dev`로 확인한 단계

포트 3000을 다른 트랙이 쓸 수 있어 `NEXT_PUBLIC_MOCK=1 pnpm exec next dev -p 3101`로 띄우고 Chrome에서 확인했다. 확인 뒤 서버는 내렸다.

1. `/s/expired`: "링크가 만료되었습니다 / 채용 담당자에게 문의해 주세요."
2. `/s/cancelled`: "취소된 초대입니다", `/s/nope`(알 수 없는 토큰, 404): "초대 링크를 찾을 수 없습니다"
3. `/s/done`: "이미 완료된 평가입니다." 아래에 디브리핑(요소별 연출 설명, 평가표 항목, 페르소나 설명, 점수 안내)
4. `/s/failed`: "시스템 문제로 평가가 중단되었습니다"와 중단 안내만(연출·페르소나 없음)
5. `/s/demo` 입장: 회사명·2시간·고정 안내 → 다음 → 동의 화면에서 체크 전 "동의하고 계속" 비활성, 체크 후 활성 → 대기 화면(팀·화면 구성 안내) → 시작하기
6. 오피스: 상단 회사명·타이머(119:59부터 감소)·제출, notice 알림 띠, 팀 채널/동료 DM, 기획안 파트 5개와 담당 배지
7. 팀 채널 전송: "보내는 중…" → ack로 확정, "이도현이 입력 중…" → "이도현이 자료 찾는 중…" → 답장, 표시 사라짐
8. 기획안 1번 입력: "저장 중…" 1초 뒤 사라짐(PUT). 동료 4번 파트는 읽기 전용, 클릭 시 "도현님 담당 파트예요. 수정 요청은 DM으로", `document.part_updated`로 초안 채워짐
9. 태스크 보드: 내 카드 3개만 상태 select, 동료 카드 2개는 텍스트. 회사 문서: 인터뷰 요약이 잠김 → `document.released`로 "새 문서" 배지와 탭 카운트, 열면 본문
10. AI 어시스턴트: 요청 → 응답과 "참고한 문서: 지표 현황"
11. `/s/live`(진행 중 재입장): `/resume`으로 토큰 재발급 후 오피스(타이머 89:59)
12. 재연결: 콘솔 `window.__officeMock.drop()` → "연결이 끊겼어요. 다시 연결하는 중…" → 3초 뒤 재연결. 보내자마자 끊은 메시지는 끊긴 동안 ack·답장을 못 받았지만 재연결 후 /state로 답장이 복원되고, 재전송한 같은 client_msg_id는 중복 없이 1건. `drop(4401)`은 재발급 후 곧바로 재연결
13. `drop(4000)`: "다른 창에서 접속했어요" 안내, 재연결하지 않음
14. 제출: 확인 창 "제출하면 세션이 끝납니다…" → 제출 → 디브리핑
15. 브라우저 콘솔 오류 없음

## 수정·추가 파일 (모두 소유 범위)

- `apps/web/app/s/[token]/page.tsx`
- `apps/web/components/office/`: `types.ts`(계약 타입), `flow.ts`(단계 판정·api 경로·제출 순서·JWT sub 읽기), `reducer.ts`(스냅샷+프레임 리듀서, 진행 표시 문구, mm:ss), `part-saver.ts`(1초 디바운스·flush), `parts.ts`, `candidate-flow.tsx`(단계 전환·연결 조립), `link-screens.tsx`, `office-view.tsx`, `chat.tsx`, `plan-doc.tsx`, `task-board.tsx`, `company-docs.tsx`, `assistant-panel.tsx`, `debrief-screen.tsx`, `flow.test.tsx`
- `apps/web/lib/ws.ts`(SessionSocket: 3초 재연결, 열릴 때마다 /state, 4401 재발급, 4000·4403 정지), `lib/ws.test.ts`
- `apps/web/mocks/office.ts`(메모리 mock 서버: 지원자 REST 전 경로, WS mock 소켓은 `replay()`로 프레임을 흘림, client_msg_id 멱등, `window.__officeMock.drop(code)`)
- `apps/web/mocks/fixtures/office/{session,frames,debrief}.json`(기존 `state.json`은 계약 예시 그대로 두고 재연결 테스트에 사용)

`components/ui/`, `lib/api.ts`, `mocks/index.ts`, `package.json`은 고치지 않았다. dev 서버가 `apps/web/AGENTS.md`를 자동 생성해 지웠다(커밋에 없음).

## 남은 문제

1. 화면 테스트는 jsdom·testing-library가 없어(`package.json`은 foundation 소유) `renderToStaticMarkup` 정적 렌더와 순수 로직(리듀서·저장기·소켓)으로 검사한다. 클릭 흐름 자체는 위 브라우저 확인으로만 검증했다.
2. 실제 api의 `POST /sessions/{id}/assistant`가 아직 없다(api-candidate 브랜치에 라우트 없음). 화면은 호출하고 실패하면 "지금은 어시스턴트를 쓸 수 없어요"를 보인다. mock에서는 즉시 응답해서 "답변 작성 중…"은 잠깐만 보인다.
3. 기획안 파트 제목을 State가 주지 않아 `components/office/parts.ts`에 카탈로그와 같은 값을 하드코딩했다(변경 요청 1).
4. 상단 회사명은 `GET /s/{token}`의 `company_name`(채용 회사)을 쓴다. 가상 회사 이름(루프랩)은 `entry_notice` 문장 안에만 있다(변경 요청 2).
5. `session_id`를 주는 응답이 `/start`뿐이라 재입장·디브리핑에서는 세션 JWT·debrief_token의 `sub`를 읽는다(변경 요청 3).
6. 실제 스택(api 8000)과의 연결 확인은 하지 않았다(브리프대로 api 상시 기동 금지, M1 끝 연결 테스트에서). api-candidate가 아직 main에 병합되지 않아 그 브랜치 코드를 읽어 응답·프레임 형식을 맞췄다.
7. 남은 시간 0초에는 클라이언트가 종료하지 않고 서버의 `session.ended`(timeout)를 기다린다.

## 변경 요청 (오케스트레이터)

1. contracts.md State 스냅샷에 `parts: [{part_no, title}]`(또는 `document`에 title)를 추가해 달라. 그러면 `parts.ts` 하드코딩을 지운다.
2. `GET /s/{token}`(또는 State)에 가상 회사 이름(`virtual_company`)을 추가할지 정해 달라. 지금 상단은 채용 회사명이다.
3. `POST /s/{token}/consent`·`/resume` 응답(또는 `GET /s/{token}`)에 `session_id`를 넣어 달라. 지금은 JWT `sub`를 디코드한다(동작은 문제없음).
4. api-candidate 변경 요청 1·2·3(close code 4401/4403, `error` 프레임, 디브리핑 실패 형태, 404 `not_found`)을 contracts.md에 반영해 달라. 이 트랙은 그 형태를 전제로 구현했다.
5. (선택) 상호작용 화면 테스트가 필요하면 foundation에 devDependencies `jsdom`, `@testing-library/react` 추가.

## 다른 트랙에 알릴 것

- **api-candidate / agent-assistant**: 화면은 `POST /sessions/{id}/assistant`의 `{call_id, message_id, content, cited_docs}`와 429 `assistant_limit`을 쓴다. 어시스턴트 실행 중 `agent.progress`(actor `assistant`)가 오면 어시스턴트 탭이 대기 표시를 한다.
- **api-candidate**: 화면은 WS가 열릴 때마다(첫 연결 포함) `/state`를 다시 받고, ack를 못 받은 메시지를 같은 `client_msg_id`로 재전송한다. 서버의 (session_id, client_msg_id) 멱등을 전제로 한다. `active_runs`의 actor로 "○○이 입력 중…"을 복원한다.
- **web-polish**: 모션 대상은 메시지 도착(`chat.tsx` 목록), 입력 중 표시(`aria-live` 줄), 문서 잠금 해제(`company-docs.tsx` "새 문서" 배지), 10분 전 타이머 경고(`office-view.tsx` `Timer`, 지금은 색만 바뀜). 레이아웃은 3열 그리드(`13rem / 가변 / 22~30rem`)로 좁은 화면 대응이 없다.
- **e2e-runner**: mock 링크 토큰 `demo`(처음부터)·`live`(진행 중)·`done`·`failed`·`expired`·`cancelled`, 개발용 `window.__officeMock.drop(code)`가 있다(mock 모드에서만).
