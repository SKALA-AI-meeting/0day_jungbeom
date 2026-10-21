# web-integrate 보고

## 요약

목업 단계에서 데이터 계층(`lib/api.ts`·`lib/ws.ts`)이 이미 `NEXT_PUBLIC_MOCK`으로 갈려 있고 화면은 그 위에서만 돌았다. 그래서 실 연결에 필요했던 변경은 아래 세 가지뿐이다. 나머지 화면은 코드 변경 없이 `NEXT_PUBLIC_MOCK=0`에서 실 REST·WS를 쓴다(실 스택 확인은 stage-e2e).

1. 키워드 버튼 후보를 State `keyword_options`에서 읽는다. 지금까지는 `mocks/debate.ts`의 `KEYWORD_OPTIONS`(mock 대본)를 직접 import했다. `StateSnapshot` 타입에 필드를 더하고 `DebateView`가 스냅샷에서 `{option_key,label}`을 `{key,label}`로 바꿔 넘긴다.
2. AI 동료 `avatar_url`(`/assets/missions/<id>/avatars/<file>`)은 api 서버가 서빙하므로 `assetUrl()`로 `API_URL`을 붙인다(`components/ui/avatar.tsx`). mock은 `/mock-avatars/…`로 바꿔 주니 영향 없다.
3. `tests/expected-failures.txt`의 `apps/web/` 줄 8개를 지웠다. 해당 옛 테스트는 이미 토론형으로 교체돼 통과하고 있었다(office 파일은 없음).

## 화면별 연결 상태

| 화면 | 상태 |
|---|---|
| 입장·동의·시작·이어하기(`/s/{token}`, `/consent`, `/start`, `/resume`) | 코드 변경 없음. 실 api 경로와 계약 일치 확인(코드 대조), 실행 확인은 stage-e2e |
| 토론방 State·WS | 변경 없음. 열릴 때마다 `/state`, `seq` 공백 시 `needsResync` → `/state`, 3초 재연결, 4401 재발급, 4000 정지 |
| typing | 입력 중 5초 갱신·stop은 이미 구현. `composer.test.tsx`로 확인 |
| 결정 사항(키워드 버튼) | `keyword_options` 연결(변경 1) |
| 자료·어시스턴트·기획안(1초 디바운스 PUT, 409 `conflict` 시 재조회)·제출·디브리핑 | 변경 없음 |
| 관리자(로그인·채용 건·지원자 목록·리포트·조정·검토 완료·기록) | 변경 없음. `components/admin/client.ts` 경로가 계약 관리자 REST와 일치 |
| 관리자 생성·초대 | 같은 `client.ts`로 연결돼 있음(P2, 실행 확인은 후속) |

페르소나 유형 문자열은 디브리핑·관리자 화면 밖의 `app`·`components`·`lib`에 없다(grep).

## 명령·결과

| 명령 | 결과 |
|---|---|
| `apps/web`: `pnpm test` | 16 파일 42개 통과 (새 테스트 6개: `lib/api.test.ts` 5, `components/debate/composer.test.tsx` 1) |
| `pnpm lint` | 통과 |
| `pnpm build` | 통과 |
| 루트 `make test` | 통과, 기대 실패 목록에 web 줄 0 |

`lib/api.test.ts`는 `tests/fixtures/contracts/`(state_keyword·entry·slot_confirm·error)로 응답 파싱·Authorization·오류 변환을 확인한다. 기존 `lib/ws.test.ts`가 WS 재연결과 reducer의 seq 공백 처리를 이미 다룬다.

## stage-e2e에서 확인할 것

- `NEXT_PUBLIC_MOCK=0`(Dockerfile ARG)에서 AI 아바타 이미지가 api 출처(`:8000/assets/…`)로 뜨는지, CORS가 막지 않는지.
- 키워드 버튼 4개가 `/state`의 `keyword_options` 순서로 나오고 `option_key`로 확정되는지.
- 기획안 단계 진입 시 `/state` 재조회로 앞 3칸이 채워지는지(WS 프레임 없음), 두 창 편집 시 409 `conflict` 후 최신으로 바뀌는지.
- 새로고침·WS 끊김 뒤 이어하기(`/resume`)와 `seq` 공백 후 `/state` 복원.
- 디브리핑 첫 화면 전까지 응답·화면에 `persona_type`이 없는지.

## api에 요청할 것

없음. 추가로, `NEXT_PUBLIC_MOCK=0` 번들에도 `lib/api.ts`·`lib/ws.ts`의 정적 import 때문에 mock 모듈이 같이 들어간다(동작 영향 없음, 번들 크기만). 필요하면 후속에서 동적 import로 나눈다.
