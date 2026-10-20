# api-admin W1 리뷰

판정: **수정 후 재리뷰 필요**. 아래 병합 차단 항목을 해결하고 공용 파일 변경은 오케스트레이터가 해당 소유자에게 배정해야 한다.

대상은 `track/api-admin`의 `e3c201c`, 요청한 `git diff main..HEAD`다. 현재 main에는 이 브랜치 분기 뒤 `99f2fff`, `502b88b`, `7b04ef8`이 추가되어 있다. 따라서 두 점 diff에 보이는 `docs/handoff.md` 되돌림과 business-mcp 파일 삭제는 이 트랙이 수정한 내용이 아니다. `git log --left-right main...HEAD`와 `git diff main...HEAD --name-status`로 확인한 실제 트랙 변경은 라우터 2개와 해당 테스트 5개뿐이다. 소유권 위반은 발견하지 않았다. 병합 전 main 위 rebase와 재검증은 필요하다(`docs/plan.md:43`, `docs/plan.md:51`).

## 1. 반드시 고칠 것 — 병합 차단

### B1. [P1] `since_t_min`을 지정한 메시지 조회 SQL이 PostgreSQL 함수 인자와 맞지 않음

- 위치: `services/api/app/routers/internal.py:138`.
- 근거: `since_t_min`은 float인데 `make_interval`의 여섯 번째 인자(mins)는 integer다. SQLAlchemy asyncpg dialect로 실제 생성한 SQL도 `make_interval($1::INTEGER, ..., $6::FLOAT)`였다. 시작한 세션에 `GET /internal/sessions/{id}/messages?since_t_min=1.5`를 보내면 함수 해석 오류로 500이 발생할 경로다. 기존 테스트는 channel·limit만 확인하고 이 필터를 호출하지 않는다(`services/api/tests/routers/test_internal.py:71`). DB에서의 실행 재현은 아래 환경 제한으로 못 했다.
- 권장 처리: Python에서 `session.started_at + timedelta(minutes=since_t_min)`을 계산해 timestamp로 비교한다. 소수 분 필터 정상 경로 한 개를 기존 메시지 테스트에 추가한다. 정수 변환으로 소수 분을 버리면 계약 위반이다(`docs/common/contracts.md:11`).

### B2. [P1] 흐름 카드가 마지막 관찰 요소를 지움

- 위치: `services/api/app/routers/internal.py:88`–`93`.
- 근거: respect가 done인 뒤 더 늦은 report_request가 done이면 `current_element()`는 null이다(함수 직접 호출로 확인). 확정 결정은 “다음 요소 카드까지, 흐름 카드·texture는 닫지 않음”이므로 보고 단계에서도 respect 창이 열려 있어야 한다(`docs/decisions.md:45`, `docs/agent/design.md:131`). 현재 구현을 사용하는 그래프·가드가 보고 중 지적을 창 밖으로 처리할 수 있다.
- 권장 처리: 최신 실행 요소 카드를 기준으로 계산하고 세션 종료 후 표현도 명시한다. respect → report_request → 지원자 지적의 정상 흐름 한 개로 검증한다. `docs/common/scenario-model.md:62`와 `docs/agent/design.md:70`에는 예전 “흐름 카드도 닫음” 문구가 남아 있으므로 오케스트레이터가 결정 기록과 함께 정합화해야 한다. 문서 충돌을 구현자가 임의로 선택한 상태로 병합하면 안 된다.

### B3. [P2] 선택 헤더 `Idempotency-Key`의 약속이 생성 API에서 전혀 지켜지지 않음

