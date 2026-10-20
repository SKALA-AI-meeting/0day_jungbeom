# api-admin 트랙 완료 보고 (W1)

- worktree `Day-0_zaeho.worktrees/api-admin`, 브랜치 `track/api-admin`, 커밋 `e3c201c`(foundation `c9fa550` 위). main 병합·push 안 함
- 키 값(`infra/.env`)은 출력·복사하지 않았다. 이 worktree에는 `infra/.env`가 없고 기본 DB 접속값(localhost:5432)으로 테스트가 돈다
- 통합 스택(`make up`, `app.run`)은 띄우지 않았다. 모든 검증은 ASGI 직접 호출(httpx) 단위 테스트다

## 완료 기준 실행 결과

| # | 기준 | 명령 | 결과 |
|---|---|---|---|
| 1 | 계약 예시대로 응답(가입·로그인, 카탈로그, 채용 건, 초대, 지원자 목록, 취소, 리포트) | `cd services/api && uv run pytest tests/routers/test_admin.py -k "follow_contract or invite_candidates or report_merges or candidate_list"` | 통과 |
| 2 | 기업 간 격리(다른 회사 채용 건·세션 404, 재응시 연결도 404) | `... -k other_company` | 통과 |
| 3 | elements 검증 400 `invalid_elements` | `... -k elements_are_validated` | 통과 (빈 배열·중복·미지 id·5개) |
| 4 | 권한 밖 변경 403 | `... -k reject_missing_or_non_admin` (관리자 아닌 JWT 403), `tests/routers/test_internal.py -k permissioned` (동료 담당 아닌 task·문서 PUT 403) | 통과 |
| 5 | 승인 전 final 409 | `... test_internal.py -k follow_approval` | 통과 (`conflict`, 해시 불일치는 `draft_mismatch`) |
| 6 | memo_required · already_reviewed(+ invalid_item · duplicate_item) | `... test_admin.py -k report_merges` | 통과. 규칙 위반 때 조정 행 0건·approve 미발행, 같은 본문 재요청 200 멱등(발행 1회), 다른 본문 409 |
| 7 | 내부 저장 멱등: 메시지(run_id·seq) | `... test_internal.py -k message_save` | 통과 (재요청은 같은 행, 브로드캐스트 1회) |
| 8 | 내부 저장 멱등: 문서 PUT(part_no·run_id) | `... -k permissioned` | 통과 (같은 run_id는 같은 revision, 새 run_id는 +1) |
| 9 | 내부 저장 멱등: 관찰(element·window_start), 근거 id 422 | `... -k observations` | 통과 |
| 10 | 분류 PUT·공개·task·division·읽기 엔드포인트 | `... test_internal.py` 나머지 | 통과 |
| 11 | `cd services/api && uv run pytest` | | **23 passed** (기존 5 + 신규 18) |
| 12 | 루트 `make test` | | exit 0 (api 23, business-mcp 1, rag-mcp 1, report-worker 1, web 1) |
| 13 | 루트 `make lint` | | exit 0 |

테스트 뒤 postgres에는 `dayzero`만 남는다(임시 DB 정리 확인).

## 수정(추가) 파일

- `services/api/app/routers/admin.py` (신규)
- `services/api/app/routers/internal.py` (신규)
- `services/api/tests/routers/{__init__,conftest,support,test_admin,test_internal}.py` (신규, 테스트 18개)

소유권 밖 파일은 수정하지 않았다. 테스트 공용 픽스처는 foundation의 `tests/conftest.py`를 건드리지 않고 `tests/routers/conftest.py`에 따로 두었다.

## 계약에 없어 내가 정한 것 (확인 필요)

