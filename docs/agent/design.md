# 에이전트 설계 (api 안의 LangGraph 모듈)

## AgentRunner 인터페이스

api의 다른 부분은 이 인터페이스만 본다. M0 공용 기반에 `FakeAgentRunner`(고정 문장을 post_message)가 있어 api·web 트랙이 에이전트 없이 전체 흐름을 돌릴 수 있다.

```python
class AgentRunner(Protocol):
    async def run(self, session_id: UUID, stimulus: Stimulus, run_id: UUID) -> RunResult: ...
# Stimulus = {type: "message"|"event"|"end", message_id?, event_ids?: [UUID]}
#   event: 같은 due_at의 행 묶음(card order). run_id는 묶음의 대표(첫 행의 run_id, api가 모든 행에 같은 값을 기록)
# RunResult = {ok: bool, fallback_used: bool, error?: str}
```
세션별 asyncio.Lock으로 직렬 실행. Lock은 메모리이므로 api는 단일 프로세스로 운영한다(제약을 `docs/plan.md`에 기록). 실행 기록은 `agent_runs`(run_id, 자극, 상태, usage)에 api가 남기고, 120초 넘게 `started`인 run은 스케줄러가 같은 run_id로 다시 실행한다.

재실행 멱등 규칙(같은 run_id로 두 번 실행해도 결과가 한 벌):
- state의 `handled_stimuli`(message_id·event_id 집합)에 이미 있으면 route가 생성·전이를 건너뛰고 ok를 돌려준다(그래프 완료 후 done 기록 전에 중단된 경우).
- 그래프 안에서 post·write마다 `seq`를 1부터 순서대로 붙인다. 중단 후 재실행은 같은 순서를 밟으므로 같은 (run_id, seq)가 되고 api가 기존 행을 돌려준다.
- 관찰 창 경계는 `now`가 아니라 카드의 `due_at`이다(아래 observe). 재실행해도 같은 (element, window_start)가 된다.
- 카드 발행 지연: 이벤트는 스케줄러가 due_at에 `fired`로 표시하고(±10초 목표는 이 시각), 카드 메시지는 Lock을 기다린 뒤 나간다. 메시지 실행이 Lock을 오래 잡지 않도록 inject를 observe보다 먼저 한다. 카드 메시지는 fired 후 90초 안에 나가는 것을 목표로 한다.

## 세션 그래프

State (TypedDict): `session_id, phase, negotiate_round, division, scenario, current_element, window_start, stimulus, run_id, seq, handled_stimuli, recent_messages, summary, tool_calls_used, token_budget_left, last_error` (15필드)

phase: `kickoff → negotiate → work → review → submit → done`

### 자극별 전이표

| phase | 자극 | 노드 | 부수 효과 | 다음 phase |
|---|---|---|---|---|
| kickoff | event kickoff | kickoff | 팀장 브리프 post(team), 동료 인사 post(dm). division은 제안하지 않음 | negotiate 대기(phase 유지) |
| kickoff | event division | propose_division | 기본 분담안 post(dm), negotiate_round=0 | negotiate |
| kickoff | message | respond | 일반 응답(수신자 규칙) | kickoff |
| negotiate | message | negotiate | 분류 `{decision: accept∣modify∣other}`. other(일반 질문·잡담)는 respond로 답하고 round를 올리지 않음. modify면 조정안 post, round+1. accept 또는 round≥3이면 set_division·update_task·확정 메시지 | 확정 시 work |
| negotiate | event (요소 카드) | inject → observe | 미합의 상태면 마지막 제안안으로 **확정**하고 "일단 이대로 진행할게요" post 후 카드 실행 (PRD F-21) | work |
| negotiate | event review | review → observe | 요소 카드와 같은 규칙으로 확정 post 후 review 실행(존중만 선택했거나 분업에 답하지 않은 경우) | review |
| work | message | respond | 수신자 규칙으로 동료/팀장 결정. 도구 선택(허용 목록), 문서명 인용. 분류가 `redivide`(분담 재조정 제안)면 negotiate 1회: 최소 조건 안에서 set_division·update_task 후 안내 | work |
| work | event (요소 카드) | inject → observe | 카드 실행 → 직전 창(current_element, [이전 카드 due_at, 이 카드 due_at)) record_observation → current_element=카드 요소 | work |
| work | event review | review → observe | 확정 division에서 동료 담당 파트를 write_document_part, 공유 메시지 post. respect 행이 있으면 동료 담당 첫 파트에 정책 위반 삽입 → 직전 창 닫기, current_element=respect | review |
| review | message | respond | 수신자 규칙. 지원자가 동료 파트의 오류를 지적하거나 수정을 요청하면 동료가 인정하고 **자기 파트만** `write_document_part`로 고친 뒤 알림(허용 도구에 포함, 지원자 파트는 api 403) | review |
| review | event report_request | request_report → observe(흐름 카드도 열린 창을 닫음) | 팀장 보고 요청 post | submit |
| submit | message | respond / respond_report | dm은 동료 respond, team은 팀장 respond_report | submit |
| any | end | observe → close | 열린 창 닫기(window_end=ends_at 또는 submitted_at) → phase done | done |

