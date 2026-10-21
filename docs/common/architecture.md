# 아키텍처

2026-10-21 토론형 전환(`docs/handoff/briefs/brief-debate-pivot.md`) 기준이다. 과제는 **지원자 + AI 동료 3명이 한 토론방에서 키워드 → 문제 상황 → 해결책을 합의하고, 지원자가 최종 기획안을 써서 제출**하는 60분 세션이다. 서비스 목적(행동 관찰로 인성을 보고, AI는 기록하고 사람이 판단)은 그대로다. 브리프 "리뷰 반영 결정"(R1~R7) 기준: 모든 세션이 5요소·카드 6장·페르소나 3명(고집형 강한결·소극형 윤하람·비판형 서지안) 고정이고 세션 길이는 60분 또는 데모 15분이다.

MVP 원칙: **평가 항목이 요구하는 조각만 분리하고 나머지는 합친다.** 분리하는 것은 MCP 서버 3개, 큐와 워커, 프론트뿐이다. 토론 그래프·어시스턴트 그래프·의도 분류는 api 프로세스 안의 모듈이다.

평가표 차원(BARS)·카드·페르소나·요소의 구체 목록과 규칙은 `scenario-model.md`·`rubric.md`가 정본이다. 이 문서와 `contracts.md`·`data-model.md`는 그 값을 **문자열 id로 받는 구조**만 정한다.

## 구성 요소

| 구성 요소 | 책임 | 기술 |
|---|---|---|
| web | 기업 관리자 화면(채용 건·초대·리포트·조정), 지원자 토론 화면(가운데 토론방, 우측 탭 합의·자료·AI 어시스턴트·기획안, 상단 단계 진행바·남은 시간) | Next.js App Router, Tailwind. `/admin/*`, `/s/[token]` |
| api | 인증, 화면 REST, WebSocket(세션별 단일 송신 큐·`seq`), DB 쓰기, 세션 시계(스케줄러: 단계 마감 시 **시간 초과 직접 채우기**·침묵 초대·카드 예정 시각·세션 만료), 세션 메일박스, 카탈로그 아바타 정적 서빙(`/assets/missions/<mission_id>/avatars/`), 의도 분류, 토론 그래프, 어시스턴트 그래프, 금지 문구 검사 | FastAPI + LangGraph, 한 프로세스 |
| 토론 그래프 (api 모듈) | **턴 매니저**(결정적 노드 + LLM 화자 선택) + **페르소나 에이전트 3**(자리 `p1`·`p2`·`p3`, 각자 입장·기억·도구 허용 목록) | LangGraph, thread `debate:{session_id}` |
| 어시스턴트 그래프 (api 모듈) | 지원자 전용 검색·요약. tool-calling 루프(`search_materials`·`get_material`, 요청당 최대 3회, 인용 포함)로 모델이 도구를 고른다. 열린 자료만 | LangGraph, thread `assistant:{session_id}` |
| debate-mcp (손) | 토론 상태 조회·변경: 상태·대화 조회, 메시지 게시, 안 제안, 입장 기록, 합의 칸 채우기, 기획안 초안 조회. business-mcp를 재정의(이름·도구 교체) | FastMCP, Streamable HTTP `:9101/mcp` |
| rag-mcp (눈) | 확정된 키워드의 참고 자료만 검색·조회(채용 건 `catalog_version`의 청크·원문). 키워드 확정 전에는 차단 | FastMCP, Streamable HTTP `:9102/mcp`, BGE-M3, pgvector |
| assessment-mcp (기록자, 신규) | 카드 전달 기록, 평가표(BARS 척도) 조회, 평가 입력 묶음(세션 기록 전체) 조회, 근거 앞뒤 맥락 조회, 아이디어 최초 제안자 조회, 평가 결과 저장 | FastMCP, Streamable HTTP `:9103/mcp` |
| report-worker | 세션 종료 후 큐 작업: 세션 기록 수집 → 사실 지표 → 평가 에이전트(BARS 차원별 수준·근거) → 리포트 초안 → 담당자 승인 대기 → 확정. 재시도, DLQ | Python, RabbitMQ consumer, LangGraph thread `report:{session_id}:{eval_round}` |
| infra | 컨테이너, 큐, DB, 관측 | Docker Compose, RabbitMQ, PostgreSQL 16 + pgvector, LangSmith(env) |

