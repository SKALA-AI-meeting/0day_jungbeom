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

State (TypedDict): `session_id, phase, negotiate_round, division, scenario, current_element, window_start, stimulus, run_id, seq, handled_stimuli, recent_messages, summary, work_notes, tool_calls_used, token_budget_left, last_error` (16필드)

`work_notes`(동료의 작업 기억, 요약으로 접히지 않음):
```
{parts: [4, 5],                                   # 확정 division에서 동료 담당
 instructions: [{t_min: 11, text: "사례는 재참여 기능 있는 서비스 위주로", source_message_id}],   # 리드 지시 누적
 agreements: ["3번은 같이, 초안은 OO님이 먼저"],
 progress: {4: "사례 3개 추림", 5: "지표 초안 중"},   # 동료가 말한 진행 상태. 말한 것만 기록
 draft_written: false, final_written: false}
```
- negotiate·respond는 구조화 출력에 `instruction?: str`를 포함한다. 지원자 메시지가 동료에게 하는 지시·요청이면 채워지고 `work_notes.instructions`에 추가된다(재지시 포함).
- 진행 상황 질문에는 `progress`만 근거로 답하고, 답한 내용을 다시 `progress`에 기록한다(두 번 물어도 같은 답).
- 중간 초안(texture `midpoint_draft`)과 리뷰 완성본은 `parts`·`instructions`·`agreements` 전부와 회사 문서 검색 결과를 입력으로 생성한다. 지시가 반영되지 않은 파트는 생성 실패로 보고 1회 재생성한다(검사: 각 instruction의 핵심어가 본문에 있는지, 규칙 함수).

phase: `kickoff → negotiate → work → review → submit → done`

### 자극별 전이표

| phase | 자극 | 노드 | 부수 효과 | 다음 phase |
|---|---|---|---|---|
| kickoff | event kickoff | kickoff | 팀장 브리프 post(team, 리드 지정 포함), 동료 인사 post(dm) | negotiate 대기(phase 유지) |
| kickoff | event division | ask_division | 동료가 어떻게 나눌지 묻는 post(dm, 힌트만), negotiate_round=0, division=None | negotiate |
| kickoff | message | respond | 일반 응답(수신자 규칙) | kickoff |
| negotiate | message | negotiate | 분류 `{decision: decide∣ask∣other, parts?}`. decide(리드가 분담을 말함): 최소 조건 충족이면 set_division·update_task·"네, 그렇게 할게요" post. 위반이면 이유와 조건에 맞춘 대안 post, round+1(round≥3이면 대안을 그대로 확정). ask(어떻게 나누면 좋겠냐고 되물음): 기본안을 **참고로** 말하되 결정은 리드에게 돌림, round 유지. other: respond로 답하고 round 유지 | 확정 시 work |
| negotiate | event (요소 카드) | inject → observe | division이 None이면 default_division으로 **확정**하고 "아직 안 정해져서 일단 이렇게 진행할게요" post 후 카드 실행 (PRD F-21). 미결정 사실은 `division_decided_by: colleague_default`로 기록 | work |
| negotiate | event review | review → observe | 요소 카드와 같은 규칙으로 확정 post 후 review 실행(존중만 선택했거나 분업을 정하지 않은 경우) | review |
| work | message | respond | 수신자 규칙으로 동료/팀장 결정. 도구 선택(허용 목록), 문서명 인용. 분류가 `redivide`(리드의 재분업·재지시)면 negotiate 1회: 최소 조건 안에서 set_division·update_task 후 "알겠어요, 그렇게 바꿀게요" 안내. 담당은 그대로 두고 방향만 바꾸는 재지시(예: 사례를 휴면 사용자로)는 동료가 수락 메시지만 post하고 자기 파트 작성 시 반영 | work |
| work | event (요소 카드) | inject → observe | 카드 실행 → 직전 창(current_element, [이전 카드 due_at, 이 카드 due_at)) record_observation → current_element=카드 요소 | work |
| negotiate·work | event texture `midpoint_draft` | draft_part | division이 있으면 동료 담당 파트 초안을 `write_document_part`(work_notes 반영, 공개 문서 인용), 보드 doing 유지, 팀 채널에 한 줄 공유(event_id=texture 행). division이 없으면 공유 메시지만. **observe 없음**, 창 경계에도 영향 없음 | 유지 |
| work | event review | review → observe | 확정 division에서 동료 담당 파트 완성본을 write_document_part(초안 + work_notes.instructions 반영), 보드 done, 공유 메시지 post(both 파트·지원자 파트에 코멘트는 성향에 맡김). respect 행이 있으면 동료 담당 첫 파트에 정책 위반 삽입 → 직전 창 닫기, current_element=respect | review |
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
| kickoff, ask_division, request_report | 카드 brief로 문장 생성 후 post | 생성 |
| negotiate | 구조화 출력 `{decision: decide∣ask∣other, parts?, instruction?}`. decide면 최소 조건 검사 후 수락(set_division·update_task(doing)·work_notes.parts) 또는 대안 생성, ask면 참고안 생성, other면 respond로 위임 | 분류 + 생성 |
| respond, respond_report | tool-calling 루프. 허용 도구만, 최대 3회, 결과 2k자 절단. 인용 시 문서 제목 포함. 구조화 선행 분류 `{recipient, kind: question∣instruction∣redivide∣progress_query∣fix_request∣other, instruction?}`로 work_notes 갱신 | **모델이 도구 선택** |
| draft_part | 중간 초안 생성·저장(texture). work_notes와 search_documents 결과 입력, 지시 반영 검사 후 1회 재생성 | 생성 |
| observe | `observe/` 순수 함수로 metrics(카탈로그 `metrics`, 신규 5개 정의는 rubric.md), LLM 레이블 분류(temperature 0). 창 안에 지원자 활동(메시지·문서 수정·문서 열람·어시스턴트 호출)이 하나도 없으면 LLM을 부르지 않고 `no_evidence`. 허용 레이블 외 출력은 `unclassified`, LLM 실패는 null. evidence는 창 안의 데이터만, 타입별 참조 `{type: message∣revision∣doc_view∣assistant_call, id}` → record_observation | 규칙 + 고정 레이블 분류 |
| inject | 카드 실행. system은 text 그대로 post(LLM 없음). colleague/manager는 brief로 생성. post는 event_id·run_id·seq 포함 | 생성 |
| review | 동료 파트 완성본 작성(write_document_part, 초안·work_notes 반영, 지시 반영 검사), 보드 done, 공유 post | 생성 |
| guard 앞 context | 페르소나별 컨텍스트 허용 목록(harness.md Context)으로 입력을 거른다: 미래 카드·관찰 레이블·어시스턴트 대화는 어떤 페르소나에도 넣지 않음 | 함수 |
| guard | 모든 생성 텍스트: 금지 패턴 치환, 600자 제한 | 함수 |

