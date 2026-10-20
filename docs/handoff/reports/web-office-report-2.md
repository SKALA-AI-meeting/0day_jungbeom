# web-office 수정 라운드 보고서 (Codex 리뷰 반영)

브랜치 `track/web-office`. `git rebase main`을 충돌 없이 마친 뒤(첫 커밋 `51bd0d9`) 수정 커밋 `fa6b12c`를 올렸다. main 병합·push는 하지 않았다. worktree의 `REVIEW.md`는 삭제했다(커밋에 없음). dev 서버가 자동 생성한 `apps/web/AGENTS.md`도 삭제했다.

## 수정 목록

### 반드시
1. **저장 실패 보존** (`part-saver.ts`, `flow.ts` `partSaveHandler`, `reducer.ts`, `plan-doc.tsx`)
   - 저장에 실패하면 최신 본문을 그대로 두고, `save_failed` 상태로 바꿔 파트 옆에 "저장 실패 · 다시 시도"를 띄운다(`retry()`).
   - 타이머 실행에 catch를 붙여 처리되지 않은 거부가 생기지 않는다.
   - `flush()`는 모든 파트가 저장되거나 403 처리가 끝날 때까지 기다리고, 하나라도 실패하면 거부한다.
   - `dirty`는 `saved` 성공 뒤에만 풀린다.
2. **제출 실패 처리** (`flow.ts` `submitSession`, `candidate-flow.tsx`, `office-view.tsx`)
   - flush나 submit이 실패하면 오피스를 닫지 않는다. 원고를 그대로 두고 확인 창 안에 오류(`role=alert`)를 보이며, 그대로 다시 제출할 수 있다.
   - `session_ending`·`conflict`가 오면 `/state`의 status로 실제 종료인지 확인한 뒤에만 디브리핑으로 넘어간다.
3. **재연결 경합** (`candidate-flow.tsx` `onOpen`, `reducer.ts` snapshot `frames`, `flow.ts` `fetchSnapshot`)
   - `/state`를 조회하는 동안 도착한 프레임은 화면에 바로 반영하면서 따로 모아 두고, 스냅샷 위에 순서대로 다시 적용한다.
   - 중복은 메시지 id(안 읽음은 다시 세지 않음)와 `document.part_updated`의 revision(현재 이하이면 무시), 공개 문서 `fresh` 중복 제거로 거른다.
   - `/state`가 실패하면 3초마다 다시 시도한다. 연결이 바뀌거나 화면이 닫히면 멈춘다.
   - 4401 재발급(`/resume`)이 일시 장애로 실패하면 다시 시도하고, 409 conflict(세션 종료)일 때만 닫는다.
4. **초기 notice 복원** (`reducer.ts`): 첫 스냅샷의 notice 채널 메시지를 알림 띠로 복원한다. 채널 안 읽음은 첫 스냅샷에서 세지 않는 규칙을 그대로 따로 유지한다.
5. **동료 파트 403** (`partSaveHandler`, `reducer.ts` `rejected`, `plan-doc.tsx`, `mocks/office.ts`)
   - 403 forbidden이면 그 파트의 예약된 디바운스와 저장 안 된 본문을 취소(`cancel`)하고, dirty를 푼 뒤 `/state`로 서버 본문을 되돌린다.
   - 안내 "도현님 담당 파트라 입력한 내용이 저장되지 않았어요…"를 띄운다. flush는 정상으로 끝난다.
   - mock 문서 PUT도 분업 확정 뒤 colleague 파트이면 403 `forbidden`을 돌려준다.
6. **타이머** (`reducer.ts` `deadlineOf`): `ends_at`이 있으면 그 시각을 종료 시각으로 쓰고, 없을 때만 `remaining_seconds`로 계산한다.

### 같이
- **파트별 저장 직렬화** (`part-saver.ts`): 같은 파트는 PUT을 하나씩만 보낸다. 앞 PUT이 끝나면 그사이 바뀐 최신 본문 하나만 이어서 보낸다.
- **디브리핑 410 구분** (`candidate-flow.tsx` `showDebrief`, `flow.ts` `LINK_NOTICES.debrief_expired`): `/debrief`가 410 expired를 주면 "안내를 볼 수 있는 기한이 지났습니다 / 과제 종료 후 7일이 지났습니다. 채용 담당자에게 문의해 주세요."를 보인다.
- **재입장 장애 안내** (`candidate-flow.tsx`, `link-screens.tsx` `LinkNotice onRetry`): `/resume`·`/state`가 일시 장애로 실패하면 제출 완료가 아니라 "잠시 연결할 수 없습니다"와 "다시 시도" 버튼을 보인다. 버튼은 입장 판정부터 다시 한다. 디브리핑 재조회 장애도 같은 안내를 쓴다.