MCP 서버 세 개의 도구 함수는 모두 `async def`다(FastMCP는 동기 도구를 워커 스레드에서 실행한다).

살린 기반: 인증(관리자 JWT·초대 링크·세션 JWT), WS 허브, 큐·report-worker 골격, rag-mcp 색인·검색, 채팅 UI·탭·Markdown 뷰어. 삭제: 보드·분업·파트 문서·팀장·시각 예약 이벤트 카드 코드(`session_events` 행 예약 방식. 시각 기반 카드는 시나리오 `offset_min`과 `card_due` 자극으로 대체).

## 원칙

1. **DB 쓰기는 api만 한다.** MCP 3개와 워커는 api의 `/internal/*`(별도 포트 8001, 미공개)을 부른다. 예외는 LangGraph checkpointer 테이블(api는 `debate:`·`assistant:` thread, 워커는 `report:` thread만), rag-mcp의 `material_chunks`, `scripts/seed.py`의 `materials`(자료 원문 버전별 시드).
2. **시간의 주인은 api다.** 세션 시작 시각과 단계 마감 시각을 DB에 두고, 5초마다 도는 스케줄러가 단계 마감(직접 시간 초과 채우기)·침묵 초대·카드 예정 시각(자극 enqueue)·세션 만료(자동 제출)를 처리한다. 접속이 끊겨도 시계는 흐른다. 시간 로직은 시계를 주입받아 가짜 시계로 단위 테스트한다.
3. **에이전트는 자극에 반응하는 함수다.** 자극은 `message`(지원자 메시지), `phase_started`(단계 시작), `idle`(지원자 침묵만), `card_due`(시각 기반 카드 예정 시각, card_id 포함) 네 가지(정본 `contracts.md` "그래프 자극"). 단계 마감은 그래프가 아니라 api가 결정적으로 직접 채운다. 자극마다 토론 그래프를 한 번 실행하고 체크포인트에 남긴다. 세션 하나 = thread 하나 = **메일박스 하나**(asyncio Task 1개가 자극 큐를 직렬 소비, 락 없음). 지원자 메시지 저장과 단계 전환이 `sessions.generation`을 올리고, 그래프는 게시 직전 generation이 바뀌었으면 남은 화자를 버린다. api는 단일 프로세스로 운영한다.
4. **시나리오는 데이터다.** 채용 건 생성 때 고정 페르소나 3자리·키워드 후보·페르소나별 단계 고정 안·카드 6장·평가표·프롬프트·자료 목록을 조립해 `positions.scenario`에 복사·고정한다(같은 채용 건 = 같은 시나리오, 요소 선택 없음). 코드는 해석만 한다. 조립 규칙은 `scenario-model.md`.
5. **결정은 결정적 코드가, 말투는 LLM이.** 누가 어떤 안을 처음 밀지, 합의 여부, 시간 초과 시 고를 안, 칸 채우기 허용, 문제 상황 기준안 잠금, 지원자 확정 값의 안 연결은 규칙으로 정한다. LLM은 의도 분류, 화자 선택 보조(규칙 결과 0명인 `message` 자극만), 발언 문장만 만든다.
6. **평가 정보는 페르소나에게 닿지 않는다.** 페르소나 respond 노드에는 assessment-mcp 클라이언트를 만들지 않고 허용 목록에도 넣지 않는다. assessment-mcp는 턴 매니저의 결정적 노드와 report-worker만 쓴다.

