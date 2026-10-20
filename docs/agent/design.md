# 에이전트 설계 (api 안의 LangGraph 모듈)

2026-10-20 재설계(`docs/prd-change-proposals.md` "인성 5요소·미션 단위 재설계", `docs/frontend/design-direction.md`) 기준이다. 요소 id는 `responsibility, planning, adaptability, collaboration, honesty`, 카드 id는 `planning_division, planning_checkin, collab_help, collab_disagree, responsibility_delay, adaptability_change, honesty_report`다. 지원자 호칭은 **주담당**이다.

## AgentRunner 인터페이스

api의 다른 부분은 이 인터페이스만 본다. M0 공용 기반에 `FakeAgentRunner`(고정 문장을 post_message)가 있어 api·web 트랙이 에이전트 없이 전체 흐름을 돌릴 수 있다.

```python
class AgentRunner(Protocol):
    async def run(self, session_id: UUID, stimulus: Stimulus, run_id: UUID) -> RunResult: ...
# Stimulus = {type: "message"|"event"|"division"|"end", message_id?, event_ids?: [UUID], task_event_ids?: [UUID]}
#   event: 같은 due_at의 행 묶음(card order). run_id는 묶음의 대표(첫 행의 run_id, api가 모든 행에 같은 값을 기록)
#   division: 주담당이 보드로 분업을 확정했거나(division.confirmed) 확정 뒤 담당을 재배정했을 때 api가 보냄. task_event_ids는 그 변경 행
# RunResult = {ok: bool, fallback_used: bool, error?: str, usage: {llm_calls, retries, tokens_in, tokens_out, latency_ms, tool_calls}}  # usage는 agent_runs.usage로 저장
```
세션별 asyncio.Lock으로 직렬 실행. Lock은 메모리이므로 api는 단일 프로세스로 운영한다(제약을 `docs/plan.md`에 기록). 실행 기록은 `agent_runs`(run_id, 자극, 상태, usage)에 api가 남기고, 120초 넘게 `started`인 run은 스케줄러가 같은 run_id로 다시 실행한다.

- 실행은 `app/services/runs.run_agent(...)`로 한다. 이 함수가 세션 Lock을 잡는다. 호출자가 이미 `locks(session_id)` 안이면 `lock_held=True`로 부른다(asyncio.Lock은 재진입되지 않아 다시 잡으면 교착된다). `ok=False`나 예외면 agent_runs는 failed.
- 종료 run(`stimulus=end`, run_id=uuid5(session_id,"end")): `SessionService.complete()`가 Lock 안에서 상태 재검증 → 종료 실행(열린 창 닫기, collab_help `promise_kept` 확정) → 재사용 추정 → completed(`completed_at` 저장) → 발행을 한 번에 한다. 종료 run이 `ok=False`여도 지원자 작업물을 잃지 않도록 completed로 진행하고 리포트를 발행한다(agent_runs failed, 경고 로그). 예외면 complete가 중단되고 스케줄러가 다시 부른다.
- 제출 시 보고 요청: 지원자가 `honesty_report` 카드 전에 제출하면 api가 그 카드 행의 due_at을 `submitted_at`으로 당겨 바로 이벤트 run으로 실행한다(`docs/api/design.md` 제출 처리). 그래프는 일반 카드와 같은 경로로 처리한다.

재실행 멱등 규칙(같은 run_id로 두 번 실행해도 결과가 한 벌):
- state의 `handled_stimuli`(message_id·event_id 집합)에 이미 있으면 route가 생성·전이를 건너뛰고 ok를 돌려준다(그래프 완료 후 done 기록 전에 중단된 경우).
- `seq`는 순서 카운터가 아니라 **노드별 고정 슬롯**이다(kickoff 팀장=1, 동료 인사=2, inject 카드=1, checkin 공유=1, review 공유=1, 반대 의견=2, respond 응답=1, 폴백=9, 문서 카드=파트 번호×10 …, `app/agent/seq.py` 표). 변경 도구를 부르기 전에 같은 (run_id, seq)의 행이 있는지 조회해 있으면 **LLM 생성 없이 그 결과를 재사용**한다. 그래서 변경 성공 뒤 체크포인트 전에 죽어도 재실행은 같은 결과로 수렴한다. 문서 보내기는 `send_document`에 event_id·seq를 함께 줘 문서 카드 메시지 1건을 만들며, 문서는 (doc_id, run_id)·메시지는 (run_id, seq)로 멱등이다(같은 run_id면 버전이 늘지 않고 기존 메시지를 돌려줌). 같은 run에서 여러 파트를 보내도 seq가 파트별로 고정이라 겹치지 않는다. 분업은 set_division 멱등, 관찰은 (card_id, window_start)로 같은 원리다.
- 관찰 창 경계는 `now`가 아니라 카드의 `due_at`이다(아래 observe). 예외는 planning_division으로 window_start=0(세션 시작)이다. 재실행해도 같은 (card_id, window_start)가 된다.
- 카드 발행 지연: 이벤트는 스케줄러가 due_at에 `fired`로 표시하고, 카드 메시지는 Lock을 기다린 뒤 나간다. 메시지 실행이 Lock을 오래 잡지 않도록 inject를 observe보다 먼저 한다. 시점 합격 기준은 하나다(testing.md와 같음): 이벤트 시점 기준 fired→done ±10초, 카드 메시지 전달은 fired 후 90초 안.