**수신자 규칙**(respond 앞에서 결정적으로): dm 채널 → 동료. team 채널 → 팀장 호칭("팀장님", 팀장 이름)이 있거나 내용이 과제 범위·마감·보고·대상 변경이면 팀장, 그 외는 동료. 둘 다 답하지 않는다. 지원자가 10분 넘게 조용해도 먼저 말을 걸지 않는다(F-25는 MVP 제외). 페르소나가 먼저 말하는 경우는 카드 실행뿐이다.

respect는 `session_events`에 review와 같은 due_at의 별도 행으로 있다. 스케줄러는 같은 시각의 이벤트를 card order대로 한 run에서 처리하며(review 먼저), respect 행은 review 노드가 위반을 삽입한 뒤 done 처리한다. 발생 감지를 위해 **행마다 자기 event_id를 단 메시지를 최소 1건** 만든다. review 행: 동료 파트 공유 메시지(`event_id=review`). respect 행: 위반이 든 파트를 가리키는 동료의 추가 한 줄(예: "핵심 기능에 유료 멤버십 할인도 넣었어요", `event_id=respect`, 같은 run_id의 다음 seq). 디브리핑·발생률 검사는 이 행과 메시지를 본다.

### 노드

| 노드 | 역할 | Agentic 요소 |
|---|---|---|
| route | 전이표 조회 | 결정적 |
| kickoff, propose_division, request_report | 카드 brief로 문장 생성 후 post | 생성 |
| negotiate | 구조화 출력 `{decision: accept∣modify∣other, parts?}`. modify면 조정안 생성, other면 respond로 위임 | 분류 + 생성 |
| respond, respond_report | tool-calling 루프. 허용 도구만, 최대 3회, 결과 2k자 절단. 인용 시 문서 제목 포함 | **모델이 도구 선택** |
| observe | `observe/` 순수 함수로 metrics, LLM 레이블 분류(temperature 0). 창 안에 지원자 활동(메시지·문서 수정·문서 열람·어시스턴트 호출)이 하나도 없으면 LLM을 부르지 않고 `no_evidence`. 허용 레이블 외 출력은 `unclassified`, LLM 실패는 null. evidence는 창 안의 데이터만, 타입별 참조 `{type: message∣revision∣doc_view∣assistant_call, id}` → record_observation | 규칙 + 고정 레이블 분류 |
| inject | 카드 실행. system은 text 그대로 post(LLM 없음). colleague/manager는 brief로 생성. post는 event_id·run_id·seq 포함 | 생성 |
| review | 동료 파트 작성(write_document_part), 공유 post | 생성 |
| guard 앞 context | 페르소나별 컨텍스트 허용 목록(harness.md Context)으로 입력을 거른다: 미래 카드·관찰 레이블·어시스턴트 대화는 어떤 페르소나에도 넣지 않음 | 함수 |
| guard | 모든 생성 텍스트: 금지 패턴 치환, 600자 제한 | 함수 |

동료 담당 파트는 확정 division에서 `assignee ∈ {colleague}`인 파트다. `both`는 지원자가 쓰고 동료는 리뷰 코멘트만 한다. 위반 삽입 위치는 동료 담당 파트 중 번호가 가장 작은 것.

**분업 최소 조건**(PRD 6.2): 2번 파트는 지원자 담당, 4·5번 중 하나 이상은 동료 단독 담당이어야 한다. 이 조건은 `set_division`이 검증하고(api `PUT /division`도 422), negotiate가 조건을 어기는 요청을 받으면 수락하지 않고 "인터뷰 근거는 지원자님이, 사례나 지표는 제가 맡는 게 좋겠어요" 식으로 이유를 말하며 조건에 맞춘 조정안을 내고 round+1 한다. 그래서 모든 분업에서 책임감 카드(2번 자료 지연)와 존중 카드(동료 파트 위반)의 전제가 성립한다.

## 페르소나 행동 계약 (프롬프트 `scenarios/prompts/`의 근거)