## 세션 흐름 한눈에

```
입장·동의·시작 ─▶ keyword(10) ─확정─▶ problem(18) ─확정─▶ solution(18) ─확정─▶ proposal(14) ─제출─▶ completed ─큐─▶ 리포트
                  └ 마감이면 api가 가장 많이 모인 의견으로 채우고 넘어감(resolution=timeout) ┘        └ 세션 만료면 현재 초안 자동 제출
```

- 단계 예산(분)은 60분 기준 10·18·18·14이고 `session_minutes`에 비례한다(데모·e2e 15분 = 2.5·4.5·4.5·3.5, 카드·유휴 오프셋은 최소 20초).
- **단계 마감 시각은 누적 고정**이다: `deadline_k = started_at + (예산 1..k의 합) × session_minutes / 60`. 일찍 확정하면 다음 단계가 그만큼 길어진다(남은 시간 이월). 마지막 proposal 마감 = `ends_at`.
- 오피스 시계: `오피스 시각 = 09:00 + t_min × 60 / session_minutes`(60분·15분 모두 09:00~10:00). 지원자 화면은 남은 시간 중심이고 오피스 시각은 메시지 타임스탬프에만 쓴다.

## 요청 흐름

### 지원자 메시지

1. web → api WS `message.send{client_msg_id, content}`
2. api(메일박스 밖): 단계 확인(in_progress 아니면 오류) → 민감정보 마스킹 → 저장(client_msg_id 멱등, `phase`, `origin` = 이 단계에서 지원자를 부른 초대 메시지 뒤 첫 발언이면 `invited`, 아니면 `spontaneous`)과 같은 트랜잭션에서 `sessions.generation += 1` → 커밋 직후(의도 분류 전) `message.ack{run_id}`·`message.new` 송신 큐 → `agent_runs` 행 `queued` → 세션 메일박스에 `message` 자극 enqueue(자극의 `generation`은 이 저장이 올린 값, `phase`는 `messages.phase`). 큐 밖 처리는 여기까지다
3. api(메일박스 안, 자극을 꺼낸 순서대로): **실시간 의도 분류**(작은 모델, 입력 단계는 저장된 `messages.phase`이고 그 단계 카탈로그 안 전체 포함, 타임아웃 10초, 재시도 없음) → `message_intents` 저장 → 토론 상태 누적: 제안이면 안 행(시나리오 키면 그 키 행, 아니면 자유 안, 최초 제안자 = candidate), confidence high인 제안·동의·반대면 `stances` 행(참여자당 현재 지지 하나, 다른 안 지지는 대체, 같은 안 반대는 철회). 실패하면 `intent=other`(fallback=true)로 두고 진행. 안·입장도 `messages.phase` 단계에 저장한다. **자극이 낡았어도 이 단계는 반드시 수행**한다
4. 자극이 낡았으면(단계가 현재 단계와 다름, 또는 generation이 현재 값보다 작아 뒤의 메시지 자극이 응답을 맡음) 턴 선택·페르소나 발언 생성 없이 `skipped`. 아니면 토론 그래프 실행:
   - `load`(결정적): DebateState(합의·시간 초과 후보, `card_progress`, `cost_left` 포함)와 최근 대화를 읽어 페르소나용으로 걸러 컨텍스트에 미리 넣는다
   - `turn`(턴 매니저): 규칙(지원자가 부른 사람, 미전달 카드 화자, 침묵 초대, 합의 성립 → `fill = {option_id, seat}`)을 먼저 적용하고, 규칙 결과가 0명이고 자극이 `message`일 때만 LLM이 **화자 0~2명**과 목적을 정한다
   - 화자마다 `typing` 시작 → `respond`(페르소나 에이전트 LLM. 자기 자리의 성향·입장 계획·카드 brief·기억, 허용 도구만) → `guard`(금지 문구 검사, 걸리면 재생성 1회 → 안전 문구) → `stance_check`(입장 계획 밖이면 응답 전체 재생성 1회 → `stance_fallback` 고정 문구) → `wait_typing`(지원자 입력 중이면 최대 10초, 그래도 입력 중이면 미게시·자극 재큐·`deferred`) → generation 확인(바뀌었으면 남은 화자 버림) → `apply`(결정적): debate-mcp `post_message{expected_generation, card_ids?}`(한 발언이 여러 카드를 전달할 수 있음), 안을 처음 밀면 `propose_option`, 입장을 표현하면 `set_stance`, 카드의 첫 발언이면 카드마다 assessment-mcp `record_observation` → `typing` 종료. 둘째 화자는 1~3초 간격
   - `fill`(결정적): `apply`가 이번 발언의 입장을 저장한 **뒤** 지지를 다시 읽어 판정한다. 지원자 포함 3/4 지지 안이 있고 칸이 empty면 `announce_fill` 분기: 지지자 중 우선순위 자리와 고정 문장 "그럼 X로 정리할게요"를 정해 `fill_slot{option_id, seat, content, run_id}`를 한 번 부른다. 일반 발언 루프(respond → apply)와 LLM을 거치지 않는다. api가 한 트랜잭션으로 합의 재검사 → 칸 confirmed → 공지 메시지 저장(seq 5, `meta.kind=consensus_fill`) → generation +1을 하고 WS `message.new`·`slot.confirmed`를 보낸다. 409면 아무것도 저장하지 않고 끝낸다
