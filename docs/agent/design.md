# 에이전트 설계 (api 안의 LangGraph 모듈)

## AgentRunner 인터페이스

api의 다른 부분은 이 인터페이스만 본다. M0 공용 기반에 `FakeAgentRunner`(고정 문장을 post_message)가 있어 api·web 트랙이 에이전트 없이 전체 흐름을 돌릴 수 있다.

```python
class AgentRunner(Protocol):
    async def run(self, session_id: UUID, stimulus: Stimulus, run_id: UUID) -> RunResult: ...
# Stimulus = {type: "message"|"event"|"end", message_id?, event_id?}
# RunResult = {ok: bool, fallback_used: bool, error?: str}
```
세션별 asyncio.Lock으로 직렬 실행. Lock은 메모리이므로 api는 단일 프로세스로 운영한다(제약을 `docs/plan.md`에 기록).

## 세션 그래프

State (TypedDict): `session_id, phase, negotiate_round, division, scenario, current_element, window_start, stimulus, run_id, recent_messages, summary, tool_calls_used, token_budget_left, last_error`

phase: `kickoff → negotiate → work → review → submit → done`

### 자극별 전이표

| phase | 자극 | 노드 | 부수 효과 | 다음 phase |
|---|---|---|---|---|
| kickoff | event kickoff | kickoff | 팀장 브리프 post(team), 동료 인사 post(dm). division은 제안하지 않음 | negotiate 대기(phase 유지) |
| kickoff | event division | propose_division | 기본 분담안 post(dm), negotiate_round=0 | negotiate |
| kickoff | message | respond | 일반 응답 | kickoff |
| negotiate | message | negotiate | 수락/수정 분류. 수정이면 조정안 post, round+1. 수락 또는 round≥3이면 set_division·update_task·확정 메시지 | 확정 시 work |
| negotiate | event (요소 카드) | observe → inject | 미합의 상태면 마지막 제안안으로 **확정**하고 "일단 이대로 진행할게요" post 후 카드 실행 (PRD F-21) | work |
| negotiate | event review | observe → review | 요소 카드와 같은 규칙으로 확정 post 후 review 실행(존중만 선택했거나 분업에 답하지 않은 경우) | review |
| work | message | respond | 도구 선택(허용 목록), 문서명 인용 | work |
| work | event (요소 카드) | observe → inject | 열린 창 닫기(current_element가 있으면 record_observation), window_start=now, current_element=카드 요소 | work |
| work | event review | observe → review | 창 닫기 → 확정 division에서 동료 담당 파트를 write_document_part, 공유 메시지 post. respect 이벤트가 있으면 동료 담당 첫 파트에 정책 위반 삽입, current_element=respect, window_start=now | review |
| review | message | respond | | review |
| review | event report_request | observe(흐름 카드도 열린 창을 닫음) → request_report | 팀장 보고 요청 post | submit |
| submit | message | respond_report | 팀장이 보고에 답함 | submit |
| any | end | observe → close | 열린 창 닫기 → phase done | done |

respect는 `session_events`에 review와 같은 due_at의 별도 행으로 있다. 스케줄러는 같은 시각의 이벤트를 card order대로 한 run에서 처리하며(review 먼저), respect 행은 review 노드가 위반을 삽입한 뒤 done 처리한다. 발생 감지를 위해 **행마다 자기 event_id를 단 메시지를 최소 1건** 만든다. review 행: 동료 파트 공유 메시지(`event_id=review`). respect 행: 위반이 든 파트를 가리키는 동료의 추가 한 줄(예: "핵심 기능에 유료 멤버십 할인도 넣었어요", `event_id=respect`, 같은 run_id의 다음 seq). 디브리핑·발생률 검사는 이 행과 메시지를 본다.

### 노드

| 노드 | 역할 | Agentic 요소 |
|---|---|---|
| route | 전이표 조회 | 결정적 |
| kickoff, propose_division, request_report | 카드 brief로 문장 생성 후 post | 생성 |
| negotiate | 구조화 출력 `{decision: accept∣modify, parts?}`. modify면 조정안 생성 | 분류 + 생성 |
| respond, respond_report | tool-calling 루프. 허용 도구만, 최대 3회, 결과 2k자 절단. 인용 시 문서 제목 포함 | **모델이 도구 선택** |
| observe | `observe/` 순수 함수로 metrics, LLM 레이블 분류(temperature 0, 허용 레이블 외는 unclassified), evidence는 창 안의 지원자 메시지 id만 → record_observation | 규칙 + 고정 레이블 분류 |
| inject | 카드 실행. system은 text 그대로 post(LLM 없음). colleague/manager는 brief로 생성. post는 event_id·run_id·seq 포함 | 생성 |
| review | 동료 파트 작성(write_document_part), 공유 post | 생성 |
| guard | 모든 생성 텍스트: 금지 패턴 치환, 600자 제한 | 함수 |

동료 담당 파트는 확정 division에서 `assignee ∈ {colleague}`인 파트다. `both`는 지원자가 쓰고 동료는 리뷰 코멘트만 한다. 위반 삽입 위치는 동료 담당 파트 중 번호가 가장 작은 것.

**분업 최소 조건**(PRD 6.2): 2번 파트는 지원자 담당, 4·5번 중 하나 이상은 동료 단독 담당이어야 한다. 이 조건은 `set_division`이 검증하고(api `PUT /division`도 422), negotiate가 조건을 어기는 요청을 받으면 수락하지 않고 "인터뷰 근거는 지원자님이, 사례나 지표는 제가 맡는 게 좋겠어요" 식으로 이유를 말하며 조건에 맞춘 조정안을 내고 round+1 한다. 그래서 모든 분업에서 책임감 카드(2번 자료 지연)와 존중 카드(동료 파트 위반)의 전제가 성립한다.

## 어시스턴트 그래프

`retrieve(search_documents top3) → answer(인용 포함) → guard`. thread `assistant:{session_id}`. 60회 초과는 api가 429로 막고 그래프는 호출되지 않는다. api가 request·response 메시지와 assistant_calls를 기록한다.

## observe (`app/agent/observe/`)

`compute_metrics(window, card, revisions, views, assistant_calls) -> dict`, `classify(window, card, llm) -> (label|None, evidence_ids)`. 입력은 창 안의 데이터만. 카드별 픽스처로 단위 테스트. agent-session 트랙이 함께 구현한다.

## 복구

`docs/common/harness.md` Recovery 행. 그래프는 `last_error`에 기록하고 `RunResult.fallback_used=True`를 돌려준다. 카운터와 세션 failed 전이는 api `SessionService`가 한다.

## 완료 기준
- M1 최소 흐름: 지원자 메시지 1개 → respond → rag 검색 → post_message → WS 노출 (FakeAgentRunner 교체)
- M2: 6분 세션 + 대본 3개로 카드 전부 정시, 분업 3회 거절 확정, 미합의 중 이벤트 도래 처리, api 재시작 후 fired 이벤트 재실행과 /state 이어하기, 허용 밖 도구 거부, 미공개 문서 질문에 "아직 공유되지 않은 자료" 답변, 강제 LLM 실패 3회에 세션 failed, LangSmith trace에 run_id
- 근거 정확성 픽스처: 질문별 기대 도구·허용 문서·인용 일치 검사 10건