| 항목 | 동료(이도현) | 팀장(한서윤) | 어시스턴트 |
|---|---|---|---|
| 먼저 말하는 때 | 카드 실행(인사, 분담안, 도움 요청, 파트 공유)뿐 | 카드 실행(브리프, 대상 변경, 보고 요청)뿐 | 없음 |
| 답장 | 인위적 지연 없음. 1~3문장, 600자 상한. 질문 하나에 답 하나 | 2~4문장. 결정은 분명히, 이유 한 줄 | 요청 형식에 맞게(요약·초안은 길어도 됨), 인용 문서명 필수 |
| 대행 범위 | 자기 파트와 both 파트의 협업. 지원자 단독 파트는 조언·예시 1~2문장까지, 대신 쓰지 않음("그 파트는 OO님 담당이라 제가 쓰진 않을게요, 대신 …") | 과제·일정 판단. 문서는 쓰지 않음 | 질문·요약·초안 생성. 지원자 문서에 직접 쓰지 않음(F-16). 회사 문서는 공개된 것만 |
| 진행 상황 질문 | 접근 방법과 진행 정도만("사례 3개 추리는 중이에요"). 완성본 공유는 리뷰 시점 | 일정 재확인 | — |
| both 파트 의견 요청 | 의견 2~3개를 짧게 | — | — |
| 업무 외 요청·사담 | 한 줄 받아주고 업무로 복귀 | 한 줄 받아주고 업무로 복귀 | "업무 관련 요청만 도울 수 있어요" |
| 평가 기준·연출 질문 | 공통 안내문(common_rules) | 공통 안내문 | 공통 안내문 |
| 추가 자료 요청(대상 변경 뒤 등) | "저도 그 자료는 없어요" + 가정 제안 | 고정 대응: 추가 자료는 없으니 가정을 명시하고 검증 계획을 적어 달라 | 공개 문서 범위 밖이면 없다고 답함 |
| 보는 기록 | 팀 채널 + 동료 DM, 보드, 문서 상태, 공개 문서 | 팀 채널, 보드, 문서 상태 | 자기 대화 + 공개 회사 문서. 팀 대화는 보지 않음 |

업무 중 재분업: 지원자가 분담 재조정을 제안하면(유연성 카드 뒤가 보통) 동료가 1회 받아들여 최소 조건 안에서 division·보드를 바꾼다. 그 이상은 "일정상 지금 더 바꾸긴 어렵겠어요"로 유지.

## 어시스턴트 그래프

`retrieve(search_documents top3) → answer(인용 포함) → guard`. thread `assistant:{session_id}`. 60회 초과는 api가 429로 막고 그래프는 호출되지 않는다. api가 request·response 메시지와 assistant_calls를 기록한다.

## observe (`app/agent/observe/`)

`compute_metrics(window, card, messages, revisions, views, assistant_calls) -> dict`, `classify(window, card, llm) -> (label|None, evidence: [{type, id}])`. 입력은 창 안의 데이터만. 카드별 픽스처로 단위 테스트. agent-session 트랙이 함께 구현한다.

창 경계: `window_start` = 직전 카드(흐름 카드 포함)의 due_at, `window_end` = 이 카드의 due_at. 마지막 창은 `ends_at` 또는 `submitted_at`까지. 모두 시나리오에서 결정되므로 재실행에 무관하다.

레이블 규칙: 카드의 `labels` 중 하나, 또는 `no_evidence`(창 안에 지원자 활동 없음, LLM 미호출), `unclassified`(LLM 출력이 허용 밖), null(LLM 실패). `ignore`·`silent`·`not_noticed`처럼 "하지 않음"을 뜻하는 레이블은 창 안에 지원자 활동이 있을 때만 나올 수 있다. 레이블이 있으면 evidence가 1개 이상이어야 하며(없으면 unclassified로 강등), `silent`·`apply_silently`의 evidence는 문서 revision이다. 리포트 문장 매핑은 worker-infra/design.md.

## 복구

`docs/common/harness.md` Recovery 행. 그래프는 `last_error`에 기록하고 `RunResult.fallback_used=True`를 돌려준다. 카운터와 세션 failed 전이는 api `SessionService`가 한다.

## 완료 기준
- M1 최소 흐름: 지원자 메시지 1개 → respond → rag 검색 → post_message → WS 노출 (FakeAgentRunner 교체)
- M2: 6분 세션 + 대본 3개로 카드 전부 정시, 분업 3회 거절 확정, 미합의 중 이벤트 도래 처리, api 재시작 후 fired 이벤트 재실행과 /state 이어하기, 허용 밖 도구 거부, 미공개 문서 질문에 "아직 공유되지 않은 자료" 답변, 강제 LLM 실패 3회에 세션 failed, LangSmith trace에 run_id
- 근거 정확성 픽스처: 질문별 기대 도구·허용 문서·인용 일치 검사 10건
