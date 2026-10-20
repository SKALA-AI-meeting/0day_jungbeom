# api-candidate W1 리뷰

판정: **수정 후 재리뷰 필요.** 아래 병합 차단 7건을 먼저 처리한다. 소스 수정·git 변경·gh·외부 게시는 하지 않았다.

대상은 `track/api-candidate`의 `911aaa3`이다. 요청된 `git diff main..HEAD`를 확인했으며, 리뷰 당시 main(`42fc6f3`)에만 있는 business-mcp·handoff 변경의 역방향 차이는 이 트랙의 삭제로 판정하지 않았다. 공통 조상 `c9fa550`부터 실제 트랙 변경은 8파일이고, `context.py` 변경은 허용된 reuse 훅 연결뿐이다. 소유권 위반은 없다.

검증: `services/api`에서 `UV_CACHE_DIR=/private/tmp/codex-api-candidate-uv uv run --offline pytest -q`를 실행했다. **3 passed, 10 errors**이며 10건 모두 PostgreSQL 접속 준비 단계의 `PermissionError: Operation not permitted`다. 이 환경에서는 DB 기반 통과를 재확인할 수 없으며 코드 실패로 단정하지 않는다. ruff 재실행은 실행 파일 부재로 불가했다. 별도 DB 없는 mock 실행으로 아래 1·3·4·6의 동작을 확인했다. 개발자의 `13 passed`·`make test/lint`·6분 실시간 결과는 보고된 증거로 구분한다.

## 1) 반드시 고칠 것 — 병합 차단

### 1. [P1] 재시작 시 이전 fired 카드보다 새 pending 카드가 먼저 실행된다

- 위치: `services/api/app/scheduler.py:99`, `services/api/app/scheduler.py:137`, `services/api/app/scheduler.py:163`.
- 근거: tick이 `_events`를 `_retry`보다 먼저 spawn하고 pending 조회에도 시간순 정렬이 없어, 상태를 가진 그래프가 카드 순서를 뒤집어 처리할 수 있다.

예를 들어 kickoff가 fired인 채 중단되고 division까지 due가 된 뒤 재시작하면 division run이 kickoff 복구 run보다 먼저 Lock에 진입할 수 있다. 오래된 fired가 아직 60초 조건을 충족하지 않았다면 새 카드만 실행된다. mock으로 디스패치 순서가 `new pending event → old fired event`임을 확인했다. 세션별 미완료 카드와 새 카드를 `due_at` 순으로 처리하고, 이전 run의 복구·재시도가 끝나기 전 후속 run이 앞서지 않도록 해야 한다. `_retry` 호출 순서만 바꾸면 60초 미만의 fired와 여러 pending 묶음 문제는 남는다. 기존 재시작 완료 기준 테스트에 후속 카드가 함께 due인 경우를 반영한다.

### 2. [P1] 지원자 문서 PUT이 동료 단독 파트도 수정한다

- 위치: `services/api/app/routers/candidate.py:341`, `services/api/app/routers/candidate.py:360`.
- 근거: 문서 존재와 세션 상태만 검사하고 분업 담당을 검사하지 않아, UI의 동료 파트 읽기 전용 규칙을 API로 우회할 수 있다.

같은 세션의 정상 JWT로 동료 담당 4번 파트에 PUT하면 지원자 revision으로 덮어쓴다. 동료의 정책 위반을 지원자가 직접 지울 수도 있어 관찰 전제가 깨진다. `docs/frontend/design.md:32`의 읽기 전용 규칙과 `docs/common/contracts.md`의 “권한·담당자는 api가 최종 판단” 원칙대로, 분업 확정 뒤 `colleague` 단독 파트는 403으로 막고 candidate·both만 허용해야 한다. 분업 전 편집 정책도 기존 화면 동작과 맞춰 명시한다. 기존 엔드포인트 테스트에 권한 실패를 포함하면 된다.

### 3. [P1] 문서 PUT과 submit이 겹치면 종료 후에도 문서가 커밋된다

- 위치: `services/api/app/routers/candidate.py:338`, `services/api/app/routers/candidate.py:346`, `services/api/app/routers/candidate.py:376`.
- 근거: `_ensure_writable`은 파트 행 잠금 대기 전에 한 번만 실행되며 complete와 공유하는 직렬화가 없어, 종료·reuse 계산·리포트 발행 뒤 쓰기가 성공할 수 있다.