5. debate-mcp → api `/internal/*` → 저장(멱등) → 세션 송신 큐 → WS(`seq` 붙임)

토큰 스트리밍은 없다(완성 문장 한 번에 게시, 금지 문구 검사와 충돌하지 않게). 비용이 하드 상한에 닿으면(`cost_left ≤ 0`, `services/budget.py`) 페르소나는 LLM 없이 고정 안전 문구만 게시한다.

경계: DB 커밋은 2·3·5. 외부 호출은 3·4(OpenAI, MCP)이고 모두 메일박스 안이다. 재시도는 LLM 2회(의도 분류는 0회), MCP upstream 1회. 페르소나 발언이 실패하면 그 발언은 생략하고 `llm_failures+1`(연속 3회면 세션 failed).

### 단계 전환과 타이머

| 사건 | 처리 |
|---|---|
| 지원자 확정 | `POST /sessions/{id}/slots/{phase}/confirm` → api가 칸을 `confirmed`(filled_by=candidate, resolution=consensus, 그 시점 지지 현황 스냅샷)로 바꾸고 다음 단계로 전환. 키워드는 버튼의 후보 키, 문제·해결책은 옵션 키·정규화 라벨 일치로만 안에 연결(LLM 없음) |
| AI 합의 채우기 | 턴 매니저 `fill`의 `announce_fill` 분기 → `fill_slot{option_id, seat, content, run_id}`. api가 한 트랜잭션에서 `consensus.judge`(지원자 포함 3/4 지지, 대기 시간 없음)를 다시 검사하고 아니면 409 `no_consensus`(AI는 합의 전에 칸을 채울 수 없다, 아무것도 저장 안 함). 성공하면 칸 확정·공지 메시지(seq 5)·전환이 함께 커밋되므로 공지가 빠진 확정은 없다. 같은 run_id 재호출은 기존 결과 |
| 단계 마감 | 스케줄러가 `now ≥ phase_deadline_at`이고 칸이 empty이면 **api `services/timeout.py`가 직접**: 시간 초과 선택 규칙으로 안을 고르고 우선순위 자리 이름으로 시나리오 고정 문장("시간이 다 돼서 대화에서 가장 많이 모인 의견인 X로 할게요")을 저장, 칸 `confirmed{resolution: timeout, filled_by: 그 자리}` → 전환. 그래프·LLM·MCP를 거치지 않는다 |
| 전환 공통 | api `SessionService.advance_phase`: `phase`·`phase_started_at`·`phase_deadline_at` 갱신, `generation += 1`, 시스템 안내 메시지("지금 할 일"과 남은 시간, 시나리오 고정 문구) 저장, WS `slot.confirmed`·`phase.changed`·`timer`. keyword 확정이면 그 키워드 자료를 열고 WS `materials.opened`. proposal 시작이면 기획안 초안의 빈 칸(키워드·문제 상황·해결책)을 확정 칸 값으로 채운다. 이어서 `phase_started`를 메일박스에 넣기만 한다(기획안 단계 `phase_started` 실행이 `honesty_credit` 관찰을 남긴다) |
| 마감 임박 | 단계 마감 `L/30` 전(60분 기준 2분, 압축 비율)에 시스템 안내 메시지 1건. 시점은 시나리오 데이터 |
| 침묵 초대 | 토론 단계에서 침묵 초대 조건(`scenario-model.md` 3.1)이 참이고 그 단계 `invite_delivered`가 false면 스케줄러가 `idle`을 넣는다(같은 단계 idle이 큐·실행 중이면 안 넣음, 지원자 입력 중이면 다음 틱). 초대 메시지(`is_invite`)가 실제 게시돼야 `invite_delivered_phases`에 들어가고, 안 됐으면 다음 틱에 다시 넣는다. 묻는 자리는 시나리오의 `silence_inviter`(비판형) |
| 카드 예정 시각 | 카드의 `offset_min`(단계 시작 기준, 최소 20초)에 도달했고 `session_cards`상 아직 delivered가 아니면 `card_due{card_id}`. 첫 처리 때 `session_cards` 행을 만들고 문제 상황 카드는 기준안을 잠근다(`locked_option_id`). 담당 화자가 게시할 때마다 `card_ids`의 카드마다 `delivered_seats`가 늘고, 남은 화자는 다음 run이 이어서 말한다. 전원 delivered 전까지 `card_due`는 새 uuid4 run_id로 다시 들어간다 |
| 세션 만료 | `ends_at` 도달 → 현재 기획안 초안으로 자동 제출(아래) |