1. **`/admin/catalog`**: `situation_public`은 카탈로그 카드의 `situation`, `pilot_value`는 없으면 false. `timeline.element_fraction_rule`은 규칙 설명 문자열, `candidate_notice_template`은 코드 상수(`{alias} {virtual_company} {expires_at} {invite_url}` 자리표시자). 카탈로그에 해당 필드가 없다.
2. **리뷰 응답 병합 표현**: `rubric.elements[].items[]`에 `adjusted: bool`을 더했다(조정값 null=기록 없음과 조정 없음을 구분). `reviewer`는 조정 행이 있을 때만 값, 요소별 `reviewer {met,judged,no_record}`·`reviewer_total`·`review {memo, reviewed_at}`는 리뷰 제출 뒤(`reports.reviewer_met`이 채워진 뒤)에만 non-null. `history[]`는 `{item_id, element, auto, reviewer, memo, created_at}`.
3. **리뷰 저장 시점**: `reports.reviewer_met/judged/review_memo`를 승인(approving 전이) 트랜잭션에서 채운다(data-model은 "검토 완료 시"라 적음). 목록 `score.source`는 이 값이 있으면 `reviewer`.
4. **자동 값과 같은 항목은 조정 행을 만들지 않는다**(메모 없이 통과). 이미 approving·reviewed인 세션에 같은 본문 재요청은 현재 status를 담아 200(`approving` 또는 `reviewed`). 세션 행을 `FOR UPDATE`로 잠가 동시 리뷰를 직렬화한다.
5. **`display_status`**: 코드값 문자열(`invited`/`expired`/`cancelled`/`in_progress`/...). 한글 라벨은 화면 몫.
6. **리포트 draft는 첫 저장이 이긴다**: 이미 report_ready 이상이면 본문을 덮어쓰지 않고 `{status: report_ready}`. 워커가 재전달해도 승인 해시가 흔들리지 않는다.
7. **final**: 본문(`reports.content`)은 불변으로 두고 stage=final, reviewed_at만 기록. 순서는 report 없음/상태 부적합 409 `conflict` → 해시 불일치 409 `draft_mismatch` → reviewed면 200 재전달.
8. **division**: 전 파트 지정 필수, `division_min` 위반·누락은 422 `invalid_division`. 확정 시 `tasks` 행을 만든다(없으면 insert, 있으면 assignee 갱신)고 `task.updated`를 브로드캐스트한다. 같은 요청 재호출은 멱등, 다른 안은 덮어쓴다(재분업 허용).
9. **task PUT / document PUT**: task 행이 없으면 404(task), 동료 단독(`colleague`)이 아니면 403. 문서 PUT도 동료 단독 파트만. 성공 시 `task.updated`·`document.part_updated`·`document.released`를 hub로 보낸다. `diff_ratio`는 `1 - SequenceMatcher.ratio()`(0=동일).
10. **`current_element`**: 결 메시지(texture)를 뺀, fired·done 카드 중 가장 늦은 `due_at`의 요소(같은 시각이면 요소가 붙은 쪽, 즉 respect). 요소 없는 흐름 카드가 가장 최근이면 null.
11. **`/internal/test/sessions`**: `ENABLE_TEST_API`가 꺼져 있으면 404. 켜져 있으면 "e2e 테스트 회사"(없으면 생성)에 채용 건과 초대를 만들고 `token`은 **초대 토큰 원문**, `invite_url`은 `WEB_ORIGIN[0]/s/<token>`.
12. **초대 안내 문안/URL**: `invite_url`의 기준은 `WEB_ORIGIN` 첫 값. 만료 시각은 KST로 문안에 적는다.

## 남은 문제

- **Idempotency-Key 미구현**: 계약 공통 항목("변경 요청은 `Idempotency-Key` 헤더를 받으며 같은 키는 같은 결과")인데 저장소(테이블)가 없다. 도메인 멱등(세션 전이, 리뷰 본문 비교, 내부 저장 멱등 키)으로 대신했다. 필요하면 foundation에서 테이블을 정해야 한다.
- **요청 본문 검증 실패(FastAPI 422)의 응답 형식**이 계약의 `{"error": {...}}`가 아니라 기본 `{"detail": [...]}`다. `main.py`에 `RequestValidationError` 핸들러가 없다(아래 변경 요청).
- **released 플래그는 `document_releases.released_at` 기준**이다. 시작 시 즉시 공개돼야 하는 문서(`releases_at_start`)도 스케줄러가 기록하기 전에는 `released: false`로 나온다. rag-mcp·지원자 문서 목록이 같은 규칙을 쓰므로 api-candidate 스케줄러가 시작 직후 첫 틱에서 기록해야 한다.
- `reports.usage`·`attempts` 컬럼은 내부 draft 요청에 필드가 없어 채우지 않는다(워커 LLM 사용량을 남기려면 계약에 필드 추가 필요).
- 같은 이메일 가입 409(`conflict`), 로그인 실패 401은 계약에 없어 추가했다.

