# api-candidate 트랙 완료 보고 (W1)

- worktree: `Day-0_zaeho.worktrees/api-candidate`, 브랜치 `track/api-candidate` (기준 `c9fa550`). main 병합·push 안 함
- 커밋: `911aaa3` (`c9fa550` 위 1개). 작업 트리 깨끗함
- 인프라는 main 저장소에서 띄운 `make infra-up` 상태 그대로 썼다. `make up`·`app.run`은 띄우지 않았다(실시간 확인은 포트 없이 스케줄러 루프만 임시 DB에서 돌림)
- `infra/.env` 키 값은 출력·복사하지 않았다

## 완료 기준 실행 결과

| # | 완료 기준 | 명령 | 결과 |
|---|---|---|---|
| 1 | 지원자 엔드포인트 | `cd services/api && uv run pytest -v tests/test_candidate.py::test_candidate_endpoints` | **통과.** GET /s/{token}(회사 이름·120분·요소 이름 4개·"2시간"·"루프랩" 안내, debrief_token 없음) → consent → start(재호출 같은 값) → resume(링크만으로 JWT 재발급) → 다른 세션 JWT로 /state 403 → 문서 목록(interview_summary 미공개) → 미공개 본문 423 `not_released` → metrics 본문 200과 `doc_views` 1행 → 작업 카드: 지원자 파트 200, 동료 파트 403 → 문서 PUT revision 1→2, 같은 본문 재요청은 2 유지 → /state의 최상위·session 키가 `tests/fixtures/contracts/state.json`과 같음(파트 1 revision 2, 파트 2 revision 0, persona "한서윤 팀장"·"이도현") → submit 두 번 모두 `{status: completed}`, report.generate 1회 → GET /s/{token}에 completed와 debrief_token → 디브리핑은 done인 cooperation 카드만, 평가표 문장 4개, persona_note·scoring_notice |
| 2 | WS(ack, 증분, 재연결 후 /state) | `uv run pytest -v tests/test_candidate.py::test_ws_ack_increment_and_reconnect` | **통과.** message.send → `message.ack → message.new(지원자) → agent.progress(started) → message.new(동료, 같은 run_id) → agent.progress(finished)`. 같은 client_msg_id 재전송은 같은 ack만. 두 번째 연결 시 첫 연결이 `session.replaced`를 받고 close 4000. 재연결 뒤 /state에 메시지 2건(지원자·동료), active_runs 빈 배열. 새 소켓이 다음 메시지의 ack를 받음 |
| 3 | 6분 테스트 세션(L=6)에서 이벤트가 ±10초 내 fired→done (FakeAgentRunner) | `uv run pytest -v tests/test_scheduler.py::test_six_minute_session_fires_events_on_time` | **통과.** 시각을 tick(now)으로 5초씩 0~355초 진행. 9행 전부 done, 모든 행 \|fired_at − due_at\| ≤ 10초, 행마다 자기 event_id의 message.new, review·respect가 같은 run_id, document.released 5건(지연 공개 포함) |
| 3' | (같은 기준, 실제 시계) | 스크래치 스크립트 `realtime_six_minutes.py`(아래 "실시간 확인") | **통과.** 실제 5초 루프(`scheduler.run(ctx)`)로 L=6·요소 4개 세션을 끝까지 돌림. 9행 전부 done, 최대 \|fired·done − due\| = 1.0초. 만료 +361.1초(ends_at +360초)에 report.generate 발행, `session.ended{reason: timeout}` |
| 4 | 만료 시 큐 발행 (FakePublisher) | `uv run pytest -v tests/test_scheduler.py::test_timeout_completes_and_publishes` | **통과.** ends_at+1초 tick → `complete("timeout")` → completed, report_enqueued_at 기록, report.generate `{session_id, attempt: 1}` 1회, 마지막 프레임 `session.ended{reason: timeout}` |
| 5 | 재시작 후 fired 이벤트 재실행 | `uv run pytest -v tests/test_scheduler.py::test_fired_event_reruns_after_restart` | **통과.** kickoff를 3분 전 fired·agent_runs started로 남긴 상태(죽은 프로세스 흉내)에서 새 Scheduler로 tick 2회 → done, 같은 run_id, attempts 1→2, 그 run_id의 메시지는 kickoff 1건뿐(중복 없음), agent_runs finished |
| 6 | 미발행 세션 재발행 | `uv run pytest -v tests/test_scheduler.py::test_unpublished_session_is_republished` | **통과.** 발행 실패로 report_enqueued_at이 빈 completed 세션 → tick의 outbox가 1회 재발행, report_enqueued_at 기록 |
| 7 | estimate_reuse 예시 2개(verbatim 1.0, edited 0.5) | `uv run pytest -v tests/test_reuse.py` | **통과.** 정규화 120자 응답을 파트 1 revision 3에 그대로 → `("verbatim", 1.0, 1, 3)`, 앞 절반(60자)만 → `("edited", 0.5, 4, 2)` |
| 8 | submitted_at 이후 PUT 409 session_ending | `uv run pytest -v tests/test_candidate.py::test_document_put_after_submit_is_session_ending` | **통과.** 제출 뒤 문서 PUT → 409 `session_ending`. 같은 테스트에서 reuse 훅 연결 확인: 제출 전 어시스턴트 응답을 파트 1에 붙여넣은 세션의 assistant_reuse가 `(call_id, 1, verbatim, 1.0)` 한 행 |
| 9 | `cd services/api && uv run pytest` | 그대로 | **통과.** 13 passed(기존 5 + 이 트랙 8) |
| 10 | 루트 `make test` | 저장소 루트 | **통과(exit 0).** api 13, business-mcp 1, rag-mcp 1, report-worker 1, web(vitest) 1. web은 이 worktree에 node_modules가 없어 pnpm이 처음 실행 때 설치했다 |
| 11 | 루트 `make lint` | 저장소 루트 | **통과(exit 0).** ruff check·format(52 files), eslint·prettier |