### 기획안 작성과 제출

1. 지원자가 우측 기획안 탭에 혼자 쓴다(`PUT /sessions/{id}/proposal`, 디바운스 저장. 진행 중 언제든 저장 가능, 제출은 proposal 단계에서만). AI 동료는 채팅으로만 기여한다(물어보면 내용 제공, 요청하면 debate-mcp `get_draft`로 초안을 읽고 의견).
2. 제출(`POST /sessions/{id}/proposal/submit`) 또는 `ends_at` 도달 → `SessionService.submit(reason)`: 한 트랜잭션에서 초안을 제출본으로 고정(`proposals.submitted`, 자동 제출이면 `auto_submitted=true`) → `status=completed`·`phase=completed`·`completed_at`·`ended_at`(커밋) → WS `session.ended{submitted∣timeout}`. 메일박스의 남은 자극은 상태 검사로 `skipped`. 중간 상태는 없다.
3. api가 RabbitMQ `report.generate`에 `{session_id, attempt, eval_round}` 발행(persistent, publisher confirm 뒤 `report_enqueued_at` 기록). 비어 있으면 스케줄러가 60초마다 재발행.

### 리포트 (report-worker)

그래프 `collect → aggregate → evaluate → draft → interrupt → finalize`.

| 노드 | 하는 일 | 도구 |
|---|---|---|
| collect | 척도와 평가 입력 묶음 수집: 세션 대화 전체·칸 기록·기획안 제출본·카드 관찰 observations(창·전달 여부 포함)·사실 지표·Contributions | assessment-mcp `get_rubric`·`get_session_record`·`get_contributions` |
| aggregate | 사실 지표 정리, 카드 창 연결, `contribution_check`(안별 실제 최초 제안자 / 기획안에 적힌 기여자) 구성. 결정적 코드, LLM 없음 | — |
| evaluate | **평가 에이전트**: 요소마다 별도 LLM 호출(`MODEL_EVALUATOR`, temperature 0~0.2, 다른 요소 결과는 입력 안 함)로 세션 전체를 읽고 차원마다 `{level 1~5 ∣ null + no_record_reason, evidence_refs, rationale, confidence}`와 요소 summary를 낸다. 검증 경계(`contracts.md` EvaluationSave): 워커가 형식·근거 개수·금지어를 보고 실패하면 **그 요소를 1회** 다시 요청 → 그래도 실패한 차원은 `evaluate_failed`. 확신도 상한 위반은 거부하지 않고 깎는다(clamp). 요소 level은 워커가 차원 평균 반올림(.5 올림)으로 계산. LLM 전송·타임아웃 실패는 저장하지 않고 큐 재시도. api는 저장 전 형식·세션 소속만 검증하고 `evaluation_runs`(prompt_versions·elements)와 `evaluations`를 한 트랜잭션으로 저장. run_id = `uuid5(session_id, "evaluate:"+eval_round)`이고 같은 run_id가 이미 있으면 LLM을 부르지 않고 `GET /evaluations`(요소 요약 포함)로 재사용 | assessment-mcp `save_evaluation`, 내부 `GET /evaluations` |
| draft | 근거마다 원문·시각·앞뒤 맥락(`get_transcript_span` 앞 5·뒤 3, 표시용)을 붙여 Report(`elements`·`dimensions`·`facts`·`contribution_check`·`seats`·`slots`·`cards`·`debrief`, 총점 없음) 조립. 카드 장면 `cards[].scene`은 카드의 고정 문장 `report_template` 그대로(LLM 없음) → 내부 `report/draft` → `report_ready` → ack | assessment-mcp `get_transcript_span`, 내부 REST |
| interrupt → finalize | 담당자 검토 완료(차원 단위 조정·메모, `reviewer_name`) → `report.approve` → 같은 thread 재개 → **승인된 draft content를 그대로** `report/final`(해시 동일, 조정은 조회 때 병합) → `reviewed` | 내부 REST |