동료 담당 파트는 확정 division에서 `assignee ∈ {colleague}`인 파트다. `both`는 지원자가 쓰고 동료는 리뷰 코멘트만 한다. 위반 삽입 위치는 동료 담당 파트 중 번호가 가장 작은 것.

**지원자는 리드**(카탈로그 `candidate_role: lead`): 분업을 정하고, 요구사항 변경 뒤 재지시하고, 보고를 맡는다. 동료는 묻고 따르되 자기 파트는 자율로 쓴다. 분업 결과에는 `division_decided_by: candidate∣colleague_default`를 남겨 리드가 결정을 미룬 경우가 관찰에 쓰인다.

**분업 최소 조건**(PRD 6.2, 카탈로그 `division_min`): 2번 파트는 지원자 담당, 4·5번 중 하나 이상은 동료 단독 담당이어야 한다. 이 조건은 `set_division`이 검증하고(api `PUT /division`도 422), negotiate가 조건을 어기는 결정을 받으면 "인터뷰 근거는 리드가 직접 보시는 게 좋겠어요, 대신 4·5번은 제가 다 맡을게요" 식으로 이유를 말하며 조건에 맞춘 대안을 내고 round+1 한다. 그래서 모든 분업에서 책임감 카드(2번 자료 지연)와 존중 카드(동료 파트 위반)의 전제가 성립한다.

## 페르소나 (프롬프트 `scenarios/prompts/`의 근거, 데이터는 카탈로그 `persona`)

동료는 규칙 묶음이 아니라 **회사가 원하는 인재상으로 설정된 한 사람**이다. 정의는 세 층이다.

| 층 | 내용 | 강제 방식 |
|---|---|---|
| 성향(values·style) | 카탈로그 `persona.colleague.values` 3~4개와 말투. 세부 행동(먼저 말 걸기, 진행 공유, 리뷰 코멘트, 길이)은 모델이 성향대로 정한다 | 프롬프트. 강제하지 않음 |
| 의무 액션(must) | 카드를 정해진 시점·내용으로 실행, 리드 결정 존중(division_min 위반만 되돌림), 자기 파트 작성·공유, 문서명 인용 | 카드는 결정적 노드(inject·review)가 실행. 인용은 guard 검사 |
| 금지 | **평가 보호(must_not_preempt)**: 책임감 창에서 대안·팀장 보고 선점 금지, 유연성 창에서 재분업 제안 금지, 자기 파트 위반 자각·수정 금지(지적받기 전), 협력 요청 철회 금지, 지원자 단독 파트 대필 금지. **공통(must_not)**: 점수·합격·연출·기준, 미래 카드, 미공개 문서 | 프롬프트 + guard 패턴 + 유출·선점 픽스처 테스트 |

동료가 먼저 말하는 경우가 카드 외에도 생기므로(진행 공유, 리뷰 코멘트, 되묻기) observe는 **동료·팀장 발화를 어느 창에서도 근거로 쓰지 않는다**. 점수는 지원자 행동만 센다. 카탈로그 `texture`의 중간 공유는 카드가 아닌 결 메시지이며 생략돼도 실패가 아니다.

