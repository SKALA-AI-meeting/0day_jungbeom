# mocks

`NEXT_PUBLIC_MOCK=1 pnpm dev`이면 `lib/api.ts`가 네트워크 대신 `mockRequest()`를, `lib/ws.ts`가 실제 소켓 대신 `createMockSocket()`을 쓴다.

| 파일                                   | 내용                                                                                   |
| -------------------------------------- | -------------------------------------------------------------------------------------- |
| `index.ts`, `types.ts`, `ws-replay.ts` | 경로 매칭, 두 표 합치기, WS 프레임 `{type, payload}` 재생                              |
| `admin.ts`                             | 관리자 경로 표와 메모리 상태(채용 건·지원자·리포트 검토·메모)                          |
| `office.ts`                            | 지원자 경로 표와 메모리 세션, MockSocket, 장면 진행용 `mockControls()`                 |
| `worst.ts`                             | break-ui 최악 데이터. 주소에 `?data=worst`(화면 위쪽 Demo / Worst case 전환)           |
| `fixtures/*.json`                      | `tests/fixtures/contracts/`에서 같은 이름·같은 id로 복사한 계약 예시(직접 고치지 않음) |
| `fixtures/office_script.json`          | web 전용 재생 대본: 장면 시각, 픽스처에 없는 메시지, 회사 문서 본문, 동료 답장 문구    |
| `fixtures/admin_candidates_extra.json` | 지원자 묶음 5종을 채우는 추가 행(sess-4~8, 계약 형태 그대로)                           |

계약 예시가 바뀌면 `tests/fixtures/contracts/`에서 다시 복사한다. 화면만 쓰는 데이터는 위의 두 web 전용 파일에만 더한다.

## 링크 토큰(지원자)

| 토큰                  | 상태                                                      |
| --------------------- | --------------------------------------------------------- |
| `demo`                | 처음부터: 입장 → 동의 → 대기 → 오피스 0분(보드 담당 없음) |
| `live`                | 진행 중 47.5분 재입장(`state.json`)                       |
| `reporting`           | 보고 대기 중 재입장(`state_reporting.json`)               |
| `done`                | 완료 → 디브리핑 다시 보기                                 |
| `failed`              | 세션 중단 안내                                            |
| `expired`·`cancelled` | 410 안내. 그 밖의 토큰은 404                              |

오피스 왼쪽 아래 "mock 조작"에서 다음 장면, 마감 2분 전, 시간 만료(자동 제출), 연결 끊기, 다른 창 접속, 보고 5분 지나기를 누른다. mock 서버 상태는 모듈 메모리라 새로고침하면 처음으로 돌아간다.