실패는 attempt+1 재발행(백오프 5·15·45초), 3회면 `report.dlq` → `report_failed` → `status=failed`(failed_stage=report). 담당자의 "리포트 다시 생성"은 completed로 되돌리고 다시 발행한다. 최신 평가 실행에 `evaluate_failed`가 없으면 같은 run_id를 재사용하고, 있으면 `eval_round`+1로 새 run_id로 다시 평가한다. 그래프 thread는 `report:{session_id}:{eval_round}`라 새 회차는 이전 interrupt 체크포인트의 draft를 재사용하지 않고 처음부터 실행하며, 같은 회차의 큐 재시도만 체크포인트에서 이어 간다. 리포트는 **담당자가 평가할 때 보는 참고 자료**다. AI 평가 에이전트가 공개된 척도로 근거를 들어 수준을 판단하고 담당자가 그것을 참고해 최종 평가한다. 합격·불합격·순위·총점은 만들지 않는다.

## 권한 경계

| 주체 | debate-mcp | rag-mcp | assessment-mcp | 비고 |
|---|---|---|---|---|
| 턴 매니저 결정적 노드(load·apply·fill) | 전부 | — | `record_observation` | 코드가 직접 호출 |
| 턴 매니저 LLM(turn) | — | — | — | 도구 없음. 주입된 상태만 본다 |
| 페르소나 respond | 조회 2개(`get_transcript`·`get_draft`, `get_debate_state`는 바인딩하지 않고 load가 걸러 주입) | `search_materials`·`get_material` | **불가** | 변경은 결정적 노드만. 평가 기준을 보고 행동을 맞추지 못하게 |
| 어시스턴트 | — | `search_materials`·`get_material` | — | 모델 tool-calling 루프, 요청당 최대 3회 |
| report-worker | — | — | `get_rubric`·`get_session_record`·`get_transcript_span`·`get_contributions`·`save_evaluation` | 코드가 직접 호출, 평가 에이전트 LLM에는 도구 없음(입력 묶음 주입). 리포트 저장은 내부 REST |