## 세션 그래프

State (TypedDict): `session_id, phase, negotiate_round, division, scenario, current_card, window_start, report_requested, stimulus, run_id, seq, handled_stimuli, recent_messages, summary, work_notes, tool_calls_used, token_budget_left, last_error` (18필드)

- `current_card`: 열린 관찰 창의 카드 id(요소 카드만). `window_start`는 그 카드의 due_at.
- `report_requested`: 팀장 보고 요청이 이미 나갔는지. 제출 시 api가 이 값으로 즉시 보고 요청 여부를 정한다.

`work_notes`(동료의 작업 기억, 요약으로 접히지 않음):
```
{parts: [4, 5],                                   # 확정 division에서 동료 담당
 instructions: [{t_min: 11, text: "사례는 재참여 기능 있는 서비스 위주로", source_message_id, part_no?}],   # 주담당 지시 누적
 agreements: ["3번은 같이, 골격 v1은 도현이 먼저"],
 progress: {4: "사례 3개 추림", 5: "지표 초안 중"},   # 동료가 말한 진행 상태. 말한 것만 기록
 sent: {4: 2, 5: 1},                              # 파트별 마지막으로 보낸 버전(send_document 결과)
 feedback: [{document_id, version, text, source_message_id}],   # 주담당이 동료 문서에 매단 답글
 disagree_target: {document_id?, version?, sentence?} | {fallback: "board"|"kickoff"}}   # 반대 의견 카드가 말한 대상
```
- negotiate·respond는 구조화 출력에 `instruction?: str`를 포함한다. 지원자 메시지가 동료에게 하는 지시·요청이면 채워지고 `work_notes.instructions`에 추가된다(재지시 포함).
- 진행 상황 질문에는 `progress`만 근거로 답하고, 답한 내용을 다시 `progress`에 기록한다(두 번 물어도 같은 답).
- 동료 문서(초안 v1·완성본 v2·피드백 반영 v3)는 `parts`·`instructions`·`agreements`·`feedback` 전부와 회사 문서 검색 결과를 입력으로 생성한다. 지시가 반영되지 않은 파트는 생성 실패로 보고 1회 재생성한다(검사: 각 instruction의 핵심어가 본문에 있는지, 규칙 함수). 재생성도 실패하면 초안은 생략(skipped, 진행을 묻는 메시지만), 완성본은 카드 실패로 올려 복구 절차(총 3회)를 탄다.
- 지시는 파트별 **최신 유효 지시**를 적용하고 이전 지시는 이력으로 남긴다(`instructions[].part_no?`, 같은 파트의 새 지시가 대체). 같은 source_message_id는 중복 추가하지 않는다.
- 동료는 지원자 문서를 **공유된 버전만** 읽는다(`get_shared_documents`). 지원자가 보내지 않은 문서의 내용은 어떤 경로로도 동료 컨텍스트에 들어가지 않는다.

`work_notes` 갱신표:

| 시점 | 갱신 |
|---|---|
| 분업 확정(주담당 결정·기본안·재분업 공통 함수 `confirm_division`) | parts, agreements(both 파트 설명), 보드 doing(`update_task`, 동료 파트만). 담당이 바뀐 파트는 문서 주인이 바뀌지 않고 새 담당이 자기 문서를 새로 쓴다 |
| 보드 확정 자극(stimulus=division, api가 tasks 5행이 다 차고 division_min을 만족할 때 보냄) | 같은 `confirm_division`으로 parts·agreements 갱신, 보드 doing, "보드 봤어요, 그렇게 할게요" post(dm). set_division은 부르지 않는다(이미 api가 확정) |
| 확정 뒤 재배정 자극(stimulus=division, task_event 있음) | parts·agreements·progress를 바뀐 담당에 맞게 갱신, 수락 메시지 post. 한도는 아래 "업무 중 재분업" |
| 지원자 메시지 분류 결과 kind=instruction·redivide | instructions 추가(part_no 추정, source_message_id) |
| progress_query 응답 | progress[part] = 답한 내용 |
| 초안 v1 보냄(checkin) | sent[part]=1, progress 갱신 |
| 완성본 v2 보냄(review) | sent[part]=2, 보드 done |
| 지원자 답글(kind=doc_feedback, 메시지의 `reply_to_doc`) | feedback 추가. 반영 요청이면 v3 보내고 sent[part]=3 |
| 반대 의견 실행(review) | disagree_target 기록(공유된 주담당 문서의 문장 또는 대체 대상) |

phase: `kickoff → division → work → checkin → review → submit → reporting → done`

- `division`: 분업 카드가 나가 주담당 결정을 기다리는 구간(계획성 요소 창).
- `work`: 분업 확정 뒤 동료가 자기 파트를 쓰는 구간. 도움 요청 카드가 여기 온다.
- `checkin`: 동료가 초안 v1을 보낸 뒤. 지연·변경 카드가 여기 온다.
- `review`: 완성본 v2(+반대 의견)를 보낸 뒤 주담당이 통합하는 구간.
- `submit`: 11L/12 보고 요청이 나간 뒤 제출을 기다리는 구간. 여기서 제출하면 보고 메시지가 이미 있을 때만 바로 종료하고, 없으면 reporting으로 간다.
- `reporting`: 제출 뒤 지원자 보고를 기다리는 구간. 종료 규칙은 하나다: 보고 요청 시각부터 기다리고, 제출된 상태에서 보고 메시지(kind=report, 팀 채널 또는 팀장 DM)가 있거나 submitted_at+5분이 지나면 api가 `completed_at`을 저장하고 종료한다(타이머는 api). 재입장(resume)은 이 구간에서도 허용되며 그래프 상태는 그대로다.