PUT이 진행 중 상태를 읽고 파트 잠금에서 기다리는 동안 submit이 완료되어도 PUT은 revision을 올리고 커밋한다. mock으로 상태를 completed로 바꾼 뒤 대기를 풀었을 때 `saved_content=after, revision=2, commits=1`을 확인했다. 지원자 PUT은 동일한 세션 Lock 안에서 최신 상태를 확인하고 저장하거나, complete와 공통으로 쓰는 DB 동시성 규칙으로 직렬화해야 한다. 잠금 없는 재조회만 추가하면 재조회와 커밋 사이 경쟁은 남는다. 내부 API까지 무조건 같은 asyncio.Lock을 잡게 하면 runner의 내부 HTTP 호출과 교착되므로 지원자 진입점과 내부 도구 경로를 구분해야 한다.

### 4. [P2] 종료 후 7일이 지나도 링크로 디브리핑 권한을 계속 재발급한다

- 위치: `services/api/app/routers/candidate.py:159`, `services/api/app/routers/candidate.py:446`; 연관 기반 코드 `services/api/app/auth.py:72`.
- 근거: 종료 시각을 검사하지 않고 GET마다 “현재부터 7일” JWT를 발급하므로 PRD 7.4의 종료 후 7일 제한이 무기한 연장된다.

8일 전에 종료된 세션을 mock으로 조회해 유효한 새 debrief JWT가 발급됨을 확인했다. 종료 기준 시각으로 고정된 만료를 발급하고 debrief 조회에서도 같은 기한을 적용해야 한다. failed 세션까지 포함한 종료 시각 저장 방법은 foundation과 맞춘다. JWT TTL이 7일인 것만으로는 종료 후 7일 제한을 충족하지 않는다.

### 5. [P2] Idempotency-Key 계약을 본문 비교로 대체할 수 없다

- 위치: `services/api/app/routers/candidate.py:334`, `services/api/app/routers/candidate.py:351`; 기준 `docs/common/contracts.md:12`.
- 근거: 헤더를 읽거나 결과를 보관하지 않아 같은 키 재요청이 원래 결과를 반환한다는 계약을 충족하지 않는다.

키 K로 A 저장(revision 1) → 다른 요청으로 B 저장(revision 2) → K의 A 재전송 시 현재 코드는 revision 3으로 B를 덮어쓴다. 같은 본문을 연속 요청하는 테스트는 이 경우를 검증하지 못한다. api-admin과 공통 요청 키·결과 저장 방식을 foundation에 요청하거나, 오케스트레이터가 MVP 계약을 명시적으로 변경해야 한다. 저장 테이블이 없다는 이유로 현재 계약을 충족했다고 처리하는 데 반대한다. 변경 승인이 없으면 구현이 필요하다.

### 6. [P2] submit 완료 후 message.send의 오류 코드가 session_ending이 아니다

- 위치: `services/api/app/routers/ws.py:84`, `services/api/app/routers/ws.py:88`; 원인 `services/api/app/services/messages.py:63`.
- 근거: 공용 접수 함수가 status를 submitted_at보다 먼저 검사해 completed 세션에 `conflict`를 던지고 WS가 그대로 전달한다.

제출된 completed 세션에 실제 접수 함수를 mock DB로 호출해 `conflict`를 확인했다. 계약은 submitted_at 이후 message.send에 `error{code: session_ending}`을 요구한다. foundation에 검사 우선순위 변경을 요청하고 기존 WS 완료 기준에서 제출 후 오류 프레임을 확인한다. 기반 코드에서 비롯된 접점 결함이며 이 트랙이 소유권 밖 파일을 직접 고치라는 뜻은 아니다.

### 7. [P2] 필수 카드 failed 저장과 세션 fail 사이의 중단을 복구하지 못한다

- 위치: `services/api/app/scheduler.py:304`, `services/api/app/scheduler.py:307`, `services/api/app/scheduler.py:310`.
- 근거: 카드 failed를 먼저 커밋한 뒤 별도 트랜잭션으로 세션을 fail하므로, 두 단계 사이에 죽으면 재시작 스케줄러가 해당 카드를 다시 찾지 못한다.