- 위치: `services/api/app/routers/admin.py:186`, `services/api/app/routers/admin.py:391`; 기준 `docs/common/contracts.md:12`.
- 근거: 같은 키·같은 본문으로 채용 건 또는 초대 생성 요청을 재전송해도 매번 새 UUID·초대 링크가 만들어진다. 세션 전이 및 내부 저장의 도메인 멱등은 이 두 생성 작업을 보호하지 못한다. 보고서가 인정한 누락이며 “테이블이 없다”는 계약 면제 근거가 아니다.
- 권장 처리: foundation과 최소 공용 멱등 저장·재응답 방식을 정해 연결한다. 초대는 토큰 원문이 DB에 없으므로 기존 초대 행 조회만으로 같은 응답을 복원할 수 없다는 점도 해결해야 한다. 또는 오케스트레이터가 계약 변경을 명시적으로 결정해야 한다. 둘 중 하나 없이 계약 준수 완료로 판단할 수 없다.

### B4. [P2] 동일 분업 재요청이 결정 시각과 응답을 바꿈

- 위치: `services/api/app/routers/internal.py:253`–`279`.
- 근거: 같은 parts·decided_by를 재전송해도 `decided_at=datetime.now()`를 다시 저장하고 보드 이벤트 전부를 다시 보낸다. 응답의 division이 달라져 보고서의 “같은 요청 재호출은 멱등” 및 그래프 재실행 규칙과 어긋난다(`docs/agent/design.md:21`).
- 권장 처리: 현재 parts·decided_by와 같으면 저장된 division을 그대로 반환하고 변경 브로드캐스트를 생략한다. 실제 재분업에만 새 결정 시각을 기록한다. 기존 분업 테스트에 동일 요청의 응답·시각 불변 검증 한 개를 합친다.

### B5. [P2, foundation 연계] 기본 422 응답이 공통 오류 계약을 위반함

- 위치: `services/api/app/routers/admin.py:84`, `services/api/app/routers/internal.py:230`; 공용 원인 `services/api/app/main.py:54`–`55`.
- 근거: ASGI로 `/admin/auth/login`에 필수 password가 없는 본문을 보냈을 때 422 `{"detail":[...]}`가 반환되는 것을 확인했다. 정상화된 `error.code`를 전제하는 화면·MCP가 일관되게 처리할 수 없다(`docs/common/contracts.md:8`).
- 권장 처리: 보고서 변경 요청 1에 동의한다. foundation이 두 앱 공통 `_base`에 RequestValidationError 핸들러를 추가해 `error.code=invalid_input` 형식으로 통일한 뒤 연결 검증한다. 라우터마다 중복 핸들러를 넣지 않는다. 기존 foundation 문제이지만 이 트랙의 계약 완료 판정 전에 해결할 의존 사항이다.

### B6. [P2] 종료된 세션에도 새 동료 문서·보드 변경을 허용함

- 위치: `services/api/app/routers/internal.py:218`, `services/api/app/routers/internal.py:314`.
- 근거: 두 함수 모두 `load_session()` 결과의 상태를 검사하지 않는다. 분업된 세션을 completed 또는 reviewed로 만든 뒤 새 run_id로 동료 파트 PUT을 호출해도 revision과 본문을 바꿀 수 있다. 관리자 리포트는 현재 DocumentState를 매번 합성하므로 확정 리포트의 산출물까지 바뀐다(`services/api/app/routers/admin.py:514`). 권한·상태 최종 검증은 API 책임이다(`docs/common/contracts.md:153`).
- 권장 처리: 새 업무 변경은 in_progress에서만 허용한다. 종료 그래프는 submitted_at이 기록된 in_progress 동안 내부 저장을 하므로 지원자용 submitted_at 차단 규칙을 그대로 복사하면 안 된다. 이미 저장된 문서 run_id의 재전달은 기존 결과로 처리하여 재전달 멱등을 보존한다. 종료 뒤 새 쓰기 거부 경로를 기존 권한 테스트에 합친다.

## 2. 고치면 좋은 것