### 결정 반영
State의 파트 제목·`virtual_company`·`session_id` 추가는 M2로 넘어갔으므로 지금 방식(`parts.ts` 하드코딩, 채용 회사명, JWT `sub`)을 유지했다. main의 contracts.md 보충(404 `not_found`, 디브리핑 기한 7일과 410, 실패 디브리핑 형태, 문서 PUT 403·409 `session_ending`, close code 4401·4403·4000, `error` 프레임)과 구현을 다시 대조했고, 모두 맞다.

## 테스트 단언 추가 (새 테스트 파일 없음)

| 기존 테스트 | 추가한 단언 |
|---|---|
| `flow.test.tsx` › 오피스 | 첫 스냅샷 notice가 `notices`에 복원되고 안 읽음은 0. deadline은 `Date.parse(ends_at)`이며 스냅샷을 5초 늦게 적용해도 같음. 화면 타이머 118:59 |
| `flow.test.tsx` › 제출 | 같은 파트 PUT이 겹치지 않고 최신 본문만 이어 보냄. 제출 전 PUT이 끝난(OK) 뒤 POST. 저장 실패 시 submitSession이 거부되고 POST 없음, 본문을 보존해 재시도 성공. `session_ending`은 `/state` 종료 확인 시에만 "ended", 아니면 거부. 동료 파트 403은 서버 본문 복원·`rejected` 표시·flush 정상 종료(mock API 사용) |
| `ws.test.ts` › 재연결 | `/state` 첫 실패 뒤 3초 재시도. 조회 중 도착한 메시지·문서 프레임이 스냅샷 뒤에도 남고 안 읽음이 이중으로 세지지 않음. ends_at 타이머 |

## 검증 명령과 결과

- `cd apps/web && pnpm test`: Test Files 8 passed, Tests 16 passed. 이 트랙 테스트는 `flow.test.tsx` 6개와 `ws.test.ts` 1개이고, 나머지는 main에 병합된 web-admin과 health 테스트다.
- `cd apps/web && pnpm lint`: eslint 오류 없음, prettier "All matched files use Prettier code style!"
- `cd apps/web && npx tsc --noEmit -p .`: 오류 없음
- 루트 `make test`: exit 0
- 루트 `make lint`: exit 0
- 브라우저 확인(`NEXT_PUBLIC_MOCK=1 pnpm exec next dev -p 3101`)
  - `/s/live`에서 notice 알림 띠와 타이머가 보인다.
  - 기획안 1번에 입력하고 "저장 중…"인 상태에서 곧바로 제출 → 확인 창 → flush → submit → 디브리핑 순으로 넘어간다.
  - 콘솔 오류는 없다. 확인 뒤 서버를 내렸다.

## 남은 문제

1. mock 서버는 페이지 메모리 안에 있어 새로고침하면 초기화된다. 그래서 "새로고침 뒤 notice 복원"은 브라우저에서 끝까지 재현하지 못했고, 리듀서 단위 테스트로만 확인했다. 저장 실패·제출 실패·403 UI도 mock 화면에서는 일으킬 수 없어 단위 테스트(저장기·핸들러·리듀서)로 검증했다.
2. 진행 중인 PUT이 끝나면 저장기가 그사이 바뀐 최신 본문을 1초 디바운스를 기다리지 않고 바로 보낸다. 같은 파트에서 동시 PUT은 생기지 않는다.
3. 실제 api와의 연결 확인은 이번에도 하지 않았다(M1 끝 연결 테스트 범위). `POST /sessions/{id}/assistant`는 main에도 아직 없다.
4. 이전 보고서의 남은 문제 1(jsdom 부재)은 그대로다.

## 다른 트랙에 알릴 것

- **e2e-runner**: 리뷰가 꼽은 실패·복구 경로가 화면에 구현돼 있다. 실제 API에서 다음 경로를 확인하면 된다.
  - 미저장 입력 → Lock 대기 → 제출: 저장이 끝난 뒤 POST
  - 분업 변경 중 PUT 403: 서버 본문 복원과 안내
  - 조회 중 WS 메시지: 스냅샷 뒤에도 보존
  - 책임감 알림 뒤 새로고침: 알림 띠 복원
  - 디브리핑 7일 만료: 410 안내
- **api-candidate**: 화면은 WS가 열릴 때마다 `/state`를 받고 실패하면 3초 간격으로 다시 시도한다. `/resume`의 409는 세션 종료로 해석한다.