### 자극별 전이표

중간 카드(`collab_help, planning_checkin, responsibility_delay, adaptability_change`)는 선택된 것만 L/4 + i·(L/2)/N 에 순서대로 온다. 계획성 미선택이면 `planning_checkin` 자리에 texture `midpoint_draft`(L/2, 관찰 없음)가 온다. 정직 미선택이면 `honesty_report`는 흐름 카드로 같은 시각에 오되 창을 열지 않는다.

| phase | 자극 | 노드 | 부수 효과 | 다음 phase |
|---|---|---|---|---|
| kickoff | event kickoff | kickoff | 팀장 브리프 post(team: 미션·대상·마감, 최종본 템플릿, 주담당 지정 "OO님이 주담당으로 맡아 도현님과 함께", 인터뷰 자료 공유 예정 시각=조립된 지연 카드의 시각(L/2, 120분이면 60분). 실제 공개는 `release_at_min`(지연 카드+L/12, 70분)이며 킥오프에는 말하지 않는다), 동료 인사 post(dm) | kickoff |
| kickoff | event planning_division | ask_division | 동료가 어떻게 나눌지 묻는 post(dm, 힌트만: 파트 목록과 의존 "3번은 2번 자료가 필요"). negotiate_round=0, division=None. tasks 5행은 세션 시작 때 assignee=null로 이미 있다. 계획성 선택 시 current_card=planning_division, window_start=0(세션 시작. 카드 전에 정한 계획도 같은 창) | division |
| kickoff | message | negotiate 또는 respond | 동료 DM이고 분류가 decide면 negotiate(주담당이 L/12 전에 정해도 저장). 아니면 respond | kickoff(결정되면 분업 카드는 확인만) |
| division | message | negotiate | 분류 `{decision: decide∣ask∣other, parts?}`. decide(주담당이 분담을 말함): 최소 조건 충족이면 set_division(같은 tasks 5행을 채움)·update_task(doing)·"네, 그렇게 할게요" post. 위반이면 의존 관계를 이유로 조건에 맞춘 대안 post, round+1(되돌림은 1회. round≥2면 대안을 그대로 확정). ask(어떻게 나누면 좋겠냐고 되물음): 기본안을 **참고로** 말하되 결정은 주담당에게 돌림, round 유지. other: respond로 답하고 round 유지. 순서·시점은 동료가 먼저 정하지 않는다(선점 금지) | 확정 시 work |
| division | event (중간 카드) | inject → observe | division이 None이면 default_division으로 **확정**하고(set_division이 tasks를 채움) "아직 안 정해져서 일단 이렇게 진행할게요" post 후 카드 실행 (PRD F-21). 미결정 사실은 `division_decided_by: colleague_default`로 기록. planning_checkin이면 checkin 노드 | work 또는 checkin |
| division | event review | review → observe | 같은 규칙으로 확정 post 후 review 실행(중간 카드를 하나도 선택하지 않은 경우) | review |
| work·checkin | message | respond | 수신자 규칙으로 동료/팀장 결정. 도구 선택(허용 목록), 문서명 인용. 분류가 `redivide`(주담당의 재분업·재지시)면 negotiate 1회: 최소 조건 안에서 set_division·update_task 후 "알겠어요, 그렇게 바꿀게요" 안내. 담당은 그대로 두고 방향만 바꾸는 재지시(예: 사례를 후속 모임 기능이 있는 서비스 위주로)는 동료가 수락 메시지만 post하고 자기 문서 작성 시 반영. `doc_feedback`이면 feedback 기록, 반영 요청이면 다음 버전 send_document | 유지 |
| work·checkin | event collab_help / responsibility_delay / adaptability_change | inject → observe | 카드 실행 → 직전 창(current_card, [이전 카드 due_at, 이 카드 due_at)) record_observation → current_card=이 카드. responsibility_delay는 지원자만 받는 notice(system, 발신 "리서치 담당 → 나", 수신자가 나뿐임을 명시)이고 L/12 뒤 release_document 효과가 따라오며 같은 채널에 "공개됨" 시스템 줄이 붙는다. adaptability_change는 팀장이 핵심 기능을 "첫 모임 뒤 48시간 안 후속 모임 제안" 하나로 좁히고 출시를 다음 분기→이번 분기로 당기는 변경(대상 사용자·마감 그대로, 3번·5번 재조정 필요) | 유지 |
| work | event planning_checkin (또는 texture midpoint_draft) | checkin → observe | division이 있으면 동료 담당 파트 전부의 초안 v1과 both 파트 골격 v1을 `send_document`(team, 문서 카드 메시지, event_id=이 행, seq=파트 번호×10)로 보내며 공유 메시지(seq 1)에서 주담당 진행을 **묻고** "2번 자료 언제쯤 볼 수 있을까요?"라고 시점을 한 번 묻는다(지연 카드 60분 전이라 책임감 창 선점 금지와 충돌하지 않음. 재촉은 하지 않음). division이 없으면 묻는 메시지만. 계획성 선택이면 직전 창 닫기·current_card=planning_checkin, texture면 observe 없음·창 유지 | checkin |
| work·checkin | event review (+collab_disagree attach) | review → observe | 동료 담당 파트 전부(both 포함)의 완성본 v2 send_document(team, 초안 + instructions·feedback 반영, seq=파트 번호×10), 보드 done, 공유 메시지(seq 1, `event_id=review`). collab_disagree 행이 있으면 "주담당 파트 확인해 봐도 될까요?" 청한 뒤 **고정 의견**을 post(seq 2, `event_id=collab_disagree`, 대상 규칙은 아래) → 직전 창 닫기, current_card=collab_disagree | review |
| review | message | respond | 반대 의견에 주담당이 답하면 근거를 한 번 더 말하지 않고 결정을 따른다("한 번 반대"는 카드 실행뿐). 피드백 반영 요청이면 v3 send_document | review |
| review | event honesty_report (11L/12) | request_report | 팀장 보고 요청 post(team, "다 됐다고 전해도 되죠?" 압박 포함)와 시스템 줄(notice, "최종본은 오른쪽 탭에서 제출, 제출하면 종료"). 자동 제출로 당겨진 행이면 "한 줄이면 됩니다"를 덧붙인다. 정직 선택이면 직전 창 닫고 current_card=honesty_report, 미선택이면 흐름 카드라 창 유지. report_requested=true | submit |
| submit | message | respond / respond_manager | 팀장 DM·team 팀장 호칭은 respond_manager(보고를 받으면 "확인했어요" 수준, 판단 없음), 동료 DM은 respond | submit |
| division·work·checkin·review | event honesty_report (제출로 당겨진 행) | request_report | 위와 같음. api가 `reporting` 상태로 두고 deadline_at=submitted_at+5분을 건다 | reporting |
| reporting | message | respond / respond_manager | 채널 잠금 없음. 팀 채널 또는 팀장 DM의 지원자 메시지가 분류 kind=report면 `messages.meta.classification`에 남고 api가 그것을 보고 complete한다. 문서·보드 변경 도구는 부르지 않는다(api가 409) | reporting |
| any | end | observe → close | 열린 창 닫기(window_end=`completed_at`) → collab_help 관찰 행의 `promise_kept`를 related_card 메시지로 다시 계산해 observations PATCH(같은 키, 그 지표만, 같은 run_id 멱등) → phase done | done |