| 항목 | 동료(이도현) | 팀장(한서윤) | 어시스턴트 |
|---|---|---|---|
| 리드에 대한 태도 | 결정을 묻고 따른다. 분업은 힌트만 주고 안을 먼저 내지 않는다. 되물으면 참고안을 말하되 결정은 돌려준다 | 리드에게 결과 책임을 묻는다(보고 요청은 리드에게) | — |
| 대행 범위 | 자기 파트와 both 파트의 협업. 지원자 단독 파트는 조언·예시 1~2문장까지 | 과제·일정 판단. 문서는 쓰지 않음 | 질문·요약·초안 생성. 지원자 문서에 직접 쓰지 않음(F-16). 회사 문서는 공개된 것만 |
| 자기 파트 | 분업 확정 시 보드 doing → 세션 중간(L/2)에 초안을 문서에 씀(지원자가 읽고 지시 가능) → 리뷰 시점에 완성본(지시 반영) + 보드 done. 진행 질문엔 work_notes.progress대로 일관되게. 파트당 300~600자, 회사 문서 인용 | — | — |
| 평가 기준·연출 질문 | 공통 안내문(common_rules) | 공통 안내문 | 공통 안내문 |
| 추가 자료 요청(대상 변경 뒤 등) | "저도 그 자료는 없어요" + 가정 제안 | 고정 대응: 추가 자료는 없으니 가정을 명시하고 검증 계획을 적어 달라 | 공개 문서 범위 밖이면 없다고 답함 |
| 업무 외 요청 | 성향대로 받아주고 업무로 복귀 | 동일 | "업무 관련 요청만 도울 수 있어요" |
| 보는 기록 | 팀 채널 + 동료 DM, 보드, 문서 상태, 공개 문서 | 팀 채널, 보드, 문서 상태 | 자기 대화 + 공개 회사 문서. 팀 대화는 보지 않음 |

업무 중 재분업·재지시: 리드가 분담을 다시 정하면(유연성 카드 뒤가 보통) 동료가 1회 받아들여 최소 조건 안에서 division·보드를 바꾼다. 그 이상은 "일정상 지금 더 바꾸긴 어렵겠어요"로 유지. 담당을 바꾸지 않는 방향 재지시는 횟수 제한 없이 수락한다. 상호 리뷰에서 동료가 지원자 파트에 코멘트를 남기는 것은 성향에 맡긴다(양방향 허용).

## 어시스턴트 그래프

`retrieve(search_documents top3) → answer(인용 포함) → guard`. thread `assistant:{session_id}`. 60회 초과는 api가 429로 막고 그래프는 호출되지 않는다. api가 request·response 메시지와 assistant_calls를 기록한다.

## observe (`app/agent/observe/`)

`compute_metrics(window, card, messages, revisions, views, assistant_calls) -> dict`, `classify(window, card, llm) -> (label|None, evidence: [{type, id}])`. 입력은 창 안의 데이터만. 카드별 픽스처로 단위 테스트. agent-session 트랙이 함께 구현한다.

창 경계: `window_start` = 직전 카드(흐름 카드 포함)의 due_at, `window_end` = 이 카드의 due_at. 마지막 창은 `ends_at` 또는 `submitted_at`까지. 모두 시나리오에서 결정되므로 재실행에 무관하다.

근거 규칙: 지원자의 메시지·문서 수정·열람·어시스턴트 호출만 근거가 된다. 동료·팀장 메시지는 어느 창에서도 근거가 아니다(동료의 자유 행동이 점수에 영향을 주지 않게).

레이블 규칙: 카드의 `labels` 중 하나, 또는 `no_evidence`(창 안에 지원자 활동 없음, LLM 미호출), `unclassified`(LLM 출력이 허용 밖), null(LLM 실패). `ignore`·`silent`·`not_noticed`처럼 "하지 않음"을 뜻하는 레이블은 창 안에 지원자 활동이 있을 때만 나올 수 있다. 레이블이 있으면 evidence가 1개 이상이어야 하며(없으면 unclassified로 강등), `silent`·`apply_silently`의 evidence는 문서 revision이다. 리포트 문장 매핑은 worker-infra/design.md.

## 복구

`docs/common/harness.md` Recovery 행. 그래프는 `last_error`에 기록하고 `RunResult.fallback_used=True`를 돌려준다. 카운터와 세션 failed 전이는 api `SessionService`가 한다.

## 완료 기준
- M1 최소 흐름: 지원자 메시지 1개 → respond → rag 검색 → post_message → WS 노출 (FakeAgentRunner 교체)
- M2: 6분 세션 + 대본 3개로 카드 전부 정시, 분업 3회 거절 확정, 미합의 중 이벤트 도래 처리, api 재시작 후 fired 이벤트 재실행과 /state 이어하기, 허용 밖 도구 거부, 미공개 문서 질문에 "아직 공유되지 않은 자료" 답변, 강제 LLM 실패 3회에 세션 failed, LangSmith trace에 run_id
- 근거 정확성 픽스처: 질문별 기대 도구·허용 문서·인용 일치 검사 10건
- 작업 기억: 대본 `all_four`에서 리드 지시 2건(분업 시 사례 기준, 유연성 뒤 대상 변경)이 동료 초안·완성본에 반영됨(핵심어 검사). 진행 질문 2회에 같은 progress로 답함. 보드가 doing(분업)→done(리뷰)으로 바뀜