3회 실패 직후 307행 커밋이 끝나고 fail 호출 전에 프로세스가 중단되면 세션은 in_progress이고 카드는 failed다. `_retry`는 fired만 읽으므로 필수 카드 실패가 방치되고, 만료 시 completed와 리포트 발행으로 진행할 수 있다. 카드 최종 실패와 SessionService.fail을 같은 트랜잭션에서 커밋하거나, 재시작 시 failed 필수 카드가 있는 in_progress 세션을 먼저 fail로 수렴시켜야 한다. 정상적인 3회 실패의 Lock 재진입 문제는 없지만 이 영속화 공백은 남는다.

## 2) 고치면 좋은 것

- **실시간 확인 스크립트의 성공 판정을 자동화한다.** `services/api/tests/test_scheduler.py:62`는 주입한 시각의 fired 오차만 검증한다. 보고서가 가리킨 `realtime_six_minutes.py:128` 부근의 출력 루프는 카드 9건·전부 done·오차 제한·completed·발행 횟수를 assert하지 않아 미완료여도 exit 0이 가능하다. 이번 표의 9건 done과 최대 1초는 정상 Fake 경로의 수동 확인 근거로 인정하되, 다음 실행부터 같은 완료 기준을 스크립트의 실패 코드로 보장하는 것을 권고한다. 실 LLM·MCP 지연이나 120분 세션 성능을 입증한 것으로 확대하지 않는다.
- **중복된 tasks 생성 소유를 정리한다.** `services/api/app/routers/candidate.py:399`의 `sync_tasks`는 api-admin의 `internal.py:258`과 같은 역할이다. api-admin에 candidate 라우터 import를 추가할 필요가 없다. 실제 저장 책임을 내부 division 라우터 한 곳으로 정하고 후보 helper를 제거하거나 테스트 준비 코드로 옮기면 유지보수 혼선을 줄일 수 있다.
- **시작 시 공개 문서를 즉시 열도록 foundation에 요청한다.** `services/api/app/routers/candidate.py:322`, `services/api/app/services/session.py:162`, `services/api/app/scheduler.py:115` 기준으로 양쪽 API가 같은 released_at을 보는 것은 맞지만 첫 tick까지 423이 되는 UX 공백은 실제다. 시작 트랜잭션에서 시작 공개 문서의 released_at을 채우는 편이 작고 일관된 개선이다.

## 3) 보고서의 남은 문제·변경 요청에 대한 의견

### 남은 문제

| 쟁점 | 의견·권장 처리 | 위치·한 줄 근거 |
|---|---|---|
| 1. POST assistant 미구현 | **M2 이관에 동의.** W1 병합 자체의 차단 사유로 추가하지 않는다. 다만 api-candidate가 REST 저장·한도·인증을, agent-assistant가 그래프를 맡도록 후속 작업을 명시한다. | `docs/plan.md:21`, `docs/agent/design.md`의 어시스턴트 그래프 절: M2 의존 기능이며 API 기록 책임은 별도로 필요하다. |
| 2. Idempotency-Key 미구현 | **대체 충족 주장에 반대.** 공용 구현 또는 공식 계약 변경이 필요하다. | `services/api/app/routers/candidate.py:351`: 현재 본문 비교는 과거 요청 키의 결과를 복원하지 못한다. 차단 5 참조. |
| 3. 시작 문서 최대 5초 공백 | **현상에 동의, 즉시 공개 개선 권장.** 프론트 대기로 영구 해결하지 않는다. | `services/api/app/scheduler.py:87`, `services/api/app/routers/candidate.py:429`: 첫 tick 전에는 released_at이 없어 423이다. |
| 4. active_runs actor·node 추정 | **W1 임시 구현에 동의.** 정확한 그래프 현재 노드로 설명하면 안 된다. M2에서 progress 상태 보관 방식과 맞춘다. | `services/api/app/routers/candidate.py:302`: DB에 현재 actor·node가 없고 message를 일괄 colleague/respond로 표시한다. |
| 5. assistant_reuse revision 없음 | **문서·스키마 불일치 지적에 동의.** 이번 트랙의 임의 스키마 변경은 피하고 오케스트레이터가 결정한다. | `services/api/app/services/reuse.py:95`, `docs/api/design.md:53`, `docs/common/data-model.md:22`: 함수는 revision을 계산하지만 저장 계약은 호출×파트별 최대값만 정의한다. |
| 6. 단위 테스트와 실시간 오차 구분 | **동의.** fired ±10초의 결정적 검증과 Fake 실시간 done 측정을 구분해 보고한 점은 적절하다. | `services/api/tests/test_scheduler.py:54`, `services/api/tests/test_scheduler.py:62`: 가상 tick 시각과 실제 done 시각은 같은 시계가 아니다. |
| 7. 2초 간격 총 3회 재시도 | **동의.** 간격은 미정이므로 2초는 작은 구현 선택이다. 순서·최종 실패 복구는 보완한다. | `services/api/app/scheduler.py:225`, `services/api/app/scheduler.py:268`: 같은 run_id와 저장된 attempts로 재시도하며 차단 1·7의 복구 결함이 있다. |
| 8. JWT 키 길이 경고 | **설정 개선에 동의.** foundation/운영 설정에서 충분한 길이의 비밀값을 넣고 예시와 맞춘다. | `services/api/app/auth.py:58`: 환경의 키로 서명하며 이번 확인에서도 길이 경고가 발생했다. 키 값은 확인·출력하지 않았다. |

