# web-office W2 리뷰

판정: **수정 후 재리뷰 필요**.

- 대상: `track/web-office`의 `git diff main...HEAD` 22개 파일. HEAD `c4b017b`, 비교한 main `ebd1c1b`, merge-base `837c1c1`.
- 개발자 보고서를 먼저 읽고 PRD 7장, 개발 규칙·설계·계약·mock 지침을 확인했다. 실제 서버 대조는 **main의** `candidate.py`, `ws.py`, `hub.py`를 `git show`로 읽었다. 아래 `main:경로:줄`은 그 버전의 위치다.
- 직접 검증: `apps/web`에서 `pnpm test` **3파일·8테스트 통과**, `pnpm lint` 통과, `pnpm exec tsc --noEmit --incremental false` 통과, `git diff --check main...HEAD` 통과. 실제 API 기동·통합 스택·브라우저 검증은 수행하지 않았다.
- 소스·설정·Git 상태를 변경하는 명령은 실행하지 않았다. 이 보고서만 추가했다.

## 1) 반드시 고칠 것(병합 차단)

### 1. [P1] 자동 저장 실패를 잊어버려, 저장하지 않은 원고를 제출할 수 있다

`apps/web/components/office/part-saver.ts:30`, `apps/web/components/office/part-saver.ts:31`, `apps/web/components/office/part-saver.ts:40` — 요청 전에 `latest`를 지우고 실패한 요청도 `inflight`에서 제거하므로, 실패가 끝난 다음의 `flush()`는 저장할 것이 없다고 성공한다.

재현: 저장 함수가 403을 반환하게 하고 디바운스가 끝난 뒤 `flush()`를 호출하면, 저장 재시도 없이 성공하고 제출을 허용한다. 타이머의 `void this.run()`에는 catch가 없어 unhandled rejection도 발생한다. 화면은 dirty 상태로 계속 “저장 중…”만 보인다(`plan-doc.tsx:46`). 네트워크 오류·5xx에서도 같은 결과다. 실패한 최신 본문을 유지하고, 저장 오류를 화면에 알리며, `flush()`가 저장 성공 또는 명시적인 권한 처리까지 확인하도록 해야 한다. 정상 저장 성공 뒤에만 dirty를 해제해야 한다.

### 2. [P1] 저장·제출 실패도 완료로 처리해 오피스를 닫는다

`apps/web/components/office/candidate-flow.tsx:311`, `apps/web/components/office/candidate-flow.tsx:314`, `apps/web/components/office/candidate-flow.tsx:56` — `flush()` 또는 `submit()`의 모든 예외를 무시하고 `finish()`하며, 아직 진행 중이라 디브리핑이 409를 반환해도 “제출되었습니다”를 보여 준다.

예: 제출 직전 PUT이 네트워크 오류로 실패하면 `submitSession()`은 POST를 호출하지 않지만 화면은 소켓을 닫고 오피스를 제거한다. 이때 서버 세션은 진행 중이고 미저장 원고는 사라진다. 제출 성공 또는 서버 상태로 종료가 확인된 경우에만 이동하고, 그 밖에는 원고를 보존한 채 오류·재시도를 제공해야 한다. `session_ending`·일반 `conflict`도 동일시하지 말고 `/state`로 실제 종료 여부를 확인해야 한다.

### 3. [P1] 재연결 스냅샷이 조회 도중 도착한 WS 증분을 지운다

`apps/web/components/office/candidate-flow.tsx:237`, `apps/web/components/office/candidate-flow.tsx:245`, `apps/web/components/office/reducer.ts:166` — WS 프레임은 즉시 반영하면서 나중에 도착한 `/state` 응답으로 메시지·태스크·진행 상태를 통째로 교체한다.

재현: 기존 snapshot → 새 `message.new` → 기존 snapshot 응답 순으로 reducer를 호출하면 방금 보이던 메시지가 사라진다. 실제 서버도 메시지를 조회한 뒤 문서·태스크 등을 추가 조회하므로 그 사이 도착한 프레임이 응답에 없을 수 있다(`main:services/api/app/routers/candidate.py:220`). 서버는 WS 증분을 다시 보내지 않으므로 다음 복구 전까지 메시지·문서 변경·finished 상태를 놓친다. 상태 조회 동안 프레임을 모아 스냅샷 적용 후 순서대로 재적용하고, 중복 메시지·revision을 고려해야 한다. `/state` 조회 실패를 무시하고 정상 연결처럼 계속 사용하는 경로도 복구 재시도가 필요하다.