### 실시간 확인
명령: `cd services/api && PYTHONPATH=. uv run python <scratchpad>/realtime_six_minutes.py` (스크립트: `/private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-Day-0-zaeho-worktrees-api-candidate/3d4d8df8-9ea0-4d2a-bbe2-ed4b919b9a30/scratchpad/realtime_six_minutes.py`). 임시 DB `dayzero_rt_<랜덤>`을 만들고 끝나면 지웠다(실행 뒤 남은 `dayzero_rt_*` 없음 확인). 포트는 열지 않았고 FakeAgentRunner·가짜 발행기를 썼다.

```
session status=completed
card            due_s  fired_s  done_s  fired-due  done-due  status
kickoff            0.0      0.0     0.0       0.0       0.0  done
division          30.0     30.1    30.1       0.1       0.1  done
cooperation       90.0     90.3    90.3       0.3       0.3  done
responsibility   150.0    150.4   150.5       0.4       0.5  done
midpoint_draft   180.0    180.5   180.6       0.5       0.6  done
flexibility      210.0    210.6   210.6       0.6       0.6  done
respect          270.0    270.8   270.8       0.8       0.8  done
review           270.0    270.8   270.8       0.8       0.8  done
report_request   330.0    330.9   331.0       0.9       1.0  done
worst |offset| = 1.0s (limit 10s)
published report.generate at +361.1s (ends_at +360s)
session.ended frames: [{'type': 'session.ended', 'payload': {'reason': 'timeout'}}]
```
오차가 카드마다 약 0.1초씩 커지는 것은 루프가 tick 처리 뒤에 5초를 쉬어 tick 시점이 조금씩 밀리기 때문이다. 각 tick은 due_at<=now인 행을 모두 집으므로 120분 세션에서도 오차는 누적되지 않고 "간격 5초 + tick 처리 시간" 안에 머문다.

## 수정 파일