revision 쟁점은 현재 내부 REST와 데이터 모델이 revision 없는 형식에 일치하므로, MVP에서는 `docs/api/design.md:53`을 “순수 함수는 최적 revision을 반환, 저장은 호출×파트별 최대값”으로 명확히 하는 방안을 우선 권고한다. 특정 반영 revision을 리포트 근거로 직접 참조해야 한다면 컬럼·내부 계약·워커 소비를 함께 확장해야 한다.

### 변경 요청

| 요청 | 의견·권장 처리 | 위치·한 줄 근거 |
|---|---|---|
| 1. WS close code·error 봉투 명시 | **동의.** 4401·4403과 error payload를 공용 계약에 반영하고 웹 복구 동작도 맞춘다. | `services/api/app/routers/ws.py:28`, `services/api/app/routers/ws.py:64`: 구현된 외부 동작을 프론트가 알아야 한다. 차단 6의 코드 불일치는 별도 수정한다. |
| 2. 세션 실패 debrief 형태 | **현 구현에 동의.** events=[]·persona_note=null·중단 안내·failed_stage로 충분하며 notice 필드 추가는 필수가 아니다. | `services/api/app/routers/candidate.py:449`: 연출을 숨기는 기존 계약을 지키고, 안내 문구를 읽는 웹 타입의 null 허용만 합의하면 된다. |
| 3. 알 수 없는 초대 토큰 404 | **동의.** 오류 표에 not_found를 명시한다. | `services/api/app/routers/candidate.py:98`: 존재하지 않는 초대와 만료·취소를 구분하는 자연스러운 응답이다. |
| 4. 시작 문서 released_at 즉시 기록 | **동의·권장.** foundation에서 시작 트랜잭션에 반영한다. | `services/api/app/services/session.py:162`: 시작 공개 예약 생성과 함께 기록하면 지원자·내부·rag가 동시에 같은 상태를 본다. |
| 5. assistant_reuse revision 컬럼 | **현재로서는 보류.** 위 남은 문제 5의 정합성 결정부터 한다. | `services/api/app/services/reuse.py:97`, `docs/common/data-model.md:22`: 현재 소비 계약에는 revision이 없어 단독 컬럼 추가의 효과가 없다. |

## 4) 다른 트랙 주의사항·완료 기준 점검