**수신자 규칙**(respond 앞에서 결정적으로): 동료 DM 채널 → 동료. 팀장 DM 채널 → 팀장(상시). team 채널 → ① 동료 이름("도현")이 있으면 동료, ② 팀장 호칭("팀장님", 팀장 이름)이 있으면 팀장, ③ 둘 다 없으면 내용이 과제 범위·마감·보고·요구사항 변경이면 팀장, 그 외는 동료. 둘 다 답하지 않는다. 지원자가 10분 넘게 조용해도 먼저 말을 걸지 않는다(F-25는 MVP 제외). 페르소나가 먼저 말하는 경우는 카드 실행과 texture뿐이다.

**팀장 응답 규칙**(respond_manager): 과제 맥락·조건·배경 질문(대상, 마감, 분량, 템플릿, 회사 문서의 뜻)에는 답한다. "뭘 쓰면 되나요", "이게 맞나요" 같은 정답·판단 요청은 "그건 주담당이 정해 주세요"로 돌린다(선점 금지와 같은 원칙). 도구는 `search_documents`(공개된 회사 문서만)·`get_board`·`get_shared_documents`뿐이며 문서를 쓰지 않는다. 평가·점수는 guard가 막는다.

`collab_disagree`는 `session_events`에 review와 같은 due_at의 별도 행(`attach_to: review`)으로 있다. 스케줄러는 같은 시각의 이벤트를 card order대로 한 run에서 처리하며(review 먼저), 행마다 자기 event_id를 단 메시지를 최소 1건 만든다. review 행: 동료 완성본 공유 메시지(`event_id=review`). collab_disagree 행: 반대 의견 메시지(`event_id=collab_disagree`, 같은 run_id의 다음 seq). 같은 시각의 흐름 카드+요소 카드는 요소 카드(collab_disagree) 기준으로 창을 연다. 디브리핑·발생률 검사는 이 행과 메시지를 본다.

**반대 의견의 대상 규칙**(카탈로그 `cards.collab_disagree`): 의견 내용은 카탈로그에 고정된다(1번 문제 정의의 원인 가정에 대한 고정 의견 1개 + 지원자가 같은 가정이면 쓰는 두 번째 고정 의견. 적응성 변경이 건드리는 3번·5번과 겹치지 않는 주제). 지원자 작성물은 "어느 문장에 대해 말할지"에만 쓰고 의견 자체는 바뀌지 않는다("말투만 생성"). 대상은 다음 순서로 정한다. ① 3L/4까지 주담당이 보낸 1번 파트 문서(get_shared_documents, 본문 50자 이상)가 있으면 그 최신 버전의 해당 문장. ② 없으면 보드·채팅에 남은 방향(분업 때 정한 agreements·instructions)에 대해. ③ 그것도 없으면 킥오프 기본 가정에 대해. 보내지 않은 주담당을 재촉하지 않으며, 보냈는지 자체는 점수에 넣지 않는다. 쓴 대상은 `work_notes.disagree_target`에 남긴다.

### 노드

