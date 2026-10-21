# 아키텍처

MVP 원칙: **평가 항목이 요구하는 조각만 분리하고 나머지는 합친다.** 분리하는 것은 MCP 서버 2개, 큐와 워커, 프론트뿐이다. 에이전트는 api 프로세스 안의 모듈이다.

## 구성 요소

| 구성 요소 | 책임 | 기술 |
|---|---|---|
| web | 기업 관리자 화면, 지원자 가상 오피스 | Next.js App Router, Tailwind. `/admin/*`, `/s/[token]` |
| api | 인증, 화면 API, WebSocket, DB 쓰기, 세션 시계·이벤트 스케줄러, LangGraph 에이전트 모듈(동료·팀장·어시스턴트·관찰) | FastAPI + LangGraph, 한 프로세스 |
| business-mcp | 세션·메시지·보드·문서(동료 문서 보내기, 공유된 문서 읽기)·관찰의 조회·변경 도구. api 내부 엔드포인트 호출 | FastMCP, Streamable HTTP `:9101/mcp` |
| rag-mcp | 회사 문서 검색·조회·색인 | FastMCP, Streamable HTTP `:9102/mcp`, BGE-M3, pgvector |
| report-worker | 세션 종료 후 리포트 생성, 재시도, DLQ | Python, RabbitMQ consumer |
| infra | 컨테이너, 큐, DB, 관측 | Docker Compose, RabbitMQ, PostgreSQL 16 + pgvector, LangSmith(env) |

## 원칙

1. **DB 쓰기는 api만 한다.** MCP와 워커는 api의 `/internal/*`(별도 포트 8001, 미공개)을 부른다. 예외는 LangGraph checkpointer 테이블(api 에이전트 모듈은 `session:`·`assistant:` thread, report-worker는 `report:` thread만)과 rag-mcp의 `doc_chunks`.
2. **시간의 주인은 api다.** 세션 시작·종료 시각과 이벤트 예정 시각을 DB에 두고(화면과 페르소나가 쓰는 오피스 시각 09:00~11:00은 이 시계를 같은 비율로 바꾼 표시값이다), 5초마다 도는 스케줄러가 때가 된 이벤트를 집어 그래프를 호출한다. 접속이 끊겨도 시계는 흐른다. 이벤트는 pending→fired→done 상태를 가지며, 프로세스가 재시작되면 fired인데 done이 아닌 이벤트를 재실행한다(메시지 저장이 run_id·seq로 멱등).
3. **에이전트는 자극에 반응하는 함수다.** 자극은 지원자 메시지, 이벤트 도래, 분업 확정(지원자의 분업안 공유·재공유), 세션 종료 네 가지. 자극마다 그래프를 한 번 실행하고 체크포인트에 남긴다. 세션 하나 = thread 하나.
4. **시나리오는 데이터다.** 채용 건의 `mission_id`가 가리키는 미션 카탈로그(`scenarios/missions/<id>/`)를 조립한 `positions.scenario` JSON이 카드 목록과 시점을 담고 코드는 해석만 한다.

## 요청 흐름

### 지원자 메시지
1. web → api WS `message.send{client_msg_id}`
2. api: 민감정보 마스킹 → 저장(client_msg_id 멱등, DB 커밋) → `agent_runs` started(커밋) → `message.ack{run_id}`와 `message.new` 브로드캐스트 → `AgentRunner.run(session_id, stimulus=message, run_id)` → finished/failed 기록
3. 그래프: `agent.progress` 이벤트를 WS로 중계하며 실행(LLM 호출 타임아웃 30초, 응답당 도구 3회). 회사 질문이면 rag-mcp 검색. 응답은 business-mcp `post_message{run_id, seq}`
4. business-mcp → api `POST /internal/sessions/{id}/messages` → 저장(멱등) → 브로드캐스트

경계: DB 커밋은 2와 4. 외부 호출은 3(OpenAI, MCP). 재시도는 LLM 2회, MCP upstream 1회. 그래프가 실패하면 고정 문장 폴백을 4와 같은 경로로 저장한다.