### 4. [P2] 새로고침·재입장하면 기존 notice를 어디에서도 볼 수 없다

`apps/web/components/office/reducer.ts:149`, `apps/web/components/office/office-view.tsx:77`, `apps/web/components/office/chat.tsx:74` — 첫 스냅샷의 메시지를 전부 도착 처리에서 제외해 notice ID가 비고, 대화창에는 team·dm만 노출된다.

재현: 책임감 자료 지연 notice를 포함한 snapshot으로 `initialState()`를 만들면 메시지는 저장되지만 `notices=[]`다. 이후 조회에서도 이미 아는 ID라 복원되지 않는다. 책임감 알림 뒤 브라우저를 다시 연 지원자는 지연 사실을 알 수 없어 동일 시나리오 경험과 상태 복원 기준을 충족하지 못한다. 첫 진입의 채널 안 읽음 제외와 notice 복원을 분리해야 한다.

### 5. [P2] 동료 파트 PUT의 실제 403 처리와 mock 계약을 맞춰야 한다

`apps/web/components/office/candidate-flow.tsx:203`, `apps/web/components/office/reducer.ts:154`, `apps/web/mocks/office.ts:319` — 저장 콜백에는 403 처리가 없고 dirty 파트는 상태 갱신에서도 무조건 유지하며, mock 문서 PUT은 동료 담당이어도 성공한다.

분업 확정 전 입력의 디바운스가 남아 있다가 해당 파트가 colleague로 확정되면 실제 API는 403을 반환한다(`main:services/api/app/routers/candidate.py:365`). 읽기 전용 속성만으로 이미 예약된 PUT을 막을 수 없다. 이 경우 담당·서버 본문을 다시 맞추고 “동료 담당이므로 저장되지 않음”을 알려야 하며, 잃어버린 입력을 저장 완료처럼 취급하면 안 된다. mock도 같은 분업 권한에서 403을 반환하도록 맞춰 이 경로를 검증해야 한다. 이는 1번의 일반 저장 실패 처리에 더해 필요한 권한 복구다.

### 6. [P2] 타이머가 명시된 `ends_at`을 쓰지 않는다

`apps/web/components/office/reducer.ts:78` — 종료 시각 대신 응답을 받은 로컬 시각에 `remaining_seconds`를 더하므로, 상태 조회 지연만큼 서버 종료보다 늦게 표시된다.

재현: 같은 snapshot을 서버 계산 시각보다 5초 늦게 적용하면 deadline이 `ends_at + 5초`가 된다. 재연결 때마다 오차가 바뀌며 남은 시간이 있는데 서버가 종료할 수 있다. `docs/frontend/design.md:38`의 `ends_at` 기준으로 계산하고, 필요하다면 서버 시각 보정을 별도 계약으로 정해야 한다. 기존 테스트도 `remaining_seconds` 기반 계산만 확인하고 있다(`apps/web/lib/ws.test.ts:64`).

## 2) 고치면 좋은 것

- **같은 파트의 저장 직렬화:** `apps/web/components/office/part-saver.ts:31` — 앞선 PUT이 Lock 대기로 수 초 걸려도 다음 디바운스가 같은 파트 PUT을 동시에 시작한다. 저장 완료를 역순으로 만드는 재현에서는 `flush()` 뒤 이전 원고가 최종 저장됐다. 실제 API Lock은 서버 도착 순서를 직렬화할 뿐 브라우저 편집 순서를 보장하지 않는다. 파트별로 진행 중 저장 뒤 최신 본문 하나만 이어 보내면 순서·불필요한 요청 문제를 함께 줄인다. 실제 서버에서 역전이 발생하는 통합 재현까지 수행한 것은 아니다.
- **디브리핑 자체의 410 구분:** `apps/web/components/office/candidate-flow.tsx:56` — `/debrief`의 410 `expired`도 “잠시 후 이 링크에서 다시”로 안내한다. `GET /s/{token}` 단계의 만료 처리는 이미 있지만(`flow.ts:43`), 디브리핑 조회에서 기한이 지난 경우에는 영구 만료·담당자 문의 안내로 구분해야 한다. main 계약의 종료 후 7일 규칙을 적용할 것.
- **재입장 연결 실패 안내:** `apps/web/components/office/candidate-flow.tsx:86`, `apps/web/components/office/candidate-flow.tsx:233` — 진행 중 `/resume`·`/state`의 일시 장애도 제출 완료 안내로 이어질 수 있다. `SUBMITTED_NOTICE`를 범용 오류 화면으로 재사용하지 말고 연결 실패·다시 시도 안내를 구분하는 편이 좋다.
- **테스트의 검증 범위:** `apps/web/components/office/flow.test.tsx:150`, `apps/web/lib/ws.test.ts:60` — 제출 테스트의 저장 함수는 즉시 성공하고, 재연결 테스트는 실제 `onOpen` 복구 콜백 대신 reducer를 수동 호출한다. 현재 8개는 완료 기준 7개+기존 health 1개로 **과잉이 아니다**. 개수를 늘리는 데 집중하기보다 기존 제출·재연결 테스트에 지연 PUT의 완료 전 POST 금지, 저장 실패, 조회 중 프레임 보존, 초기 notice·403 계약을 반영하는 것이 필요하다. 라이브러리 추가 없이도 저장기·reducer 경로는 검사할 수 있다.