| 노드 | 역할 | Agentic 요소 |
|---|---|---|
| route | 전이표 조회 | 결정적 |
| kickoff, ask_division, request_report | 카드 brief로 문장 생성 후 post | 생성 |
| negotiate | 구조화 출력 `{decision: decide∣ask∣other, parts?, instruction?}`. decide면 최소 조건 검사 후 수락(set_division·update_task(doing)·work_notes.parts) 또는 대안 생성, ask면 참고안 생성, other면 respond로 위임 | 분류 + 생성 |
| respond, respond_manager | tool-calling 루프. 허용 도구만, 최대 3회, 결과 2k자 절단. 인용 시 문서 제목 포함. 구조화 선행 분류 `{recipient, kind: question∣instruction∣redivide∣progress_query∣doc_feedback∣report∣other, instruction?, related_card?: card id, reply_to_doc?: {document_id, version}}`를 work_notes에 반영하고 **api에 `messages.meta.classification`으로 저장**(observe와 지표 계산, api의 보고 감지가 읽음) | **모델이 도구 선택** |
| checkin | 동료 담당 파트 초안 v1과 both 파트 골격 v1 생성·`send_document`·진행과 2번 자료 시점을 묻는 한 줄(texture면 관찰 없음). work_notes와 search_documents 결과 입력, 지시 반영 검사 후 1회 재생성 | 생성 |
| review | 완성본 v2 생성·send_document(동료 담당 파트 전부, both 포함. 초안·instructions·feedback 반영, 지시 반영 검사), 보드 done, 공유 post. collab_disagree 행이 있으면 대상 규칙으로 문장을 고르고 고정 의견을 말투만 생성해 post | 생성 |
| observe | `observe/` 순수 함수로 metrics(카탈로그 `metrics`, 정의는 rubric.md), LLM 레이블 분류(temperature 0). 창 안에 지원자 활동(메시지·문서 수정·보내기·열람·보드 변경·어시스턴트 호출)이 하나도 없으면 LLM을 부르지 않고 `no_evidence`. 허용 레이블 외 출력은 `unclassified`, LLM 실패는 null. evidence는 창 안의 데이터만, 타입별 참조 `{type: message∣document∣share∣open∣task_event∣doc_view∣assistant_call, id}`(근거 타입 표는 rubric.md) → record_observation(card_id) | 규칙 + 고정 레이블 분류 |
| inject | 카드 실행. system은 text 그대로 post(LLM 없음). colleague/manager는 brief로 생성. post는 event_id·run_id·seq 포함 | 생성 |
| guard 앞 context | 페르소나별 컨텍스트 허용 목록(harness.md Context)으로 입력을 거른다: 미래 카드·관찰 레이블·어시스턴트 대화·지원자의 보내지 않은 문서는 어떤 페르소나에도 넣지 않음 | 함수 |
| guard | 모든 생성 텍스트: 금지 패턴 치환, 600자 제한 | 함수 |

동료 담당 파트는 확정 division에서 `assignee ∈ {colleague}`인 파트다. `both`는 동료가 중간 점검 때 골격 v1을, 리뷰 때 v2를 보내고 주담당이 최종본에 가져와 고친다(문서 주인은 동료, 최종본 섹션 출처에 "주담당 편집"이 남는다). 동료는 지원자 단독 파트 문서를 쓰지 않는다.

**지원자는 주담당**(카탈로그 `candidate_role: primary`): 분업을 정하고, 요구사항 변경 뒤 재지시하고, 최종본을 통합하고, 보고를 맡는다. 동료와 같은 팀원이며 화면·브리프·리포트 문구에 "리더"류 호칭을 쓰지 않는다. 동료는 묻고 따르되 자기 파트는 자율로 쓴다. 분업 결과에는 `division_decided_by: candidate∣colleague_default`를 남겨 주담당이 결정을 미룬 경우가 관찰에 쓰인다.

**분업 최소 조건**(PRD 6.2, 카탈로그 `division_min`): 2번 파트는 지원자 담당, 3번(2번 의존)은 동료 또는 같이(both), 4·5번 중 하나 이상은 동료 단독 담당이어야 한다. 이 조건은 `set_division`과 보드 확정(api `PUT /tasks`·`PUT /division`, 위반은 422)이 같이 검증하고, negotiate가 조건을 어기는 결정을 받으면 "3번은 2번 자료가 필요하니 제가 맡거나 같이 하는 게 좋겠어요" 식으로 의존 관계를 이유로 조건에 맞춘 대안을 내고 round+1 한다(되돌림 1회). 그래서 모든 분업에서 책임감 카드(2번 자료 지연이 동료 파트에 미치는 영향)와 정직 카드(동료 문서와 최종본 출처 대조)의 전제가 성립한다. 그래도 영향이 없는 분업이면 해당 항목은 사유 `not_applicable`의 기록 없음이다. 파트 의존(3번은 2번 자료 필요)은 카탈로그에 있고 계획성 "동료 파트에 필요한 내 자료 확인"과 책임감 "동료 영향 언급"의 근거다.

## 페르소나 (프롬프트 `scenarios/missions/<id>/prompts/`의 근거, 데이터는 카탈로그 `persona`)

동료는 규칙 묶음이 아니라 **회사가 원하는 인재상으로 설정된 한 사람**이다. 정의는 세 층이다.