### 이벤트 도래
1. 스케줄러가 `status=pending AND due_at <= now`를 집어 `fired`로 바꾸고(커밋) `AgentRunner.run(stimulus=event)`
2. `inject`가 카드를 실행(시스템 카드는 LLM 없이 고정 문장, 문서를 보내는 카드는 `send_document`에 event_id와 파트별 고정 seq), 이어서 요소 카드면 `observe`가 직전 열린 창([이전 요소 카드 due_at, 이 카드 due_at). planning_division은 세션 시작부터)을 카드 단위로 `record_observation`. 흐름 카드·texture는 창을 닫지 않고, 같은 시각의 흐름 카드+요소 카드는 요소 카드 기준. 창 밖 근거는 메시지의 `related_card`만. 행마다 자기 event_id의 카드 메시지가 저장되면 `done`
3. 실패 시 attempts+1로 재실행(최초 포함 총 3회, 같은 run_id), 3회째도 실패면 이벤트 failed·세션 failed·`session.ended{failed}`. `send_document`가 1회 재시도 뒤에도 실패하면 그 시도는 실패이고 이벤트 행에 `document_missing`을 남긴다

### 분업 확정
지원자가 섹션 담당 5개를 정하고 **분업안 공유**를 누르면 api가 5개 섹션 담당과 `division_min`을 한꺼번에 검사해 불변 스냅샷으로 division을 확정하고(할 일 개수는 검사하지 않음. decided_by=candidate, task_events, WS `division.confirmed`. 위반이면 422와 위반 섹션 목록) 동료 그래프를 `stimulus=division`으로 한 번 실행해 work_notes를 갱신한다. 동료가 실행 담당인 할 일이 보드에 있으면 그 할 일만 doing으로 바꾸고, 할 일이 0개면 보드는 건드리지 않는다. 채팅으로 정한 분업은 동료 그래프가 `set_division`으로 섹션 담당 draft를 쓰고 같은 검사로 스냅샷을 만든다(할 일 행은 만들지 않음). 다음 요소 카드까지 미확정이면 동료가 기본안으로 확정한다.

### 세션 종료와 리포트
1. 제출(한서윤에게 보내기) 또는 `ends_at` 도달 → `SessionService.submit(reason, message?)`: 세션 Lock 안에서 대기 중 저장을 끝내고 `submitted_at` 기록과 최종본 version 생성, 제출 메시지(최종본 카드, 본문은 선택)를 한서윤 DM에 `kind=report`로 저장, 한서윤 고정 답장("받았어요, 수고하셨어요.", LLM 없음) 저장(커밋, 이후 문서·보드·어시스턴트는 409 `session_ending`, 메시지는 WS 오류 `session_ending`). 아직 pending인 진행 확인 DM 카드(honesty_report 또는 흐름 report_request)는 DM을 보내지 않고 제출 시점에 정직 창을 연다. 이어서 같은 요청 안에서 `SessionService.complete()`: `AgentRunner.run(stimulus=end, run_id=uuid5(session_id,"end"))`로 마지막 창 정리(열린 창 닫기, collab_help의 `promise_kept`를 `update_observation`으로 갱신) → 재사용 추정 계산 → `status=completed`·`completed_at`(커밋). 중간 상태는 없다. end 실행 전에 죽으면 스케줄러가 `submitted_at`이 있고 `completed_at`이 없는 세션을 다시 complete()하며 같은 run_id라 중복이 없다. 리포트 발행은 마지막 관찰이 저장된 뒤에만 일어난다
2. api가 RabbitMQ `report.generate`에 `{session_id}` 발행(persistent), `report_enqueued_at` 기록. 발행 실패나 프로세스 종료로 기록이 비어 있으면 스케줄러가 60초마다 재탐색해 재발행
3. report-worker 그래프 `collect → draft → interrupt → finalize`. interrupt 체크포인트 저장 → draft 저장 → `status=report_ready` → ack(이 순서라 ack 뒤 승인은 항상 재개 대상이 있다). 관리자 검토 완료 → api `status=approving`(커밋) → `report.approve` 발행·`approve_enqueued_at` 기록(비어 있으면 스케줄러가 재발행) → 워커가 같은 thread 재개 → final 저장 → `status=reviewed` → ack
4. 워커 실패는 attempt+1 재발행(백오프 5·15·45초), 3회면 `report.dlq`. dlq 소비자가 `report_failed` → `status=failed`. api가 내려가 있으면 재발행과 dlq 처리가 큐에 남았다가 복구 후 처리된다. 담당자의 "리포트 다시 생성"(`POST /admin/sessions/{id}/report/regenerate`)은 completed로 되돌리고 `report.generate`를 다시 발행한다
5. 관리자 화면은 리포트 근거의 `record_ref`로 전체 기록(`GET /admin/sessions/{id}/record`, 시간순 통합 목록)의 해당 위치로 이동한다. 샘플 리포트는 web 정적 픽스처, 인쇄·PDF는 web 인쇄 CSS다