- **[P2] 분류 결과의 읽기 경로를 명확히 하기** — `services/api/app/routers/internal.py:141`, `services/api/app/routers/internal.py:193`: classification은 meta에 저장하지만 내부 메시지 GET과 PUT 응답의 `serialize()`는 meta를 제거한다(`services/api/app/services/messages.py:34`). observe가 DB를 직접 읽을지, 내부 GET에 classification을 추가할지 agent-session과 정하고 계약에 기록해야 한다. 현재 Message 계약에는 meta가 없어 라우터만의 명백한 계약 위반으로 보지는 않는다.
- **[P2] final 동시 재전달의 reviewed_at 안정성** — `services/api/app/routers/internal.py:634`–`644`: 순차 재전달은 올바르지만 두 요청이 모두 approving을 읽으면 각각 현재 시각을 만든다. reviewed_at까지 동일해야 하는 재전달 계약을 보장하려면 같은 세션 또는 리포트 행 잠금 안에서 상태를 재조회하는 편이 일관된다. 문서 revision 직렬화와 같은 작은 범위로 처리하면 된다.
- **[P3] 재리뷰 오류의 우선순위 통일** — `services/api/app/routers/admin.py:601`: 이미 승인한 세션에 메모 없는 새 변경을 보내면 `already_reviewed`가 아니라 먼저 `memo_required`가 난다. 계약의 “다른 본문은 409”와 오류 우선순위를 맞추거나 명시하면 화면 처리가 단순해진다(`docs/common/contracts.md:40`). 최초 제출의 validation 자체는 적절하다.
- **테스트 18개는 과잉 아님** — `services/api/tests/routers/test_admin.py:13`, `services/api/tests/routers/test_internal.py:35`, `docs/dev-process.md:34`: 관리자 8개·내부 10개는 응답, 격리, 권한, 멱등, 승인 규칙 등 완료 기준에 대응한다. elements 4개 사례도 문서가 명시한 네 검증 조건이다. 개수를 줄이기보다 B1·B2·B4·B6을 기존 기능 테스트에 필요한 만큼 합치는 것이 맞다.
- **보드 doing 책임을 문서로 고정하기** — `services/api/tests/routers/test_internal.py:117`, `docs/agent/design.md:84`: 현재 분업 직후는 전부 todo이고 그래프가 별도 update_task(doing)를 호출하는 설계다. 따라서 라우터의 todo만으로 오류라고 단정하지 않는다. 그래프가 동료 카드 전부를 doing으로 바꾸는 책임과 재분업 때 기존 본문·revision을 보존하는 규칙을 전달해야 한다.

## 3. 개발자 보고서 쟁점별 의견

번호는 보고서의 각 절 번호와 대응한다. 아래 위치는 판단 근거가 되는 구현·계약이다.

### “계약에 없어 내가 정한 것”