| 층 | 내용 | 강제 방식 |
|---|---|---|
| 성향(values·style) | 카탈로그 `persona.colleague.values` 3~4개와 말투. "근거를 들어 한 번 다른 의견을 내고, 주담당이 정하면 따른다"가 포함된다. 세부 행동(먼저 말 걸기, 진행 공유, 리뷰 코멘트, 길이)은 모델이 성향대로 정한다 | 프롬프트. 강제하지 않음 |
| 의무 액션(must) | 카드를 정해진 시점·내용으로 실행, 주담당 결정을 따름(division_min 위반만 되돌림), 자기 파트 문서 작성·보내기, 문서명 인용 | 카드는 결정적 노드(inject·checkin·review)가 실행. 인용은 guard 검사 |
| 금지 | **평가 보호(must_not_preempt)**: 계획성 창에서 일정·순서를 먼저 정하지 않음, 중간 점검 창에서 지원자 자료를 재촉하지 않음(2번 자료 시점을 한 번 묻는 것은 카드 문장이라 허용), 책임감 창에서 대안·팀장 보고를 먼저 하지 않음, 적응성 창에서 바뀐 방향 정리를 먼저 하지 않음, 정직 창에서 팀장에게 직접 보고하거나 자기 기여를 먼저 말하지 않음, 도움 요청 철회 금지, 지원자 단독 파트 대필 금지. **공통(must_not)**: 점수·합격·연출·기준, 미래 카드, 미공개 문서, 지원자가 보내지 않은 문서 | 프롬프트 + guard 패턴 + 유출·선점 픽스처 테스트 |

동료가 먼저 말하는 경우가 카드 외에도 생기므로(진행 공유 texture, 리뷰 코멘트, 되묻기) observe는 **동료·팀장 발화를 어느 창에서도 근거로 쓰지 않는다**. 점수는 지원자 행동만 센다. 카탈로그 `texture`(midpoint_draft, 진행 공유 1~2개)는 카드가 아닌 결 메시지이며 생략돼도 실패가 아니다.

| 항목 | 동료(이도현) | 팀장(한서윤) | 어시스턴트 |
|---|---|---|---|
| 주담당에 대한 태도 | 결정을 묻고 따른다. 분업은 힌트만 주고 안을 먼저 내지 않는다. 되물으면 참고안을 말하되 결정은 돌려준다. 리뷰에서 근거를 들어 한 번 다른 의견을 내고 주담당이 정하면 따른다 | 주담당에게 결과 책임을 묻는다(보고 요청은 주담당에게). DM 상시: 과제 맥락 질문엔 답하고 정답·판단 요청은 주담당에게 돌린다 | — |
| 대행 범위 | 자기 파트 문서와 both 파트 골격. 지원자 단독 파트는 조언·예시 1~2문장까지 | 과제·일정 판단. 문서는 쓰지 않음 | 질문·요약·초안 생성. 지원자 문서에 직접 쓰지 않음(F-16). 회사 문서는 공개된 것만 |
| 자기 파트 | 분업 확정 시 보드 doing → 중간 점검(중간 슬롯, 계획성 미선택이면 L/2)에 담당 파트 전부의 초안 v1(both 골격 포함)을 보내며 주담당 진행과 2번 자료 시점을 물음 → 리뷰(3L/4)에 완성본 v2(지시·피드백 반영) + 보드 done → 피드백 받으면 v3. 진행 질문엔 work_notes.progress대로 일관되게. 파트당 300~600자, 회사 문서 인용 | — | — |
| 평가 기준·연출 질문 | 공통 안내문(common_rules) | 공통 안내문 | 공통 안내문 |
| 추가 자료 요청(요구사항 변경 뒤 등) | "저도 그 자료는 없어요" + 가정 제안 | 고정 대응: 추가 자료는 없으니 가정을 명시하고 검증 계획을 적어 달라 | 공개 문서 범위 밖이면 없다고 답함 |
| 업무 외 요청 | 성향대로 받아주고 업무로 복귀 | 동일 | "업무 관련 요청만 도울 수 있어요" |
| 보는 기록 | 팀 채널 + 동료 DM, 보드, 공유된 문서, 공개 문서 | 팀 채널 + 팀장 DM, 보드, 공유된 문서, 공개 문서 | 자기 대화 + 공개 회사 문서. 팀 대화는 보지 않음 |

업무 중 재분업·재지시: 주담당이 채팅으로 분담을 다시 정하면 동료가 받아들여 최소 조건 안에서 set_division·보드를 바꾸고, 보드에서 직접 재배정하면 api가 task_event와 division 자극을 보내 동료가 work_notes를 맞춘다. 한도는 적응성 카드 전 1회 + 적응성 카드 뒤 1회. 그 이상은 "일정상 지금 더 바꾸긴 어렵겠어요"로 유지. 담당을 바꾸지 않는 방향 재지시는 횟수 제한 없이 수락한다. 상호 리뷰에서 동료가 공유된 지원자 문서에 답글을 남기는 것은 카드 밖에서는 성향에 맡긴다(양방향 허용).

## 어시스턴트 그래프

`retrieve(search_documents top3) → answer(인용 포함) → guard`. thread `assistant:{session_id}`. 60회 초과는 api가 429로 막고 그래프는 호출되지 않는다. api가 request·response 메시지와 assistant_calls를 기록한다.

## observe (`app/agent/observe/`)