## 운영 목표 (시연 환경)

| 항목 | 목표 | 확인 |
|---|---|---|
| 동시 세션 | 5 | e2e 대본 5개 동시 실행(all_five×3, one_element, no_assistant) |
| 페르소나 응답 지연 | p95 8초 (LLM 타임아웃 30초) | messages.meta |
| 이벤트 시점 오차 | fired→done ±10초 (스케줄러 주기 5초 + 실행), 카드 메시지 전달은 fired 후 90초 안 | e2e summary 단언 1 |
| api 재시작 복구 | 90초 안에 WS 재연결·fired 이벤트 재실행 (재실행 조건 fired 후 60초) | restart 대본 |
| 세션당 비용 | $0.5 이하 | 토큰 메타 합산 |

## 저장소 구조

```
apps/web/                 Next.js
services/api/             FastAPI + LangGraph (app/routers, app/agent, app/scheduler.py)
services/business-mcp/
services/rag-mcp/
services/report-worker/
scenarios/                missions/<id>/(mission.yaml, cards.yaml, persona.yaml, documents/, prompts/), version.py, e2e/ 대본
scripts/                  seed.py, make_session.py, worktree.sh
tests/e2e/                run.py, records/
infra/                    docker-compose.yml, docker-compose.dev.yml(로컬 포트 바인딩), .env.example, db/schema.sql
docs/
```

## ISO/IEC 25010 대응

| 품질 특성 | 설계 반영 |
|---|---|
| 기능 적합성 | PRD 기능 ID(F-xx)별 완료 조건을 e2e 단언으로 검증 |
| 신뢰성 | 체크포인트 재개, 이벤트 상태(pending·fired·done)와 멱등 저장으로 재시작 시 누락·중복 없음, 큐 persistent·manual ack·재발행 재탐색·DLQ, LLM 폴백과 세션 실패 기준 |
| 성능 효율성 | 위 운영 목표. 응답당 도구 호출 3회, 호출당 입력 6k·출력 400 토큰, 검색 결과 3청크 |
| 보안성 | 역할 분리 JWT, 모든 조회에 company_id, 초대 토큰 해시 저장·72시간, 내부 API는 미공개 포트 + 시크릿, 권한 판단은 api만, 비밀값 env |
| 유지보수성 | 시나리오 데이터화, 서비스별 컨테이너, 계약 문서가 정본 |
| 이식성 | Docker Compose 한 번에 기동. 외부 의존은 OpenAI·LangSmith뿐 |
| 호환성 | MCP 표준 전송, REST·WebSocket 계약 문서화 |
| 사용성 | 오피스 시각·마감·남은 시간 상시 표시, 메인 영역 탭 전환과 새 메시지 배지, 새로고침 없는 도착, 진행 표시, 이어하기, 끊김 구간 표시 |