| 파일 | 내용 |
|---|---|
| `services/api/app/routers/candidate.py` (새) | `/s/{token}` GET·consent·resume·start(Bearer, 토큰의 세션과 일치 확인), `/sessions/{id}/state`(State 스냅샷), `PUT document/{part_no}`(행 잠금, revision+1, `document_revisions` 스냅샷·length·diff_ratio, 같은 본문은 그대로 반환, DB 시각 사용), `PUT tasks/{part_no}`(candidate·both만, 아니면 403), `GET documents`, `GET documents/{doc_id}`(미공개 423 `not_released`, `doc_views` 기록), `POST submit`(complete를 Lock 밖에서), `GET debrief`(세션 JWT 또는 debrief_token, done인 요소 카드만), 분업 확정용 `sync_tasks(db, session_id, parts)` |
| `services/api/app/routers/ws.py` (새) | `/ws/sessions/{id}?token=`: accept 후 토큰 검증(실패 4401, 다른 세션 4403), hub 연결, `message.send` 검증 → `accept_candidate_message` → 새 메시지면 `scheduler.spawn(run_id, run_message)`(run_agent 기본 lock_held=False), 오류는 `{"type":"error","payload":{code,message}}` |
| `services/api/app/scheduler.py` (새) | `async def run(ctx)` 5초 루프와 `Scheduler.tick(now)`: releases·events·retry·runs·timeouts·ending·outbox(60초). 같은 due_at 묶음을 카드 순서로 한 run_id, fired는 tick 안에서 커밋, 실행은 백그라운드(키별 1개). 카드 실행은 세션 Lock 안에서 상태 재확인 → attempts+1 → agent_runs started로 되돌림 → run_agent(lock_held=True) → 행마다 자기 event_id 메시지가 있으면 done, 3회째 실패면 failed(texture는 skipped)와 세션 fail(`card_failed:<card_id>`). `spawn`·`drain`·`run_message`·`complete` |
| `services/api/app/services/reuse.py` (새) | `estimate_reuse`(순수 함수, design.md 알고리즘, `autojunk=False`), `record_reuse`(complete의 reuse 훅: 호출×파트별 최대 ratio를 assistant_reuse에 upsert) |
| `services/api/app/services/context.py` (foundation 파일, plan.md가 이 트랙에 넘긴 reuse 훅 연결만) | `session_service()`가 `reuse_estimator=record_reuse`를 넘긴다 |
| `services/api/tests/test_candidate.py`, `test_scheduler.py`, `test_reuse.py` (새) | 완료 기준 한 줄당 테스트 하나(8개) |

## 남은 문제
1. **`POST /sessions/{id}/assistant` 미구현.** 지원자 REST 표에는 있지만 브리프 범위 목록에 없고, 어시스턴트 그래프(agent-assistant, M2)가 필요하다. 라우터 소유가 candidate.py이므로 M2에서 누가 붙일지 정해야 한다
2. **`Idempotency-Key` 헤더는 처리하지 않는다.** 저장할 테이블이 없다. 대신 문서 PUT은 같은 본문이면 revision을 올리지 않고, start·consent·submit은 SessionService가 멱등이다
3. **시작 시 공개 문서는 첫 tick(최대 5초)까지 `released: false`**다. `start()`는 document_releases를 released_at 없이 만들고, released_at은 스케줄러가 기록한다. 그 사이 본문 조회는 423이다
4. **active_runs의 actor·node는 추정값**이다. agent_runs에 그 컬럼이 없어 자극 종류로 정했다: message → colleague/respond, event → 카드 actor(manager면 manager, 아니면 colleague)/inject, end → colleague/end
5. **assistant_reuse에 revision이 없다.** design.md는 "결과 행에 part_no와 revision을 남긴다"인데 스키마 PK는 (call_id, part_no)이고 revision 컬럼이 없다. 호출×파트별 최대 ratio만 저장한다. estimate_reuse 반환값에는 revision이 있다
6. 단위 테스트의 ±10초는 tick에 넘긴 시각으로 본 fired_at 오차다. done까지의 실제 지연은 위 실시간 확인으로 따로 쟀다
7. 카드 실행 재시도는 같은 작업 안에서 2초 뒤 바로 한다(최초 포함 3회). 백오프 간격은 문서에 없어 정했다
8. 테스트 실행 시 PyJWT가 HMAC 키 길이 경고를 낸다(현재 환경의 JWT_SECRET 길이). 값은 확인·출력하지 않았다. 운영 전 32바이트 이상으로 바꾸는 것이 좋다

