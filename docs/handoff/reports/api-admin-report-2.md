# api-admin 수정 라운드 보고 (Codex 리뷰 반영)

브랜치 `track/api-admin`, 커밋은 `git log -1`(e3c201c 위). worktree의 `REVIEW.md`는 삭제함. main 병합·push 안 함. 키 값 출력 없음.

## 수정 목록
- **B1** `internal.py`: `since_t_min`을 `started_at + timedelta(minutes=…)`로 계산해 비교(`make_interval` 제거). 기존 메시지 테스트에 소수 분(1.5, 0.0) 경로 추가.
- **B2** `current_element(events, status)`: 가장 최근 fired/done **요소 카드**의 요소. 흐름 카드·texture는 창을 닫지 않음. in_progress일 때만 값이 있고(제출 뒤 종료 실행 중에도 in_progress라 마지막 창이 열려 있음) completed 이후는 null. 테스트: responsibility 50분 → report_request 110분 done 뒤에도 `responsibility`.
- **B3** contracts.md 공통에서 `Idempotency-Key` 제거(CORS 헤더 포함), 멱등은 도메인 규칙으로만, 생성 POST 자동 재시도 없음. decisions.md 기록.
- **B4** 같은 parts·decided_by 재요청은 저장된 division 그대로(decided_at 유지), 브로드캐스트 생략. 분업 테스트에 합침.
- **B5** `main.py` `_base`에 `RequestValidationError` 핸들러(422 `invalid_input`, 두 앱 공통). 테스트: 관리자 로그인 본문 누락, 내부 메시지 본문 누락.
- **B6** 문서 PUT·task PUT은 in_progress일 때만(분업 PUT은 원래 그랬음). 이미 저장된 run_id 재전달은 기존 결과. 종료 뒤 새 쓰기 409·재전달 200·task 409를 권한 테스트에 합침.
- **같이**: 내부 메시지 GET·POST·분류 PUT 응답에 `meta` 포함(공개 API 제외, 테스트 반영) / final 재전달은 세션 행 `FOR UPDATE` 안에서 상태 재조회 / 리뷰 오류 우선순위: 이미 제출된 세션은 `already_reviewed`(409)가 400 검증보다 먼저(테스트 반영) / tasks 생성은 내부 division PUT(한 트랜잭션)으로 확정.
- **문서**: contracts.md(catalog 필드 출처, 리포트 `adjusted`·`review`·`history`, `invalid_division`·`duplicate_item`, 테스트 세션 token=초대 토큰, 가입 409·로그인 401, 오류 우선순위, 내부 meta, 종료 뒤 쓰기 거부, B3), data-model.md("리뷰 제출(approving 전이) 트랜잭션"), decisions.md "2026-10-20 api-admin 리뷰 반영" 절.

## 수정 파일
`services/api/app/main.py`(B5 허용), `app/routers/{admin,internal}.py`, `tests/routers/{test_admin,test_internal}.py`, `docs/common/{contracts,data-model}.md`, `docs/decisions.md`

## 검증
| 명령 | 결과 |
|---|---|
| `cd services/api && uv run pytest` | 23 passed (테스트 수는 그대로, 기존 테스트에 합침) |
| `make test` | exit 0 |
| `make lint` | exit 0 |

## 남은 것 / 알릴 것
- scenario-model.md:62, agent/design.md:70의 "흐름 카드도 창을 닫음" 문구는 건드리지 않았다(오케스트레이터 정합화).
- 브랜치는 main 위 rebase 전이다(main에 99f2fff·502b88b·7b04ef8 추가됨). 병합 전 rebase 후 `make test`·`make lint` 필요.
- api-candidate: sync_tasks 제거, 시작 문서 released_at 첫 틱 기록. agent-session: 재분업 시 task 상태 전이(doing/done)는 그래프 책임.