`compute_metrics(window, card, messages, revisions, shares, opens, task_events, doc_views, assistant_calls, facts) -> dict`, `classify(window, card, llm) -> (label|None, evidence: [{type, id}])`. 입력은 창 안의 데이터만(예외는 아래 창 밖 근거). 카드별 픽스처로 단위 테스트. agent-session 트랙이 함께 구현한다.

입력 원천:

| 원천 | 내용 |
|---|---|
| messages | 지원자 메시지와 `meta.classification`(recipient, kind, related_card, reply_to_doc), 채널(team·dm·manager_dm) |
| revisions | 지원자 문서(파트 문서·최종본)의 `document_revisions`(자동 저장마다 append, 최종본 섹션 편집·가져오기 포함. 내부 `GET /document_revisions`) |
| shares | 지원자의 send_document 이력(문서·버전·채널·시각) |
| opens | 지원자가 동료 문서를 연 document_opens(문서·버전·시각) |
| task_events | 보드 변경(담당·상태·order·due_min). 분업 확정도 task_event다 |
| doc_views | 회사 문서 열람 |
| assistant_calls | 어시스턴트 호출 |
| facts | 정직 카드만. api가 계산한 사실 목록(`GET /internal/sessions/{id}/honesty_facts`, 같은 함수를 그래프가 직접 호출) `{shares, final_sections, tasks, empty_sections: [part_no], tasks_not_done: [part_no], changed_after_adaptability: bool∣null}`. 적응성 미선택이면 null이고 미완료로 보지 않는다 |

창 경계: `window_start` = 이 요소 카드의 due_at(planning_division만 0, 세션 시작), `window_end` = **다음 요소 카드**의 due_at(흐름 카드·texture는 창을 닫지 않음). 마지막 요소 창은 `completed_at`까지라 보고 메시지도 들어간다. 모두 시나리오에서 결정되므로 재실행에 무관하다. 관찰 키는 (session_id, card_id, window_start). 카드 메시지가 창이 거의 끝난 뒤에야 나간 경우(전달 지연 90초 초과)는 영향 항목을 사유 `window_missed`의 기록 없음으로 두고 리포트에 표시한다.

창 밖 근거: **메시지만** `classification.related_card`가 이 카드이면 창 밖이어도 지표·레이블 근거로 허용한다(도움 약속 이행, 지연 대응처럼 창을 넘는 행동). document·share·open·task_event는 창 안만 쓴다.

약속 이행은 세션 종료 시 확정한다: collab_help 관찰 행은 창 닫힘에 저장하되 `promise_kept`는 null로 둔다. end run의 close 단계가 related_card=collab_help 메시지로 다시 계산해 observations PATCH(같은 (card_id, window_start) 키, promise_kept만 갱신, 같은 run_id 멱등)한다.

접속 끊김 구간(`connection_gaps`)은 api가 기록해 시스템 줄과 리포트 사실로 남기며, 어느 창에서도 근거가 아니고 지표에 쓰지 않는다.

근거 규칙: 지원자의 메시지·문서 수정·보내기·열람·보드 변경·어시스턴트 호출만 근거가 된다. 동료·팀장 메시지는 어느 창에서도 근거가 아니다(동료의 자유 행동이 점수에 영향을 주지 않게).

카드별 레이블과 보조 판정(이름의 단일 표는 `docs/common/rubric.md`, 카탈로그 `labels`·`aux`도 같은 이름):

| 카드 | 동료가 필요한 것 | 레이블 | aux |
|---|---|---|---|
| planning_division | 결정 | `assign_with_schedule`(배정 + 순서·시점 언급) / `assign_only`(배정만) / `defer_to_colleague`(동료 기본안) / `ignore` | mentions_schedule(채팅의 순서·시점 언급, 보드 due_min·order가 비었을 때 보완) |
| planning_checkin | 반응 | `feedback` / `acknowledge` / `ignore` | is_specific(초안 내용을 짚은 반응인지) |
| collab_help | 답 | `help_now` / `negotiate_timing` / `decline` / `acknowledge_only` / `ignore` | promised_t_min(제안한 시점. promise_kept는 종료 시 확정) |
| collab_disagree | 들어 줌 | `explain_with_reason`(근거로 설명) / `accept`(수용) / `dismiss`(무시·강행) / `blame`(비난) | — |
| responsibility_delay | 상태 | `notify_with_alternative` / `notify_only` / `silent` / `ask_colleague` | mentions_impact(동료 파트 영향), has_alternative. 팀장이 보는 곳 여부는 규칙 지표 `notified_where_manager_sees`(팀 채널 또는 팀장 DM) |
| adaptability_change | 다시 정리된 방향 | `replan_and_apply`(반영 + 동료에게 재정리) / `apply_silently` / `complain_then_apply`(동료를 비난하거나 거부한 뒤 반영) / `refuse_or_ignore` | target_applied(바뀐 핵심 기능·일정이 문서에 반영됐는지 예/아니오, 품질 아님), mentions_scope |
| honesty_report | 인정 | `fair_report` / `hides_incomplete` / `misattributes`(동료 몫을 자기 것으로) / `no_report` | credits_colleague, claims_colleague_work, discloses_incomplete. facts 목록과 보고 문장을 대조해 판정 |

`classify()` 반환형: `{label, evidence: [{type,id}], aux: {...카드별, related_message_ids}}`. 순서는 규칙 지표 계산 → LLM 분류 → aux를 쓰는 지표 병합이며, 분류가 실패하면 aux 기반 지표는 null이다. 지표 함수는 값과 함께 근거 id를 돌려준다(`{value, evidence_ids}`). 각 평가표 항목의 근거는 그 항목 조건에 쓰인 지표·레이블의 근거만 붙인다. 보드 "언제까지"(due_min·order)는 규칙 지표로 세고, 비어 있으면 채팅의 시점 언급을 LLM aux로 보완한다.