| 쟁점 | 의견·권장 처리 | 위치·한 줄 근거 |
|---|---|---|
| 1. catalog 필드 출처·템플릿 | 동의. 현재 카탈로그에서 변환하고 안내 문구를 상수로 두는 정도는 MVP에 적절. 출처와 문자열 타입을 계약에 명시 | `services/api/app/routers/admin.py:125` — 요구된 응답 필드를 기존 데이터로 구성하며 새 저장소를 만들지 않음 |
| 2. adjusted·review·history | 동의. adjusted는 reviewer=null인 실제 조정과 무조정을 구분하므로 필요. review·history 필드 자체는 이미 계약 예시에 있고 내부 구조만 보강하면 됨 | `services/api/app/routers/admin.py:281`, `docs/common/contracts.md:54` — null 조정은 행 존재 여부로 최종값을 선택해야 함 |
| 3. approving 시 합계·메모 저장 | 동의. API 리뷰 제출이 담당자의 검토 완료이고 워커 final은 확정 처리. “검토 완료 시”를 이 시점으로 문서화 | `services/api/app/routers/admin.py:623`, `docs/common/rubric.md:20` — 조정 저장·합계·approving은 한 트랜잭션이어야 함 |
| 4. 동일 자동값 생략·리뷰 잠금 | 동의. 변경만 저장하고 메모를 요구하는 규칙에 맞으며, 같은 세션의 두 리뷰가 unique 제약 오류로 끝나는 것을 막음 | `services/api/app/routers/admin.py:573`, `services/api/app/routers/admin.py:591`, `infra/db/schema.sql:212` — 세션 행 잠금 뒤 최신 상태를 읽고 조정·합계·전이를 커밋함 |
| 5. display_status 코드값 | 동의. API는 상태 코드를 주고 화면이 한글 라벨로 표시 | `services/api/app/routers/admin.py:314`, `docs/common/contracts.md:36` — expired가 저장 상태와 별도인 표시값이라는 계약과 일치 |
| 6. 첫 draft 유지 | 동의. 기존 content와 hash를 유지해야 승인 대상이 바뀌지 않음 | `services/api/app/routers/internal.py:610` — report_ready 이후 재전달이 저장 본문을 덮어쓰지 않음 |
| 7. final 본문 불변·오류 순서 | 동의. 해시는 합성 GET 응답이 아니라 저장된 content에 적용. 동시 final 시각 문제는 2절 참고 | `services/api/app/routers/internal.py:638`, `docs/common/contracts.md:67` — GET의 stage·조정·산출물은 해시 대상과 분리되어 있음 |
| 8. 분업 전체 지정·tasks 생성·재분업 | 조건부 동의. 최소 조건과 재분업 지원은 맞지만 B4를 수정해야 함. tasks 생성 담당은 오케스트레이터 결정 필요. **권장은 api-admin의 내부 division에 유지**하고 foundation 기록을 정정하는 것 | `services/api/app/routers/internal.py:258`, `docs/decisions.md:60` — 기존 결정의 api-candidate 담당과 충돌하지만 실제 분업 확정 경로는 내부 PUT이므로 division·tasks를 한 트랜잭션으로 쓰는 편이 자연스러움 |
| 9. 동료 단독 파트만 쓰기·diff_ratio | 권한·revision·변경 비율 정의에 동의. B6의 종료 상태 검증 추가 필요 | `services/api/app/routers/internal.py:315`, `services/api/app/routers/internal.py:353`, `docs/agent/design.md:93` — both는 지원자가 쓰고 동료는 코멘트만 하는 규칙과 일치 |
| 10. current_element에서 흐름 카드가 창을 닫음 | 반대. B2에 따라 최신 결정으로 맞추고 충돌하는 문서를 함께 정리 | `services/api/app/routers/internal.py:91`, `docs/decisions.md:45` — 마지막 요소 창은 보고 단계까지 유지되어야 함 |
| 11. 테스트 세션의 token·회사 | 동의. 테스트 진입용 초대 토큰이면 링크로 consent·start를 거칠 수 있음. 토큰 종류를 계약에 명시 | `services/api/app/routers/internal.py:672`, `services/api/app/routers/internal.py:700` — 환경 플래그와 내부 인증으로 접근을 제한하며 token과 invite_url이 같은 원문을 사용 |
| 12. WEB_ORIGIN 첫 값·KST 안내 | 동의. 실제 만료 필드는 UTC, 사람이 복사하는 문구만 KST이므로 계약과 양립 | `services/api/app/routers/admin.py:400`, `services/api/app/routers/admin.py:410` — ISO 응답과 안내 문구 표현을 구분함 |

리뷰 조정 핵심 규칙은 대체로 충족한다. unknown item·중복 item·변경 시 빈 메모를 저장 전에 거부하고, null도 실제 조정으로 저장하며, 항목당 unique와 단일 트랜잭션을 사용한다. 변경 리뷰 재제출을 막고 동일 유효 내용은 재전달로 처리한다(`services/api/app/routers/admin.py:566`, `services/api/app/routers/admin.py:604`, `infra/db/schema.sql:212`).

