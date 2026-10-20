# api 설계 (FastAPI + LangGraph 모듈)

## 구조와 소유

```
services/api/app/
  main.py              앱 2개 마운트: 공개(8000) /admin,/s,/sessions,/ws · 내부(8001) /internal   [foundation]
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
`create_for_invite`, `consent`, `start`(이벤트·공개 예약 펼치기), `complete(reason)`(재사용 추정 계산 → completed → AgentRunner end → 큐 발행 → session.ended), `mark_report_ready`, `approve`(approving + report.approve 발행), `mark_reviewed`, `fail(reason)`. 모든 전이는 현재 상태를 검사하고 멱등이다.

## 스케줄러 (5초)
```
events:   status=pending AND due_at<=now → fired(커밋) → runner.run(event) → 성공 시 done / 실패 시 attempts+1(≤2 재실행, 아니면 failed+세션 fail)
retry:    status=fired AND fired_at < now-60s → 재실행 (재시작 복구)
releases: release_at<=now AND released_at null → 기록 → document.released
timeouts: in_progress AND ends_at<=now → complete("timeout")
outbox:   status=completed AND report_enqueued_at null → report.generate 재발행
```
세션별 Lock으로 메시지 자극과 직렬화. 같은 due_at 이벤트는 card order로 한 run에 처리.

## 제출 처리
`/submit` 또는 timeout → `assistant_reuse` 계산(호출 응답 × 파트 내용의 정규화 문자열 겹침: ≥0.8 verbatim, ≥0.3 edited, 아니면 none) → complete().

## 문서 저장
`PUT /sessions/{id}/document/{part_no}`는 revision+1, `document_revisions`에 길이·diff_ratio 기록. 회사 문서 본문 조회는 `doc_views` 기록.

## 완료 기준
- foundation: `docker compose up`에서 api healthy, 모델·마이그레이션, SessionService 단위 테스트(전이 전부·멱등), 조립 결과가 scenario-model.md 수치와 일치, FakeAgentRunner로 메시지→post→WS 흐름
- api-admin: 관리자·내부 엔드포인트가 계약 예시대로, 기업 간 격리, elements 검증, 권한 밖 변경 403, 승인 전 final 409
- api-candidate: 지원자 엔드포인트·WS(ack, 증분, 재연결 후 /state), 6분 테스트 세션에서 이벤트가 ±5초 내 fired→done, 만료 시 큐 발행, 재시작 후 fired 이벤트 재실행, 미발행 세션 재발행