## 3) 보고서의 “남은 문제”·“변경 요청” 쟁점별 의견

### 남은 문제

| 번호 | 의견과 근거 |
|---|---|
| 1. 정적 렌더·순수 로직 테스트 | 제약 공개는 적절하다. 다만 실제 조립 컴포넌트의 실패 처리까지 검증된 것은 아니다(`candidate-flow.tsx:304`). jsdom 부재가 1~6번 결함을 허용하는 근거는 아니다. |
| 2. 실제 assistant 라우트 없음 | main에도 해당 라우트가 없다. 현 W2는 계약에 맞는 호출·mock·실패 안내를 구현했으므로 이것만으로 이 트랙을 차단하지 않는다(`flow.ts:99`, `candidate-flow.tsx:294`). M2 서버 구현과 M1 이후 연결 검증이 남았다고 인계해야 한다. |
| 3. 파트 제목 하드코딩 | 현재 `parts.ts:3`의 5개 값은 카탈로그와 일치하고 현 State에는 제목이 없으므로 임시 대응은 수용 가능하다. 채용 건 시나리오 고정 원칙상 향후 제목은 최신 카탈로그가 아닌 해당 세션의 scenario에서 받아야 한다. |
| 4. 상단 채용 회사명 | `candidate-flow.tsx:320`은 실제 API의 `company_name` 의미와 일치한다(`main:services/api/app/routers/candidate.py:159`). 현재 명시적 계약 위반으로 보지 않는다. 가상 회사명으로 바꿀지는 오케스트레이터가 제품 의미와 계약을 함께 정할 사안이다. |
| 5. JWT sub로 session_id 읽기 | 서버 토큰의 sub와 일치하며 권한 판단은 서버가 수행하므로 현 구현의 보안 결함은 아니다(`flow.ts:63`). 명시적 응답 필드 추가가 결합도를 줄이지만 현 트랙 필수 선행 조건은 아니다. |
| 6. 실제 스택 미확인 | 단위 mock 중심·통합 스택 단일 실행 규칙에 부합한다. 보고서의 “api-candidate가 main 미병합”은 현재는 지난 상황이며, 이번 리뷰에서는 병합된 main 코드를 대조했다. 실제 연결 테스트 완료로 간주할 수는 없다. |
| 7. 0초에 서버 종료 대기 | 수용 가능하다. 종료·자동 제출의 주체는 API이고 `session.ended`로 전환하는 구현은 맞다(`reducer.ts:241`). 클라이언트 POST 자동 종료를 추가할 필요는 없으나, 타이머 기준 오류와 재연결 복구는 위 지적대로 수정해야 한다. |

### 변경 요청