- **api-admin — division→tasks는 이미 구현되어 있다.** `track/api-admin:services/api/app/routers/internal.py:258`은 division과 같은 트랜잭션에서 tasks를 upsert하고 상태를 유지하며, 279행에서 task.updated도 보낸다. 이 구현을 유지하고 `sync_tasks` import 요청은 철회한다. 결과적으로 첫 분업·재분업 모두 지원자 라우터가 기대하는 행을 제공한다.
- **api-admin·rag-mcp — 공개 기준은 released_at으로 통일한다.** candidate의 `services/api/app/routers/candidate.py:322`와 admin 브랜치 `internal.py:414`가 일치한다. 시각이 지났다는 이유만으로 release_at을 보고 true로 만드는 별도 규칙은 넣지 않는다. 내부 수동 공개는 `track/api-admin:services/api/app/routers/internal.py:446`에서 이미 document.released를 보내므로 candidate 보고서의 브로드캐스트 누락 우려는 현재 admin 구현에서는 해소되어 있다.
- **foundation — 공용 변경을 맡는다.** `services/api/app/services/session.py:162`의 시작 문서 공개, `services/api/app/auth.py:72`의 종료 기준 토큰 기한, `services/api/app/services/messages.py:63`의 submitted_at 우선 검사, 요청 키 저장 정책은 소유권 승인 아래 조정한다. 후보 트랙의 무단 기반 수정은 요구하지 않는다.
- **agent-session — Lock 호출 방식은 현재 맞다.** `services/api/app/scheduler.py:230`에서 Lock을 잡은 카드 실행은 277행에서 lock_held=True를 쓰고, `services/api/app/routers/candidate.py:439`의 submit과 `scheduler.py:212`의 메시지 실행은 Lock 밖에서 공용 래퍼를 부른다. `SessionService.complete`도 `services/api/app/services/session.py:211`에서 lock_held=True를 쓰므로 확인한 경로에 직접적인 재진입 교착은 없다. 내부 MCP HTTP 라우터에 같은 세션 Lock을 추가하면 실행 중인 runner가 자기 Lock을 기다릴 수 있으니 주의한다.
- **agent-session — 같은 run_id와 전체 event_ids 순서를 보존한다.** `services/api/app/scheduler.py:270`은 재시도 시 묶음 전체를 넘기고 300행에서 ok와 event_id별 메시지를 확인한다. 실제 그래프도 고정 seq 슬롯·기존 결과 재사용을 지켜야 한다. 정상 3회 실패·texture skipped 처리는 구현되어 있지만 차단 1·7을 반영한 복구 확인이 필요하다.
- **web-office — 인증·복구 규약을 반영한다.** `services/api/app/routers/ws.py:39`는 accept 후 JWT를 검증하고 세션 소유가 다르면 4403, 토큰 오류는 4401이다. `services/api/app/hub.py:44`의 교체 연결은 session.replaced와 4000을 사용한다. JWT 소유 확인은 REST start와 세션 경로에도 적용되어 있다. 오류 봉투와 failed debrief의 null 필드, assistant 별도 배열을 목 타입과 맞춘다.
- **agent-assistant·worker — reuse는 반영 추정이다.** `services/api/app/services/reuse.py:90`은 호출 이후 지원자 revision만 비교하고 호출×파트별 최대값을 저장한다. 정규화·20자 블록 합·0.8/0.3 임계값과 120자 예시는 설계와 맞으며 `autojunk=False`도 합리적이다. `response_message_id`가 저장된 호출만 집계되므로 응답 메시지와 연결을 먼저 저장해야 한다. 최종 문서에 남아 있는 비율이나 검증 행동 점수로 해석하지 않는다.
- **오케스트레이터 — 7종 스케줄러 책임은 모두 존재한다.** `services/api/app/scheduler.py:95`의 releases·events·retry·stale runs·endings와 outbox가 표의 7종을 담당한다. timeouts와 ending을 `_endings` 하나로 합친 것은 문제없다. outbox는 generate와 approve 모두 공용 재발행 함수를 쓴다. 존재 여부는 충족하지만 카드 순서와 실패 전이 내구성은 차단 항목대로 보완한다.
- **오케스트레이터 — 신규 테스트 8개는 과잉이 아니다.** `services/api/tests/test_candidate.py:92`, `services/api/tests/test_scheduler.py:49`, `services/api/tests/test_reuse.py:17`은 엔드포인트·WS·제출 후 차단·시계·만료·재시작·미발행·reuse 예시에 대응하며 입력 조합 전수 테스트가 없다. 결함 검증은 해당 완료 기준 테스트에 포함하고 별도 경계값 묶음을 늘리지 않는다. 실시간 스크립트는 단일 Fake 세션의 보조 근거이며 M1 끝 실제 연결 검증과 M2 그래프 검증은 여전히 남는다.