FOR UPDATE는 리뷰의 Session과 문서 쓰기의 DocumentState에 적절하다. 단일 프로세스여도 공개·내부 요청은 동시에 처리되고 기존 asyncio 세션 Lock을 내부 라우터에서 재획득하면 그래프의 HTTP 호출과 교착할 수 있으므로, 짧은 DB 행 잠금은 합리적인 선택이다(`services/api/app/routers/admin.py:591`, `services/api/app/routers/internal.py:323`, `docs/agent/design.md:15`). 공개 예약 행 잠금도 타당하며 정상 시작 경로에서는 예약이 미리 생성된다(`services/api/app/routers/internal.py:434`, `services/api/app/services/session.py:164`).

### “남은 문제”

| 쟁점 | 의견·권장 처리 | 위치·한 줄 근거 |
|---|---|---|
| Idempotency-Key 없음 | 대체 처리로 충분하다는 판단에는 반대. B3를 공용 변경 요청에 포함 | `services/api/app/routers/admin.py:397`, `docs/common/contracts.md:12` — 초대 생성 재시도는 도메인 멱등으로 보호되지 않음 |
| 기본 422 형식 | 문제 인식·foundation 변경 요청에 동의. B5 해결 후 완료 판정 | `services/api/app/main.py:54` — 요청 검증 예외의 공통 핸들러가 없음 |
| 시작 문서 released_at 지연 | released_at 기준에 동의. 시작 직후 첫 그래프가 rag를 쓰기 전에 공개 기록을 보장하는 순서를 api-candidate와 정해야 함 | `services/api/app/routers/internal.py:406`, `services/api/app/services/session.py:164` — start는 예약만 만들므로 5초 루프만 기다리면 첫 대화에서 미공개로 보일 수 있음 |
| usage·attempts 미저장 | 이 트랙 계약상 누락 필드이므로 수용. 관측 기록 책임은 worker와 함께 확정하고 필요할 때 계약 변경 | `services/api/app/routers/internal.py:603`, `docs/common/data-model.md:23` — draft 요청은 content만 받음; 라우터가 워커 실행 정보를 추정할 수 없음 |
| 중복 가입 409·로그인 실패 401 | 동의. 인증 정상 실패 의미에 맞고 별도 설계 확장 불필요 | `services/api/app/routers/admin.py:95`, `services/api/app/routers/admin.py:118` — 중복 계정과 잘못된 자격 증명을 구분함 |

### “변경 요청”

| 쟁점 | 의견·권장 처리 | 위치·한 줄 근거 |
|---|---|---|
| 1. RequestValidationError 핸들러 | 동의. 공용 _base에 한 번 구현하고 8000·8001 모두 적용. 의미 오류를 HTTPException으로 직접 올린 현재 방식도 타당 | `services/api/app/main.py:51`, `services/api/app/routers/internal.py:50` — SessionError 기본 매핑에 기대지 않고 계약 상태 코드를 보존함 |
| 2. catalog·report·division·test token 계약 보강 | 동의하되 report의 review·history는 기존 필드임을 구분. adjusted와 각 내부 구조, duplicate_item·invalid_division, tasks 소유권을 명확히 함 | `docs/common/contracts.md:33`, `docs/common/contracts.md:54`, `services/api/app/routers/admin.py:570` — 구현 간 해석 차이를 줄이는 작은 공용 계약 변경임 |
| 3. final 오류 코드 | 동의. 상태 부적합 conflict, 승인 해시 불일치 draft_mismatch를 유지 | `services/api/app/routers/internal.py:636`, `docs/common/contracts.md:149` — 계약 표의 순서·코드와 일치함 |

## 4. 다른 트랙 주의사항