| 번호 | 의견과 근거 |
|---|---|
| 1. State에 파트 제목 | 찬성하되 후속 계약 개선이다. 세션 scenario의 part_no·title을 함께 주면 `parts.ts:3`의 중복을 제거할 수 있다. 트랙이 공용 계약을 직접 고치지 않은 것은 적절하다. |
| 2. virtual_company | 오케스트레이터 결정 대상으로 유지한다. `Entry`에는 지금 그 필드가 없고(`types.ts:8`), 임의로 `entry_notice` 문장을 파싱해 이름을 추출해서는 안 된다. |
| 3. session_id 추가 | 찬성하는 선택적 개선이다. consent·resume과 종료 재입장 응답까지 일관되게 주면 `sessionIdFromToken()` 의존을 없앨 수 있다(`flow.ts:64`). |
| 4. API 보충 계약 반영 | **main에서는 이미 반영됨.** `docs/common/contracts.md`의 “지원자 경로 보충” 및 “연결 거절과 오류 프레임”에 404, 실패 디브리핑, 4401·4403·4000, error 봉투가 명시돼 있다. 재요청보다 main 기준 갱신·재검증이 필요하다. `lib/ws.ts:80`의 4000·4403 정지와 `lib/ws.ts:85`의 4401 재발급 방향은 맞다. |
| 5. jsdom·testing-library 추가 | 선택 사항이다. foundation 소유 의존성을 임의 수정하지 않은 것은 적절하다. 클릭·effect 조립 검증에 도움이 되지만 순수 로직으로 확인 가능한 병합 차단 수정까지 의존성 추가를 기다릴 필요는 없다(`flow.test.tsx:150`). |

공통 확인: 변경 파일은 지원자 화면·office·WS 및 관련 테스트·office mock 범위이며, 금지된 `components/ui/`, `lib/api.ts`, `mocks/index.ts`, `package.json` 수정은 없다. 오피스 4탭·동료 파트 readOnly·카드 권한 UI·인용 문서명은 구현돼 있다(`office-view.tsx:118`, `plan-doc.tsx:34`, `task-board.tsx:38`, `assistant-panel.tsx:48`). 오피스에 점수·합격·순위·연출 상황을 표시하는 문구는 발견하지 못했다. 동의 화면의 관찰·점수 처리 안내와 종료 화면의 평가 언급은 PRD가 요구한 범위다. `failed_stage=session`이면 연출·페르소나를 렌더하지 않는 처리도 서버 계약과 맞는다(`debrief-screen.tsx:7`). MVP 제외 기능을 추가한 정황은 없다.

## 4) 다른 트랙 주의사항

- **api-candidate:** 문서 저장은 세션 Lock 대기와 403을 포함한다(`main:services/api/app/routers/candidate.py:354`). 프론트가 이를 복구하고 저장 완료 뒤 제출하도록 1·2·5번을 먼저 수정해야 한다. WS 4401 재발급·4000/4403 정지, `{type,payload}`, 동일 client_msg_id 멱등은 현재 main과 맞는다. 프론트 `/state`와 WS 사이의 경합은 서버의 멱등만으로 해결되지 않는다.
- **agent-assistant / API 담당:** `flow.ts:99`의 POST 본문은 `{prompt}`, 응답은 `{call_id,message_id,content,cited_docs}`, 429 코드는 `assistant_limit`이다. 구현 후 공개 문서명 매핑과 actor=assistant 진행 표시를 연결 검증할 것. 요청 중 재연결은 프론트가 임시 `local-*` call_id를 사용하므로 서버 call_id와의 중복·완료 상태도 대조할 것(`candidate-flow.tsx:283`, `reducer.ts:157`).
- **foundation:** 병합 차단 수정 때문에 공용 UI props·API 래퍼·패키지를 바꿀 필요는 없다. 의존성 추가 요청은 별도 결정하며 테스트 8개를 과잉으로 줄일 이유도 없다. `lib/ws.test.ts`는 WS 구현에 대응하는 테스트로 소유권 위반으로 판단하지 않았다.
- **web-polish:** 좁은 화면 대응과 메시지 도착 시 스크롤 처리는 후속 점검 대상이다(`office-view.tsx:110`, `chat.tsx:91`). 문구를 다듬을 때도 오피스에 관찰·점수·연출을 노출하지 말 것. 동의·실패 중단·디브리핑 문구는 각각의 PRD 맥락을 유지할 것.
- **e2e-runner:** mock 경로 표는 계약의 REST 경로와 맞지만 문서 403·저장 지연을 현재 mock이 재현하지 못한다(`mocks/office.ts:315`). 실제 API에서 “미저장 입력→Lock 대기→제출”, “분업 변경 중 PUT 403”, “조회 중 WS 메시지”, “책임감 알림 뒤 새로고침”, “디브리핑 7일 만료”를 계약상 필요한 실패·복구 경로로 확인할 것. 정상 플로우 외 입력 조합 전수 테스트는 필요 없다.
