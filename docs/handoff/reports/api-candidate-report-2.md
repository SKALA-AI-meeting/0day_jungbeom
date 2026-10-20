# api-candidate 수정 라운드 보고 (Codex 리뷰 반영)

- 브랜치 `track/api-candidate`, 커밋 `9bfe0c9`(`911aaa3` 위, 오케스트레이터 rebase 뒤 `82f5f8b`). main 병합·push·rebase 안 함(main에는 api-admin `9447848`이 이미 들어가 있어 contracts.md·decisions.md는 병합 때 충돌 정리가 필요할 수 있다. 이 트랙은 새 절만 추가했다)
- worktree의 `REVIEW.md`(추적 안 됨) 삭제함
- 이번 라운드 허용 범위의 foundation 파일 3개(`session.py`, `auth.py`, `messages.py`)만 고쳤다. 그 밖의 foundation 파일은 그대로

## 수정 목록

### 반드시
1. **스케줄러 세션별 직렬**(`app/scheduler.py` `_events`): 세션마다 "fired 또는 due된 pending 중 due_at이 가장 이른 묶음" 하나만 본다. pending이면 카드 순서로 묶어 fired → 실행, fired면 이 프로세스에서 실행 중(`_inflight`)이면 기다리고 아니면(재시작) fired_at < now-60s일 때 같은 run_id로 재실행. 앞 묶음이 done·failed·skipped가 되기 전에는 뒤 묶음을 fired로 만들지 않는다. 기존 `_retry`(fired 재실행)는 이 경로에 합쳤고, `_stale_runs`(120초)는 메시지 실행만 다룬다
2. **지원자 문서 PUT 권한**(`app/routers/candidate.py`): `sessions.division.parts[part_no] == "colleague"`면 403 `forbidden`. 분업 전(division 없음)에는 모든 파트 허용
3. **문서 PUT을 세션 Lock 안에서**: `put_document`가 `ctx.locks(session_id)`를 잡고 `_save_part`에서 세션을 다시 읽어(populate_existing) submitted_at → 409 `session_ending`, 진행 중 아님 → 409 `conflict`를 확인한 뒤 저장. 내부 라우터는 건드리지 않음(Lock 없음)
4. **디브리핑 기한**: `auth.debrief_deadline(ended_at)`(= +7일)과 `debrief_token(session_id, expires_at=None)`(exp를 그 시각으로). 기준 시각은 `submitted_at or ends_at`이고, 진행 중 실패는 `SessionService.fail(stage="session")`이 `ends_at = min(ends_at, now)`로 실패 시각을 남긴다(컬럼 추가 없이. 리포트 단계 실패는 세션 종료가 submitted_at이라 그 기준). `GET /s/{token}`과 `GET /sessions/{id}/debrief` 모두 기한이 지나면 410 `expired`
5. Idempotency-Key: 지시대로 아무것도 하지 않음
6. **접수 함수 검사 순서**(`app/services/messages.py`): submitted_at 검사를 status보다 먼저 → completed 이후 message.send도 `session_ending`
7. **카드 실패 트랜잭션**: 3회째 실패 시 카드 failed를 따로 커밋하지 않고 `SessionService.fail`이 같은 트랜잭션에서 커밋(fail()의 조회 전 자동 flush). 새 `_retry`는 "failed 필수 카드(texture 아님)가 남은 in_progress 세션"을 찾아 `fail(session, "card_failed:<card_id,...>")`로 수렴

### 같이
- `sync_tasks` 제거. 엔드포인트 테스트는 division과 tasks 행을 테스트 안에서 직접 만든다
- `SessionService.start()`: `releases_at_start` 행의 released_at을 시작 트랜잭션에서 바로 기록(지연 공개는 None). 스케줄러 releases는 released_at이 빈 행만 보므로 지연 공개만 기록·알림
- 실시간 스크립트: 9건·전부 done·최대 오차 ≤10초·completed·report.generate 1회를 PASS/FAIL로 출력하고 하나라도 실패면 exit 1
- `infra/.env.example`: JWT_SECRET 위에 "32바이트 이상" 주석(값은 그대로)

### 문서 동기화
- `docs/common/contracts.md`: "지원자 경로 보충" 절(초대 토큰 404, 디브리핑 기한 = 종료 +7일·410, 세션 실패 디브리핑 형태, 문서 PUT 권한·Lock·409, 시작 공개 즉시)과 WS 절 끝 "연결 거절과 오류 프레임"(4401→/resume 후 재연결, 4403, 4000, error 봉투와 code). 기존 문장은 고치지 않음
- `docs/api/design.md`: 스케줄러 표 아래 세션별 due_at 직렬 처리 문단, estimate_reuse 저장 규칙 한 줄(순수 함수는 최적 revision 반환, 저장은 호출×파트별 최대값)
- `docs/decisions.md` 맨 아래 "2026-10-20 api-candidate 리뷰 반영 (Codex)" 절: 1·2·3·4·7, 시작 시 즉시 공개, assistant_reuse revision 컬럼 보류, message.send 검사 순서

## 테스트 변경(완료 기준 테스트에 합침, 새 테스트 없음)
- `test_candidate_endpoints`: 분업 확정 뒤 동료 파트(4) 문서 PUT 403 `forbidden`, debrief_token exp == submitted_at + 7일. 시작 공개 문서를 수동으로 released 처리하던 준비 코드 삭제(start가 바로 공개)
- `test_ws_ack_increment_and_reconnect`: 제출 뒤 `session.ended` 프레임, 이어진 message.send에 `error{code: session_ending}`
- `test_fired_event_reruns_after_restart`: kickoff가 fired로 남은 채 division(10분)도 due인 시각(+11분)에 재시작 → 첫 tick 뒤 kickoff done·division pending, 이후 division done, event 메시지 순서가 kickoff(같은 run_id) → division
- `test_six_minute_session_fires_events_on_time`: document.released는 지연 공개 `interview_summary` 1건만(시작 공개 4건은 start가 기록)