- session_id는 그래프가 주입하고 모델이 바꿀 수 없다.
- assessment-mcp는 `X-Assessment-Token` 헤더(env `ASSESSMENT_MCP_TOKEN`)가 있어야 응답한다. 토큰은 api의 결정적 노드 모듈과 워커에만 주고 페르소나 노드의 MCP 클라이언트 설정에는 넣지 않는다(허용 목록과 이중 차단).
- 페르소나 컨텍스트에 넣지 않는 것: 평가 척도·평가 결과·관찰·카드 이름·요소 이름·`card_progress`·`cost_left`, 다른 자리의 성향 이름, 아직 오지 않은 카드, 어시스턴트 대화, 열리지 않은 자료, 지원자의 기획안 초안(요청받아 `get_draft`를 부른 경우 제외).
- 권한·상태 판단(단계, 합의, 마감, 자료 잠금)은 api가 최종 판단한다. MCP는 전달만 한다.

## Harness 위치

상세 수치는 `harness.md`. 토론형에서 추가된 규칙과 위치만 적는다.

| 요소 | 위치 | 토론형 규칙 |
|---|---|---|
| Instructions | `positions.scenario`에 고정된 자리별 프롬프트·공통 규칙·금지 문구 패턴 | 기능 설명만 하고 평가 대상 행동을 유도하지 않음, 수준·점수·합격·연출 언급 금지, 지원자 대신 결론·평가 발언 금지 |
| Tools | 토론 그래프 노드별 허용 목록(위 표) | 페르소나는 assessment 접근 불가 |
| Context | `load`가 만든 자리별 컨텍스트 | 걸러 낸 DebateState를 미리 주입(조회 도구 왕복 줄임): 자기 입장 계획, 지지 현황, 최근 대화, 카드 brief, 열린 자료 청크 |
| State·Memory | PostgresSaver `debate:{id}`·`assistant:{id}`·`report:{id}:{eval_round}` | 자리별 기억(밀었던 안, 지원자에게 한 말)은 그래프 State |
| Agent Loop | 세션 메일박스(자극 4종 직렬 소비), 턴 매니저: 자극당 화자 0~2명(턴 LLM은 규칙 0명인 `message`만), 응답당 도구 3회, recursion_limit 20 | 침묵 초대 단계당 1회(실제 게시 기준), generation이 바뀌면 남은 화자 버림, 입력 중 10초 대기 뒤 재큐 |
| Guardrails | `guard`·`stance_check` 노드(코드에서 무조건 실행), api 합의 검사 | 금지 문구 재생성 1회 → 안전 문구. 계획 밖 입장 → 전체 재생성 1회 → `stance_fallback`. AI는 합의 전에 칸을 못 채움(409 `no_consensus`), 시간 초과는 api만 채움, 비용 하드 상한 $2 넘으면 고정 문구만 |
| Recovery | LLM 래퍼(30초, 재시도 2회), 의도 분류 실패 → other, 평가 검증 실패 요소 1회 재요청 → `evaluate_failed`, 전송 실패 → 큐 재시도·DLQ, 메일박스 재시작 복구(`agent_runs` queued·started 재큐, 200초 초과 재실행), WS seq 빠짐 → `/state` | |
| Observability | LangSmith trace, `agent_runs.usage`(`cost_usd` 포함)·`agent_runs.decision`(턴 매니저 결정), `messages.meta`(`stance_check`), `sessions.debate_cost_usd`(상한 판단)·`sessions.cost_usd`(전체 관측), `reports.usage`, `evaluation_runs.prompt_versions` | |

