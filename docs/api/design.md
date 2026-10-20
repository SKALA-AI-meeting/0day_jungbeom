# api 설계 (FastAPI + LangGraph 모듈)

## 구조와 소유

```
services/api/app/
  main.py              FastAPI 앱 2개: 공개 /admin,/s,/sessions,/ws · 내부 /internal                     [foundation]
  run.py               uvicorn Server 두 개(8000, 8001)를 한 asyncio 루프에서 실행. hub·Lock·스케줄러 공유   [foundation]
  config.py, db.py     env, SQLAlchemy async                                                   [foundation]
  models/              테이블 모델                                                              [foundation]
  auth.py              JWT, 역할 의존성, bcrypt, 초대 토큰 해시                                  [foundation]
  services/session.py  SessionService: 상태 전이의 유일한 소유자                                 [foundation]
  services/scenario.py 카탈로그 로드(버전 해시), 조립, 이벤트·공개 예약 펼치기                     [foundation]
  hub.py               세션별 WS 연결, broadcast                                                [foundation]
  queue.py             RabbitMQ publish(persistent), 재발행 재탐색                               [foundation]
  masking.py           전화번호·이메일 마스킹                                                    [foundation]
  agent/runner.py      AgentRunner Protocol + FakeAgentRunner                                   [foundation]
  routers/admin.py     /admin/*                                                                 [api-admin]
  routers/internal.py  /internal/*                                                              [api-admin]
  routers/candidate.py /s/*, /sessions/*                                                        [api-candidate]
  routers/ws.py        /ws/sessions/{id}                                                        [api-candidate]
  scheduler.py         5초 루프                                                                 [api-candidate]
  agent/               세션·어시스턴트 그래프, observe, prompts                                   [agent-session, agent-assistant, prompts]
  Dockerfile, pyproject.toml, /health                                                           [foundation]
```

## 인증
`docs/common/contracts.md`의 인증 생명주기 표가 정본. 의존성 `require_admin`, `require_candidate(session_id 일치)`, `require_internal`. 내부 앱은 8001 포트에 따로 띄우고 compose에서 공개하지 않는다.

## SessionService
`create_for_invite`, `consent`, `start`(이벤트·공개 예약 펼치기), `complete(reason)`(submitted_at 커밋 → AgentRunner end(고정 run_id, 세션 Lock을 잡으므로 진행 중 run이 끝난 뒤 실행) → 재사용 추정 계산 → completed 커밋 → 큐 발행(confirm 후 enqueued_at) → session.ended), `mark_report_ready`, `approve`(approving 커밋 → report.approve 발행 → approve_enqueued_at 기록), `mark_reviewed`, `fail(reason)`. 모든 전이는 현재 상태를 검사하고 멱등이다.

## 스케줄러 (5초)
```
events:   status=pending AND due_at<=now → 같은 due_at 행을 card order로 묶어 하나의 run_id 생성·fired 커밋 → agent_runs started → runner.run(event, event_ids, run_id) → ok면 행마다 자기 event_id의 메시지가 있는지 확인해 done / 실패 시 attempts+1(총 3회까지 같은 run_id로 재실행, 아니면 failed+세션 fail)
runs:     agent_runs.status=started AND started_at < now-120s → 같은 run_id로 재실행
retry:    status=fired AND fired_at < now-60s → 재실행 (재시작 복구)
releases: release_at<=now AND released_at null → 기록 → document.released
timeouts: in_progress AND ends_at<=now AND submitted_at null → complete("timeout")
outbox:   status=completed AND report_enqueued_at null → report.generate 재발행
          status=approving AND approve_enqueued_at null → report.approve 재발행
ending:   in_progress AND submitted_at not null → complete() 재실행(종료 run_id 고정, 멱등)
```
세션별 Lock으로 메시지 자극과 직렬화. 같은 due_at 이벤트는 card order로 한 run에 처리.

## 제출 처리
`/submit` 또는 timeout → `complete()` 안에서 end 실행 뒤 `assistant_reuse` 계산.

`estimate_reuse(response: str, revisions: list[Revision]) -> (reuse, ratio, part_no, revision)` (순수 함수, `app/services/reuse.py`):
- 정규화: 공백·구두점 제거, 소문자. 응답 정규화 길이가 20자 미만이면 none.
- 비교 대상: 그 호출 **이후** 지원자가 저장한 모든 파트의 모든 revision(스냅샷 본문).
- ratio = (응답과 revision의 공통 부분 문자열 중 길이 20자 이상인 것들의 합) / 응답 정규화 길이. `difflib.SequenceMatcher.get_matching_blocks` 사용.
- 파트·revision 중 최대 ratio를 택한다. ≥0.8 verbatim, ≥0.3 edited, 아니면 none. 결과 행에 part_no와 revision을 남긴다.
- 예: 응답 120자, 파트 1 revision 3에 그대로 붙여넣음 → ratio 1.0 verbatim. 문장 절반만 가져감 → 0.5 edited.

## 문서 저장
`PUT /sessions/{id}/document/{part_no}`는 revision+1, `document_revisions`에 본문 스냅샷·길이·diff_ratio 기록. submitted_at 이후는 409 `session_ending`. 회사 문서 본문 조회는 `doc_views` 기록.

## 완료 기준
- foundation: `docker compose up`에서 api healthy, 모델·마이그레이션, SessionService 단위 테스트(전이 전부·멱등), 조립 결과가 scenario-model.md 수치와 일치, FakeAgentRunner로 메시지→내부 저장→hub 브로드캐스트(단위 테스트, WS 라우터는 api-candidate)
- api-admin: 관리자·내부 엔드포인트가 계약 예시대로, 기업 간 격리, elements 검증, 권한 밖 변경 403, 승인 전 final 409
- api-candidate: 지원자 엔드포인트·WS(ack, 증분, 재연결 후 /state), 6분 테스트 세션에서 이벤트가 ±10초 내 fired→done, 만료 시 큐 발행, 재시작 후 fired 이벤트 재실행, 미발행 세션 재발행