## 검증 명령과 결과

| 명령 | 결과 |
|---|---|
| `cd services/api && uv run pytest -q` | **13 passed** |
| 저장소 루트 `make test` | **exit 0** (api 13, business-mcp 1, rag-mcp 1, report-worker 1, web 1) |
| 저장소 루트 `make lint` | **exit 0** (ruff check·format 52 files, eslint·prettier) |
| 실시간: `cd services/api && PYTHONPATH=. uv run python <scratchpad>/realtime_six_minutes.py` | **exit 0, PASS 5건**(9건·전부 done·최대 오차 1.0초 ≤ 10초·completed·report.generate 1회). 아래 출력 |

테스트 파일 밖에서 한 번씩 확인하고 지운 임시 검사(커밋 안 함):
- 디브리핑 기한: submitted_at을 8일 전으로 옮긴 세션 → `GET /s/{token}` 410 `expired`, `GET /debrief`(debrief JWT) 410 `expired`. 진행 중 실패 세션 → ends_at이 예정보다 앞당겨짐, 디브리핑은 `{events: [], persona_note: null, scoring_notice: 중단 안내, failed_stage: "session"}`
- PUT과 제출 경쟁: 다른 실행이 세션 Lock을 잡은 동안 PUT을 걸고 그 뒤에 complete()를 대기열에 넣음 → Lock을 먼저 기다린 PUT이 저장(revision 1)되고 그다음 종료, 제출 뒤 PUT은 `session_ending`. 리뷰가 지적한 "종료 뒤 커밋"은 Lock 안 재확인으로 생기지 않는다

### 실시간 확인 출력
```
kickoff 0.0/0.0/0.0, division 30.0/30.1/30.2, cooperation 90.0/90.3/90.3, responsibility 150.0/150.5/150.5,
midpoint_draft 180.0/180.5/180.6, flexibility 210.0/210.6/210.7, respect·review 270.0/270.8/270.8,
report_request 330.0/330.9/331.0   (due/fired/done 초)
worst |offset| = 1.0s, published report.generate at +361.1s (ends_at +360s), session.ended reason timeout
PASS events == 9 / all done / worst offset <= 10s / completed / published once
```
스크립트 결함: PASS/FAIL 루프 변수가 임시 DB 이름을 덮어써 이 실행의 임시 DB가 남았다. 확인 후 직접 지우고 변수 이름을 고쳤다(자세한 내용은 report-3).

## 남은 문제
- `POST /sessions/{id}/assistant`는 여전히 미구현(리뷰 동의대로 M2. REST 저장·한도·인증은 이 라우터, 그래프는 agent-assistant)
- active_runs의 actor·node는 자극 종류로 정한 추정값(M2에서 progress 상태 보관과 맞춤)
- 카드 직렬 처리로, 앞 묶음이 끝난 다음 tick(최대 5초)에 뒤 묶음이 나간다. 같은 시각에 쌓인 경우(재시작 뒤)만 해당하고 정상 진행에서는 묶음 간격이 분 단위라 영향 없음. 재시작으로 남은 fired 묶음은 fired_at+60초까지 기다리므로 그 뒤 카드도 그만큼 늦어진다(설계의 retry 60초 규칙 유지)
- 지원자 문서 PUT이 세션 Lock을 기다리므로 동료 응답(LLM) 생성 중에는 저장 응답이 그만큼 늦다. web은 PUT을 디바운스·대기 처리해야 한다(아래 알림)
- 진행 중 실패 시각을 ends_at에 겹쳐 기록한다. failed 세션의 ends_at은 "예정 종료"가 아니라 "실제 종료"가 된다. 별도 컬럼(failed_at)이 낫다면 foundation 스키마 변경이 필요하다
- 테스트 실행 시 PyJWT 키 길이 경고는 환경의 JWT_SECRET 때문(값 확인·출력 안 함). 예시 파일에 주석만 넣었다

## 다른 트랙에 알릴 것
- **web-office**: 문서 PUT이 진행 중 에이전트 실행이 끝날 때까지 기다릴 수 있다(수 초). 저장 요청을 겹쳐 보내지 말고 마지막 본문만 보내는 디바운스를 권장. 분업 확정 뒤 동료 파트 PUT은 403. 시작 직후 /state의 시작 공개 문서는 이미 released. 디브리핑 410 `expired`(종료 7일 뒤) 안내 화면 필요. WS 4401·4403·4000과 error 프레임은 contracts.md 새 표 참고
- **agent-session**: 같은 세션의 다음 카드 묶음은 앞 묶음이 done·failed·skipped가 된 뒤에만 실행된다. done 판정은 여전히 "ok=True이고 행마다 자기 event_id 메시지". 카드 최종 실패는 세션 fail과 같은 트랜잭션
- **api-admin**: tasks 생성은 내부 division PUT이 단독으로 맡는다(`sync_tasks` 제거됨). 문서 PUT 권한은 `sessions.division.parts`(문자열 키)를 본다
- **foundation/오케스트레이터**: 이번 라운드에서 고친 foundation 파일은 `session.py`(start 즉시 공개, fail(session)의 ends_at), `auth.py`(debrief_deadline, debrief_token expires_at), `messages.py`(검사 순서) 3개뿐