## 변경 요청 (오케스트레이터)
1. **contracts.md WS 절**에 추가: 인증 실패 close code(`4401` 토큰 없음·만료 → `/resume`, `4403` 다른 세션), 오류 프레임 `{"type":"error","payload":{"code","message"}}`(`session_ending`, `conflict`, `invalid_input`)
2. **contracts.md 디브리핑**: 세션 실패(failed_stage=session) 응답 형태를 정해 달라. 지금은 `{events: [], persona_note: null, scoring_notice: <중단 안내>, failed_stage: "session"}`로 키는 계약대로 두고 연출·페르소나는 비웠다. 별도 `notice` 필드가 낫다면 바꾸겠다
3. **contracts.md 지원자 REST**: 알 수 없는 초대 토큰은 404 `not_found`로 돌려준다(표에 없음)
4. (선택) `SessionService.start()`(foundation)가 `releases_at_start` 행의 released_at을 시작 시각으로 바로 기록하면 "남은 문제 3"의 5초 공백이 없어진다
5. (선택) assistant_reuse에 `revision int` 컬럼(schema.sql·models, foundation) — design.md 문구와 맞추려면

## 다른 트랙에 알릴 것
- **api-admin**: `PUT /internal/sessions/{id}/division`이 분업을 저장할 때 같은 트랜잭션에서 `from app.routers.candidate import sync_tasks`; `await sync_tasks(db, session_id, parts)`를 부르고 커밋해 달라(parts는 `{part_no: candidate|colleague|both}`, 재분업이면 담당만 바뀌고 status는 유지). 내부 `GET /documents`의 released는 `document_releases.released_at`(스케줄러가 기록) 기준으로 맞추면 지원자 화면과 같다. `POST /internal/.../releases/{doc_id}`가 released_at을 먼저 기록하면 스케줄러는 그 행을 건너뛰고 document.released도 보내지 않는다(그쪽에서 브로드캐스트 필요)
- **web-office**: WS close code 4401(→ `POST /s/{token}/resume` 후 재연결)·4403·4000(session.replaced). 오류 프레임 type은 `error`. State의 `messages`에는 `assistant` 채널을 넣지 않고 `assistant` 배열로 따로 준다(`notice`는 messages에 있음). `remaining_seconds`는 서버 시각 기준 정수. 시작 직후 최대 5초 동안 문서가 미공개로 보일 수 있고 `document.released`가 오면 갱신하면 된다. 디브리핑 세션 실패 형태는 변경 요청 2
- **agent-session**: 카드 실행 Stimulus의 `event_ids`는 재시도에도 항상 같은 묶음 전체를 카드 순서로 넘긴다(seq 슬롯이 순번에 묶여 있으므로). done 판정은 "ok=True이고 행마다 자기 event_id를 단 메시지가 있음". 같은 run_id 재실행은 최초 포함 3회, 그다음 failed와 세션 fail(`card_failed:<card_id>`), texture는 skipped(세션 유지). 실행 중에는 세션 Lock을 스케줄러가 잡고 `run_agent(lock_held=True)`로 부른다. 메시지 실행은 `scheduler.run_message`(Lock은 run_agent가 잡음)
- **agent-assistant**: `record_reuse`는 `assistant_calls.response_message_id → messages.content`를 응답 원문으로 쓰고, 그 호출의 `created_at` 이후 지원자(by=candidate) revision과 비교한다. 응답 메시지는 assistant_call과 같은 트랜잭션이나 그 전에 저장해야 한다
- **worker**: assistant_reuse는 호출×파트당 한 행(파트별 최대 ratio). 지원자가 그 호출 뒤 고친 파트만 행이 있다