- **오케스트레이터/foundation** — `docs/decisions.md:60`, `services/api/app/main.py:51`: tasks 생성 책임을 api-admin 내부 PUT으로 일원화하는 결정을 기록하고 api-candidate에 전달할 것을 권장한다. Idempotency-Key와 422 공통 처리는 공용 파일 소유자에게 배정한다. 이 리뷰에서는 파일을 고치지 않았다.
- **api-candidate** — `services/api/app/routers/internal.py:258`, `services/api/app/routers/internal.py:406`: 분업 후 tasks가 만들어진다는 전제를 맞추고 중복 생성 로직을 두지 않는다. 시작 문서는 첫 agent 실행 전 공개되도록 순서를 보장한다. 상태 스냅샷·지원자 문서 쓰기는 이 트랙과 동일한 document_states/revisions를 사용한다.
- **agent-session** — `services/api/app/routers/internal.py:86`, `docs/agent/design.md:84`: B2 수정과 관찰 창 문서 정합화가 선행되어야 한다. set_division 뒤 동료 task를 doing으로, 리뷰 시 done으로 바꾸며 재분업 횟수는 그래프가 제한한다. 분류 결과를 관찰 함수에 공급할 읽기 경로도 합의한다.
- **business-mcp** — `services/api/app/routers/internal.py:230`, `docs/common/contracts.md:153`: 분업·권한 오류는 API가 최종 판단한다. 자동 재시도가 set_division에 들어가므로 B4 수정 전에는 결정 시각이 달라진다. 이미 main에 병합된 MCP 구현을 이 브랜치의 두 점 diff를 보고 삭제하면 안 된다.
- **worker** — `services/api/app/routers/internal.py:597`, `services/api/app/routers/internal.py:638`: final에는 저장한 draft content를 그대로 보내고 ensure_ascii=False·키 정렬·공백 제거 SHA-256 규칙을 공유한다. GET /admin/report의 합성 응답을 final로 보내면 해시가 다르다. 메시지는 기본 200개 제한이므로 전체 수집 방식과 B1 수정 뒤 since_t_min 사용을 확인한다.
- **web-admin** — `services/api/app/routers/admin.py:281`, `services/api/app/routers/admin.py:326`: reviewer=null만으로 무조정 여부를 판별하지 말고 adjusted를 사용한다. approving부터 목록은 reviewer 합계를 표시하며 final 전까지 reviewed_at은 null일 수 있다. 조정 메모를 관찰 서술 옆에도 표시한다(`docs/common/rubric.md:20`).
- **rag-mcp / e2e-runner** — `services/api/app/routers/internal.py:406`, `services/api/app/routers/internal.py:700`: released_at 기록 전 문서는 공개하지 않는다. 테스트 세션 token은 candidate JWT가 아닌 초대 링크 토큰이며, 짧은 세션도 consent·start를 거쳐야 한다.

## 검증 결과와 한계

- 정적 검토: 지정 라우터 전체, 테스트 18개, 공용 상태 서비스·인증·모델·DDL·계약·평가표·결정 기록을 대조했다. 소유권 밖 실제 트랙 수정과 MVP 과잉 분리는 발견하지 않았다(`docs/plan.md:51`, `docs/dev-process.md:34`).
- 테스트 재실행: `cd services/api && PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/private/tmp/codex-api-admin-uv uv run --offline pytest -q -p no:cacheprovider` → **2 passed, 21 errors**. `services/api/tests/conftest.py:39`의 PostgreSQL 연결에서 샌드박스 `PermissionError: [Errno 1] Operation not permitted`가 발생했다. 제품 assertion 실패로 해석하지 않으며, 개발자 보고의 23 passed를 독립 검증했다고 주장하지 않는다. 권한 확대가 허용되지 않는 환경이라 재시도하지 않았다.
- DB 없이 확인: `current_element()`의 흐름 카드 후 null, asyncpg dialect의 `make_interval(..., FLOAT)` SQL 생성, ASGI 422 detail 응답을 직접 확인했다. 새 테스트 파일과 제품 코드는 작성하지 않았다.
- lint/format 재실행: `uv run --offline ruff check ...`, `uv run --offline ruff format --check ...` 모두 `ruff` 실행 파일이 없어 시작하지 못했다. 개발자 보고의 make lint 성공은 독립 확인하지 못했다. 전체 스택·LLM·큐·외부 서비스는 실행하지 않았다.
