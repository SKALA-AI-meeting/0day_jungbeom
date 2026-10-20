# api 설계 (FastAPI + LangGraph 모듈)

## 구조

```
services/api/app/
  main.py            앱 생성, 라우터 등록, 스케줄러 시작
  config.py          env
  db.py              SQLAlchemy async 세션
  models/            테이블 모델
  auth.py            JWT 발급·검증, 역할 의존성, bcrypt
  scenario.py        카탈로그 로드, 조립, session_events 펼치기
  routers/admin.py   /admin/*
  routers/candidate.py /s/*, /sessions/*
  routers/internal.py  /internal/*
  routers/ws.py      /ws/sessions/{id}
  hub.py             세션별 WS 연결 집합, broadcast
  scheduler.py       5초 루프: 이벤트 fire, 문서 공개, 만료 종료
  queue.py           RabbitMQ publish
  masking.py         전화번호·이메일 마스킹
  agent/             에이전트 모듈 (agent 트랙 소유)
```

## 인증

- 관리자: signup 시 company 생성. JWT `{sub: admin_id, role: admin, company_id}` 24시간.
- 지원자: `/s/{token}` 조회는 토큰 해시로 invite 조회. `/consent`에서 session 생성(status invited→consented_at 기록)하고 세션 JWT `{sub: session_id, role: candidate}` 발급. 만료는 세션 `ends_at`+1시간.
- 내부: `X-Internal-Token` 상수 비교.
- 의존성: `require_admin`, `require_candidate(session_id 일치)`, `require_internal`.

## 스케줄러

```
every 5s:
  fire events: due_at <= now, fired_at null → set fired_at → agent.run(session, "event", event_id)
  releases: release_at <= now, released_at null → set → broadcast document.released
  timeouts: status in_progress, ends_at <= now → complete(session, "timeout")
```
`complete()`는 status=completed, `agent.run(session,"end")`, 큐 발행, `session.ended` 브로드캐스트. 스케줄러는 세션 단위로 직렬 실행(세션별 asyncio.Lock)해서 메시지 자극과 겹치지 않게 한다.

## 자극 직렬화

`agent.run`은 세션별 Lock 안에서 실행된다. 지원자가 연속으로 메시지를 보내면 큐에 쌓여 순서대로 처리된다.

## 제출 처리

`/submit` 또는 timeout → `assistant_calls.reused_in_part` 계산(각 어시스턴트 응답과 각 파트의 정규화 문자열 겹침 비율: ≥0.8 verbatim, ≥0.3 edited, 아니면 none) → complete().

## 완료 기준

- api-core: 계약의 관리자·내부 엔드포인트가 예시대로 동작, 기업 간 격리 테스트, elements 검증, 조립 결과가 scenario-model.md의 수치와 일치하는 단위 테스트
- api-realtime: 지원자 엔드포인트·WS, 6분 테스트 세션에서 카드가 ±5초 내 fire되고 만료 시 큐 발행, 재시작 후 /state 복원