역할별 모델 env: `MODEL_PERSONA`, `MODEL_TURN`, `MODEL_INTENT`, `MODEL_ASSISTANT`, `MODEL_EVALUATOR`(평가 에이전트). 비어 있으면 `OPENAI_MODEL`. 키 선택 규칙은 공용 LLM 래퍼 한 곳.

MCP 접속 env: `DEBATE_MCP_URL`(`http://debate-mcp:9101/mcp`), `RAG_MCP_URL`(`http://rag-mcp:9102/mcp`), `ASSESSMENT_MCP_URL`(`http://assessment-mcp:9103/mcp`). 정본은 `contracts.md` "MCP 도구", 전체 env 목록은 `worker-infra/design.md`.

## 운영 목표 (시연 환경)

| 항목 | 목표 | 확인 |
|---|---|---|
| 동시 세션 | 5 | P2 동시 실행 확인 |
| 의도 분류 지연 | p95 3초 (타임아웃 10초) | message_intents.latency_ms |
| 페르소나 응답 지연 | 지원자 메시지 → 첫 페르소나 게시 p95 8초 (LLM 타임아웃 30초) | agent_runs, messages.meta |
| 단계 마감 처리 | 마감 → `phase.changed` 15초 안 (스케줄러 5초 + api 직접 채우기) | 가짜 시계 단위 테스트, e2e summary |
| api 재시작 복구 | 90초 안에 WS 재연결, 미처리 마감·제출 재처리 | restart 대본 |
| 세션당 비용 | 목표 $0.5(관측), 하드 상한 $2(토론 비용 기준, 페르소나 고정 문구로 전환) | `sessions.cost_usd` = agent_runs.usage + reports.usage의 `cost_usd`(관측). 상한은 `sessions.debate_cost_usd`(리포트 제외) |

## 저장소 구조

```
apps/web/                 Next.js
services/api/             FastAPI + LangGraph (app/routers, app/agent/{debate,assistant,intent,guard,llm,mcp_client}, app/mailbox.py, app/scheduler.py, app/services/{timeout,budget}.py)
services/debate-mcp/      (business-mcp 이름 변경)
services/rag-mcp/
services/assessment-mcp/  (신규)
services/report-worker/
scenarios/                시나리오 카탈로그(구조는 scenario-model.md), version.py, e2e/ 대본
scripts/                  seed.py, make_session.py, purge.py
tests/e2e/
infra/                    docker-compose.yml, docker-compose.dev.yml, .env.example, db/schema.sql
docs/
```

## ISO/IEC 25010 대응

| 품질 특성 | 설계 반영 |
|---|---|
| 기능 적합성 | PRD 기능 ID별 완료 조건을 e2e 단언으로 검증 |
| 신뢰성 | 체크포인트 재개, 멱등 저장, 세션 메일박스와 generation, api 직접 시간 초과 채우기, 큐 persistent·manual ack·재발행·DLQ, 의도 분류 실패 시 other, WS seq 재동기화 |
| 성능 효율성 | 위 운영 목표. 자극당 화자 2명, 응답당 도구 3회, 검색 결과 3청크 |
| 보안성 | 역할 분리 JWT, 모든 관리자 조회에 company_id, 초대 토큰 해시·72시간, 내부 API 미공개 포트 + 시크릿, assessment-mcp 별도 토큰, 비밀값 env |
| 유지보수성 | 시나리오 데이터화, 서비스별 컨테이너, 계약 문서가 정본 |
| 이식성 | Docker Compose 한 번에 기동. 외부 의존은 OpenAI·LangSmith뿐 |
| 호환성 | MCP 표준 전송, REST·WebSocket 계약 문서화 |
| 사용성 | 단계 진행바·남은 시간 상시 표시, 입력 중 표시, 새로고침 없는 도착, 이어하기, 끊김 구간 표시 |
