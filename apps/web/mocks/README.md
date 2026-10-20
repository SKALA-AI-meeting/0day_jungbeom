# mocks

`NEXT_PUBLIC_MOCK=1 pnpm dev`이면 `lib/api.ts`가 네트워크 대신 `mockRequest()`를 부른다.

| 파일                                   | 소유       | 내용                                                      |
| -------------------------------------- | ---------- | --------------------------------------------------------- |
| `index.ts`, `types.ts`, `ws-replay.ts` | foundation | 경로 매칭, 두 표 합치기, WS 프레임 `{type, payload}` 재생 |
| `admin.ts`, `fixtures/admin/`          | web-admin  | 관리자 화면 경로 표 `ROUTES`와 응답 JSON(`report.json`)   |
| `office.ts`, `fixtures/office/`        | web-office | 지원자 화면 경로 표 `ROUTES`와 응답 JSON(`state.json`)    |

`fixtures/`의 JSON은 `docs/common/contracts.md` 예시(저장소 `tests/fixtures/contracts/`와 같은 내용)에서 시작한다.