## 변경 요청

1. (foundation, `main.py`) `RequestValidationError` 핸들러를 추가해 422도 `{"error": {"code": "invalid_input", ...}}` 형식으로. 내가 던지는 의미적 오류(`invalid_division`, `invalid_evidence`, `invalid_event`, `draft_mismatch`, `already_reviewed`, `memo_required`, `invalid_item`, `duplicate_item`, `invalid_elements`)는 라우터에서 `HTTPException`으로 상태 코드를 직접 지정했다. `ERROR_STATUS`에 없는 코드를 `SessionError`로 던지면 400이 되기 때문이다.
2. (contracts.md) 위 "계약에 없어 내가 정한 것" 1·2·8·11을 계약에 반영(catalog 필드 출처, 리포트 병합 필드 `adjusted`·`review`·`history`, division 오류 코드, 테스트 세션 `token` 의미). 오류 코드 `duplicate_item`(400)도 추가 필요(rubric.md는 "같은 item_id가 두 번이면 400"만 명시).
3. (contracts.md) 승인 전 final 409의 코드: 상태 부적합은 `conflict`, 해시 불일치는 `draft_mismatch`로 구현했다. 계약 표와 일치하므로 확인만.

## 다른 트랙에 알릴 것

- **web-admin**: 목록 `score`는 report 없으면 null, `source`는 `auto`/`reviewer`, `by_element[].{element,met,judged}`. 리포트 `rubric.elements[].items[]`의 `reviewer`/`memo`는 조정된 항목에만 값이 있고 `adjusted`로 구분한다. 리뷰 오류 코드: `memo_required`·`invalid_item`·`duplicate_item`(400), `already_reviewed`(409), 상태 부적합 `conflict`(409). 이미 제출한 리뷰와 같은 본문 재전송은 200.
- **worker**: draft/final 본문의 `rubric.elements[].items[]`는 각 항목에 `id`·`auto`가 필요하고 `rubric.auto_total {met,judged,no_record}`가 목록 합계의 원천이다. draft는 먼저 저장된 것이 유지되고, final은 draft와 정규화 JSON 해시(키 정렬·공백 제거·`ensure_ascii=False`, sha256)가 같아야 한다. `report_failed`는 이미 failed여도 200 멱등.
- **business-mcp**: `post_message`/`write_document_part`/`record_observation`/`release_document`/`update_task`/`set_division`이 호출할 내부 경로는 계약 그대로 구현됐다. 오류 형식은 `{"error": {"code", "message"}}`이고 의미 코드는 위 목록과 `forbidden`(403), `not_found`(404), `conflict`(409), 422(`invalid_*`)다. 문서 PUT·task PUT은 `set_division`으로 task 행이 만들어진 뒤에만 성공한다(없으면 task 404, 문서는 403).
- **api-candidate**: 분업 확정(`PUT /internal/.../division`)이 `tasks` 행을 만든다(foundation 보고의 "분업 확정 때 api-candidate가 만든다"와 달리 이 라우터가 만든다). 지원자 쪽 `tasks` 갱신(PUT /sessions/{id}/tasks)은 그 행을 전제로 한다. 분류 PUT은 `messages.meta.classification`에 쓴다. 스케줄러는 `releases_at_start` 문서의 `released_at`을 시작 직후 기록해야 내부 문서 목록의 `released`가 맞는다.
- **agent-session / e2e-runner**: `/internal/sessions/{id}`의 `current_element`·`t_min_now`는 요청 시각 기준으로 계산한다. 테스트 세션 생성 `/internal/test/sessions`는 `ENABLE_TEST_API=1`에서만 열린다.