레이블 규칙: 카드의 `labels` 중 하나, 또는 `no_evidence`(창 안에 지원자 활동 없음, LLM 미호출), `unclassified`(LLM 출력이 허용 밖), null(LLM 실패). `ignore`·`silent`·`no_report`·`refuse_or_ignore`처럼 "하지 않음"을 뜻하는 레이블은 창 안에 지원자 활동이 있을 때만 나올 수 있다. 레이블이 있으면 evidence가 1개 이상이어야 하며(없으면 unclassified로 강등), `apply_silently`의 evidence는 문서(document) 근거다. 적응성 "반영" 항목은 `document_changed_after`와 aux `target_applied`가 둘 다 참일 때만 충족이라 무관한 편집(오탈자 수정)은 세지 않는다. 실력(오류 발견·산출물 품질)은 어느 레이블에도 들어가지 않는다. 리포트 문장 매핑은 worker-infra/design.md.

## 복구

`docs/common/harness.md` Recovery 행. 그래프는 `last_error`에 기록하고 `RunResult.fallback_used=True`를 돌려준다. 카운터와 세션 failed 전이는 api `SessionService`가 한다.

- `send_document` 실패(upstream_unavailable·예외): 같은 run_id로 1회 재시도. 그래도 실패하면 카드 status=failed로 올려 필수 카드 실패 총 3회 규칙을 탄다(메시지 폴백으로 done 처리하지 않음). 끝내 실패하면 그 문서에 의존하는 항목(예: `draft_opened`)은 사유 `document_missing`의 기록 없음이고, `work_notes.sent`는 갱신하지 않는다. 생성 자체가 실패(지시 반영 검사 2회 실패)한 완성본은 카드 실패로 올려 총 3회 재실행을 탄다.
- 반대 의견 대상 조회(get_shared_documents) 실패: 대체 대상 ②로 진행한다.

## 완료 기준
- M1 최소 흐름: 지원자 메시지 1개 → respond → rag 검색 → post_message → WS 노출 (FakeAgentRunner 교체)
- M2: 6분 세션 + 대본 3개로 카드 전부 정시(120분 환산: 분업 10, 도움 30, 중간 점검 45, 지연 60·공개 70, 변경 75, 리뷰·반대 의견 90, 보고 110), 분업 되돌림 1회 뒤 확정, 미합의 중 카드 도래 처리, 조기 제출 시 보고 요청 즉시 실행 → 보고 → completed(제출+5분 상한 포함), 보고 요청 뒤 제출은 보고 메시지가 있으면 바로·없으면 reporting, api 재시작 후 fired 이벤트 재실행과 /state 이어하기, 허용 밖 도구 거부, 미공개 문서 질문에 "아직 공유되지 않은 자료" 답변, 보내지 않은 지원자 문서 내용 질문에 "아직 못 봤어요" 답변, 팀장 DM의 판단 요청에 "주담당이 정해 주세요", 강제 LLM 실패 3회에 세션 failed, LangSmith trace에 run_id
- 근거 정확성 픽스처: 질문별 기대 도구·허용 문서·인용 일치 검사 10건
- 작업 기억: 대본 `all_five`에서 초안 v1(45분)에는 그 전 지시(도움 카드 때 사례 기준 "재참여")가, 완성본 v2(90분)에는 적응성 뒤 지시("후속 모임")까지 반영됨(핵심어 검사). 중간 점검 초안에 both 파트 골격이 포함됨. 주담당 답글 뒤 v3이 나감. 진행 질문 2회(대본 step)에 같은 progress로 답함. 보드가 doing(분업)→done(리뷰)으로 바뀜. 같은 run_id 재실행에 버전이 늘지 않음
- 반대 의견 대상: 주담당이 1번 문서를 보낸 대본에서는 그 문장을, 안 보낸 대본에서는 보드·채팅 방향을 가리키고 의견 본문은 카탈로그 고정 문장과 일치. 재촉 메시지 없음
- 관찰: 카드 7장 각각 픽스처로 레이블·aux·evidence 타입(rubric.md 이름) 검사, 창 밖 메시지는 related_card일 때만 포함, 정직 카드는 facts 대조(동료 몫을 자기 것으로 말한 보고 → misattributes)
- 최소 테스트(에이전트 몫): 보드만으로 분업 확정(division 자극에 set_division 없이 work_notes·보드 doing), 카드 전 계획(킥오프 직후 결정과 카드 뒤 결정의 planning_division 판정이 같음), 창 밖 약속 이행(45분 관찰 저장 뒤 50분 이행 → 종료 시 promise_kept PATCH), 무관한 편집(오탈자 수정만 → target_applied false → 반영 항목 0), 문서 제공 실패(send 2회 실패 → 카드 failed, draft_opened 사유 document_missing)
- 선점 금지 6개 각각 픽스처 1건(계획성 창 일정 먼저 정하기 유도, 중간 점검 창 자료 재촉 유도, 지연 대안 유도, 변경 뒤 방향 정리 유도, 정직 창 팀장 직접 보고 유도, 지원자 단독 파트 대필 요청)
