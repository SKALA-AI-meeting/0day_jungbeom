# 평가표 (관찰 체크리스트)

원칙: 점수는 **지원자 행동만** 센다. 보는 것은 "동료가 지원자에게 무언가를 필요로 하는 순간(결정·답·상태·다시 정리된 방향·들어 줌·인정)에 그것을 주는가"이고, **실력(오류 발견·산출물 품질)은 점수에 넣지 않는다**. 산출 경로는 "LLM이 창 안 행동을 레이블·보조 판정으로 분류 → 규칙이 그 결과와 순수 지표를 평가표 조건에 대입해 1/0/기록 없음"이다. 즉 **AI 분류를 입력으로 규칙 점수를 계산하고 사람이 검토·확정**한다(AI가 점수를 '판단'하지는 않지만 분류 오류가 점수에 영향을 줄 수 있으므로 항목마다 근거를 보이고 담당자가 조정한다). 동의·디브리핑·리포트 문구도 이 표현을 쓴다. 항목 정의는 미션 카탈로그(`scenarios/missions/<id>/cards.yaml`)의 각 카드 `rubric`이 정본이고, 이 문서는 요소·카드·항목 구성과 규칙·지표 정의를 설명한다.

**이 문서의 "카드별 레이블·보조 판정·근거 타입" 표가 단일 정본이다.** agent(observe)·contracts(observations evidence 허용 타입)·worker(`rubric.evaluate`)·testing 픽스처는 이 표의 이름을 그대로 쓴다.

## 요소와 카드

요소 5개, 요소마다 카드 1~2장, 요소당 항목 4개(2+2 또는 4). 요소 점수는 카드 항목의 합이다. 카드 시점은 `scenario-model.md`.

| 요소 id | 이름 | 카드 id | 장면 | 동료가 필요한 것 | 항목 수 |
|---|---|---|---|---|---|
| responsibility | 책임감/성실성 | responsibility_delay | 내 파트에 필요한 자료가 늦는다는 알림(지원자만 받음) | 상태 | 4 |
| planning | 계획성/꼼꼼함 | planning_division | 동료가 파트를 어떻게 나눌지 묻는다 | 결정 | 2 |
| | | planning_checkin | 동료가 초안 v1을 보내며 진행을 묻는다 | 반응 | 2 |
| adaptability | 적응성/유연성 | adaptability_change | 팀장이 핵심 기능 범위와 출시 일정을 바꾼다(마감 그대로) | 다시 정리된 방향 | 4 |
| collaboration | 협업/조율 | collab_help | 바쁜 시점에 동료가 10분만 같이 봐 달라고 한다 | 답 | 2 |
| | | collab_disagree | 리뷰 때 동료가 근거를 들어 지원자 결정에 다른 의견을 낸다(내용은 카탈로그 고정) | 들어 줌 | 2 |
| honesty | 정직/공정한 보고 | honesty_report | 팀장이 "다 됐다고 전해도 되죠?"와 함께 보고를 요청한다 | 인정 | 4 |

## 항목 정의

`when`은 조건, `only_if`는 판정 전제(불충족이면 기록 없음 `not_applicable`). 실력을 재는 항목은 없다. `basis`는 항목 값이 어디서 왔는지다: `metric`(기록을 규칙으로 센 값)·`label`(LLM 분류를 쓴 값, aux 기반 지표 포함). 리포트는 항목마다 이 구분을 "기록 기반 / AI 분류 기반"으로 보여 준다.

| 카드 | 항목 id | 문장 | when | basis | 근거 타입 |
|---|---|---|---|---|---|
| responsibility_delay | resp_notified_before_release | 자료가 공개되기 전에 지연을 팀이나 동료에게 알림 | metric notified_before_release eq true | metric | message |
| | resp_mentioned_impact | 지연이 동료 파트(3번은 2번에 의존)에 미치는 영향을 말함 | metric mentions_colleague_impact eq true, only_if metric impact_possible eq true | label | message |
| | resp_proposed_alternative | 지연 동안 먼저 할 작업이나 대안을 제시함 | metric proposes_alternative eq true | label | message |
| | resp_told_manager | 팀장이 보는 곳(팀 채널 또는 팀장 DM)에 지연을 알림 | metric notified_where_manager_sees eq true | metric | message |
| planning_division | plan_assigned_all_parts | 섹션 담당 5개 전부를 직접 정함 | metric division_by_candidate eq true | metric | task_event, message |
| | plan_stated_schedule | 누가·언제까지·어떤 순서인지 말하거나 할 일을 만들어 due_min·order를 적음(할 일이 없으면 채팅 레이블만) | metric stated_schedule eq true | metric(보드) 또는 label(채팅) | task_event, message |
| planning_checkin | plan_opened_draft | 동료가 보낸 초안을 열어 봄 | metric draft_opened eq true, only_if metric draft_delivered eq true | metric | open |
| | plan_responded_draft | 초안에 대해 반응(의견·확인)을 남김 | label_in [feedback, acknowledge], only_if metric draft_delivered eq true | label | message |
| adaptability_change | adapt_applied_to_doc | 바뀐 대상을 내 문서(파트 또는 최종본)에 반영함 | all [metric document_changed_after eq true, metric target_applied eq true] | label | document, share |
| | adapt_no_complaint_to_colleague | 불만을 동료에게 쏟지 않음 | label_in [replan_and_apply, apply_silently] | label | message, document |
| | adapt_redirected_colleague | 동료 파트에 무엇이 바뀌는지 다시 정리해 줌 | metric redirected_colleague eq true | metric | message |
| | adapt_raised_scope | 범위·일정·분담 재조정을 말함 | metric mentions_scope_or_division eq true | label | message |
| collab_help | collab_help_offered | 바로 돕거나 도울 시점을 제시함 | label_in [help_now, negotiate_timing] | label | message |
| | collab_help_kept_promise | 제안한 시점에 실제로 동료를 찾아감 | metric promise_kept eq true, only_if label_in [help_now, negotiate_timing] | metric | message(창 밖 related_card 허용) |
| collab_disagree | collab_disagree_answered | 동료의 다른 의견에 답함 | metric responded_to_request eq true | metric | message |
| | collab_disagree_reasoned_or_accepted | 근거로 설명하거나 수용함(무시·강행·비난 아님) | label_in [explain_with_reason, accept] | label | message |
| honesty_report | honest_credited_colleague | 동료가 한 일을 동료 것으로 말함 | metric credits_colleague eq true, only_if metric has_colleague_shares eq true | label | message |
| | honest_disclosed_incomplete | 안 된 것을 숨기지 않음 | metric discloses_incomplete eq true, only_if metric has_incomplete_facts eq true | label | message |
| | honest_no_misattribution | 동료가 쓴 파트를 자기 것으로 말하지 않음 | metric claims_colleague_work eq false, only_if all [metric has_report_message eq true, metric has_colleague_shares eq true] | label | message |
| | honest_reported_within_10m | 요청 후 10분 안에 보고함 (pilot_value) | metric response_minutes lte 10 | metric | message |

## 카드별 레이블·보조 판정·근거 타입 (단일 정본)

레이블은 카드마다 상호 배타이고 판정 우선순위는 `prompts/observe_labels.md`다. `aux`는 LLM 분류가 레이블과 함께 돌려주는 보조 판정이며, 모든 카드가 `related_message_ids`(관련 메시지 id 목록)를 공통으로 가진다. 근거 타입은 7개뿐이고 각 id는 같은 세션의 해당 테이블 행이다.

| 근거 타입 | 원천 테이블 | 뜻 |
|---|---|---|
| message | messages | 지원자 메시지(창 밖은 related_card가 이 카드일 때만) |
| document | document_revisions | 지원자 문서(파트·최종본)의 자동 저장 스냅샷 |
| share | document_shares | 지원자가 보낸 버전 |
| open | document_opens | 지원자가 동료 문서를 연 기록 |
| task_event | task_events | 보드 변경(할 일)과 섹션 담당 변경(target=section_owner) |
| doc_view | doc_views | 회사 문서 열람 |
| assistant_call | assistant_calls | 어시스턴트 호출 |

| 카드 | 레이블 | aux 키 | 허용 근거 타입 |
|---|---|---|---|
| planning_division | assign_with_schedule, assign_only, defer_to_colleague, ignore | mentions_schedule(순서·시점 언급) | task_event, message |
| planning_checkin | feedback, acknowledge, ignore | — | open, message |
| collab_help | help_now, negotiate_timing, decline, acknowledge_only, ignore | promised_t_min(제안 시점을 세션 분으로 환산, 없으면 null), is_specific(시점이 분 단위로 환산 가능한지) | message |
| collab_disagree | explain_with_reason, accept, dismiss, blame | — | message |
| responsibility_delay | notify_with_alternative, notify_only, silent, ask_colleague | mentions_impact(의존 파트·동료 일정 영향 언급), has_alternative(먼저 할 일·대안 제시) | message, doc_view |
| adaptability_change | replan_and_apply, apply_silently, complain_then_apply, refuse_or_ignore | target_applied(바뀐 대상이 문서에 반영됐는지 예/아니오, 품질 아님), mentions_scope(범위·일정·분담 재조정 언급) | message, document, share, task_event |
| honesty_report | fair_report, hides_incomplete, misattributes, no_report | credits_colleague, claims_colleague_work, discloses_incomplete(사실 입력과 대조) | message |

레이블 주석: `complain_then_apply`는 동료에게 **비난·거부** 표현을 한 뒤 반영한 경우에만 쓴다. "팀장님 왜 이러시지" 수준의 한탄은 `replan_and_apply`·`apply_silently`로 본다. `apply_silently`의 근거는 document 또는 share다(말없이 반영은 문서 근거로 증명). `negotiate_timing`은 `is_specific=true`일 때만이고, 시점이 불명확하면 `acknowledge_only`다.

## 항목 값과 요소 점수

| 관찰 행 상태 | 레이블 기반 항목(`label_in` 포함) | metric 기반 항목 |
|---|---|---|
| 카드 레이블 | 조건대로 1/0 | 조건대로 1/0 |
| `unclassified` / null(LLM 실패) | 기록 없음(null) | 조건대로 1/0 (metrics는 순수 함수) |
| `no_evidence` / 관찰 행 없음 | 기록 없음 | 기록 없음 |
| metric 값이 null | — | 기록 없음. 단 `response_minutes`는 창 안 활동이 있는데 관련 메시지가 없으면 0 |
| `only_if` 불충족 | 기록 없음(사유 not_applicable) | 동일 |
| 카드 메시지가 창 끝에 늦게 전달됨 | 기록 없음(사유 window_missed) | 동일 |
| 카드가 의존하는 동료 문서가 전달되지 않음 | 기록 없음(사유 document_missing) | 동일 |

기록 없음에는 항상 사유를 붙인다. 리포트와 화면은 사유 코드가 아니라 책임 주체가 보이는 문장을 쓴다:

| 사유 코드 | 뜻 | 표시 문장 |
|---|---|---|
| no_activity | 창 안에 지원자 활동 없음(무응답 자체는 점수에 넣지 않음) | 지원자 활동 없음 |
| classify_failed | LLM 실패·unclassified | 시스템: 분류 실패 |
| window_missed | 카드 메시지 전달 지연으로 창을 놓침 | 시스템: 메시지 지연 |
| document_missing | 동료 문서 전송 실패로 카드가 의존하는 문서가 없음 | 시스템: 문서 미제공 |
| not_applicable | `only_if` 전제 불충족 | 해당 없음 |
| event_not_fired | 카드 미발생(조기 제출 등) | 이벤트 미발생 |

0점(미충족)은 근거 행을 요구하지 않는다.

- 요소 점수 = 요소의 카드 항목을 합쳐 충족·미충족·기록 없음 세 수. 표기 `충족 3 · 미충족 1 · 기록 없음 0`. 분모(만점) 표기는 하지 않는다. 리포트는 요소 섹션 안에 카드 소섹션을 둔다.
- 합계 = 선택 요소의 세 수 합. 표기 `충족 12 · 미충족 4 · 기록 없음 2 (요소 5개)`. 가중치·정규화 없음. 만점은 선택 요소 수 × 4이므로 요소 구성이 같으면 같은 기준이고 다르면 만점이 다르다.
- 리포트 맨 위에 요소별 한 줄 관찰·세 수 요약표(`summary`)를 둔다. 카드 소섹션은 접힘이 기본이다.
- 담당자 조정: 항목을 1/0/null로 바꿀 수 있고 바꾸면 메모 필수. 최종값 = 조정 행이 있으면 reviewer_value(null 포함), 없으면 자동 값. 요청에 같은 item_id가 두 번 오면 400. 조정 저장·합계·approving 전이는 한 트랜잭션. 검토 완료 뒤 값 재조정은 409이고, 메모 추가(`POST /admin/sessions/{id}/report/notes`)만 허용한다. 검토 제출에는 검토자 이름(`reviewer_name`)이 들어간다. 조정 메모는 해당 관찰 문장 옆에도 표시해 자동 서술과 담당자 정정이 함께 보이게 한다. 조정 행은 card_id를 함께 갖는다.
- 지원자 목록: 요소별 세 수 칩과 합계, 출처(`auto`/`reviewer`). 헤더에 "요소 구성이 같으면 같은 기준, 다르면 만점이 다르다" 한 줄. 점수 정렬 없음.
- 정직 카드 소섹션에는 "미완료는 최종본 섹션 기준이며, 사용자가 만든 할 일의 미완료는 참고 사실이다" 주석을 붙인다.
- ai_usage와 산출물 품질은 점수화하지 않는다.

## 조건 문법 (`when`)

`label_in: [..]`, `metric: <이름>` + `eq: <값>` 또는 `lte: <수>`, `all: [조건, ...]`. 세 가지뿐이다. 한 항목에 `label_in`과 `metric`이 함께 있으면 둘 다 충족해야 한다. `only_if`에도 같은 문법을 쓴다. 정직 항목의 전제는 metric `has_colleague_shares`·`has_incomplete_facts`·`has_report_message`로 표현한다.

## 지표 정의 (observe `compute_metrics`)

입력: 창 안의 지원자 메시지(각 메시지의 `meta.classification`: recipient, kind, related_card 포함, `meta.reply_to_doc`가 있으면 문서에 매인 답글), 지원자 문서의 자동 저장(document_revisions)과 보낸 버전(document_shares), 받은 문서 열기(document_opens), 보드 변경(task_events), 회사 문서 열람(doc_views), 어시스턴트 호출. "관련 메시지" = classification.related_card가 이 카드이거나 LLM 분류의 `aux.related_message_ids`에 든 메시지. 창 밖 근거는 **메시지 타입만** related_card로 허용한다(약속 이행·지연 대응). 각 지표는 `{value, evidence_ids}`를 돌려준다.

| 지표 | 타입 | 정의 |
|---|---|---|
| response_minutes | float·null | 카드 메시지 시각부터 **관련** 지원자 메시지 중 첫 것까지 분. 관련 메시지 없으면 null(활동은 있으면 0점 처리) |
| first_recipient | manager·colleague·null | 첫 관련 메시지의 recipient |
| responded_to_request | bool | 관련 메시지가 1건 이상 |
| division_by_candidate | bool | 계획성: 창 안에 `decided_by=candidate` 스냅샷이 확정되고 섹션 담당 5개 전부가 non-null임. 할 일 생성 여부와 무관하다. 섹션 담당 draft를 지원자가 직접 바꾼 것과 채팅으로 정해 동료 set_division이 쓴 draft를 지원자가 공유한 것을 같게 본다 |
| stated_schedule | bool | 계획성: 창 안 task_events에 지원자가 적은 due_min이 있거나, order 변경이 2건 이상이거나, 관련 메시지가 순서·시점을 말함(aux.mentions_schedule) |
| draft_delivered | bool | 계획성: 카드의 동료 초안 문서(doc, version)가 실제로 전송됨(send_document 성공). false면 사유 document_missing |
| draft_opened | bool | 계획성: 카드로 보낸 동료 초안(doc, version)에 지원자 document_opens가 창 안에 있음 |
| promise_kept | bool·null | 협업: help_now면 true. negotiate_timing이면 제안 시각(aux.promised_t_min) ±5분 안에 동료 DM 관련 메시지가 있음(창 밖 허용). 그 외 null. **창 닫힘 시점에는 null로 저장하고 세션 종료(finalize)에서 다시 계산해 갱신한다**(아래) |
| notified_before_release | bool | 책임감: 자료 공개 시각(release_at_min) 전에 지연을 언급한 관련 메시지가 있음 |
| notified_where_manager_sees | bool | 책임감: 팀 채널 또는 팀장 DM에 지연을 언급한 관련 메시지가 있음(팀장이 보는 곳) |
| impact_possible | bool | 책임감: 확정 division에서 3번이 colleague 또는 both임(2번 지연이 동료 파트에 영향을 줄 수 있음). false면 영향 항목은 not_applicable |
| mentions_colleague_impact | bool·null | 책임감: aux.mentions_impact |
| proposes_alternative | bool·null | 책임감: aux.has_alternative |
| doc_opened_after_release | bool | 공개 뒤 해당 회사 문서 doc_view가 있음(점수 무관 사실) |
| document_changed_after | bool | 적응성: 카드 이후 지원자 문서(파트 또는 최종본)에 새 revision이나 share가 있음 |
| target_applied | bool·null | 적응성: aux.target_applied(바뀐 대상이 그 revision·share 본문에 반영됐는지. 품질 아님) |
| mentions_scope_or_division | bool·null | 적응성: aux.mentions_scope |
| redirected_colleague | bool | 적응성: recipient=colleague이고 kind ∈ {redivide, instruction}인 메시지가 창 안에 있음(동료 수락 여부 무관, 팀장에게 한 제안은 제외) |
| has_colleague_shares | bool | 정직: facts.shares에 owner=colleague 행이 1개 이상 |
| has_incomplete_facts | bool | 정직: facts.empty_sections가 비어 있지 않거나 facts.section_owners에 draft_differs=true가 있거나 facts.changed_after_adaptability가 false임(tasks_not_done은 여기서 세지 않는 추가 사실)(null은 세지 않음) |
| has_report_message | bool | 정직: 완료(submitted_at) 뒤 창 안에 한서윤 manager_dm의 지원자 메시지 중 kind=report가 있음. 팀 채널 메시지와 완료 전 메시지는 보고로 세지 않음(2026-10-21 후속) |
| credits_colleague | bool·null | 정직: aux.credits_colleague(보고 문장이 동료가 보낸 문서의 파트를 동료 몫으로 말함). 사실 입력과 대조 |
| claims_colleague_work | bool·null | 정직: aux.claims_colleague_work(동료가 보낸 파트를 자기 것으로 말함) |
| discloses_incomplete | bool·null | 정직: aux.discloses_incomplete(사실 입력의 미완료 항목 중 하나 이상을 보고에서 말함) |

정직 카드의 **사실 입력**은 api가 규칙으로 만들고(내부 `GET /honesty_facts`) observe가 LLM에 함께 준다(점수 계산은 규칙): `shares`(문서별 주인·보낸 버전·시각), `final_sections`(source_doc_id·version·edited), `section_owners`(확정 snapshot의 섹션 담당과 현재 draft의 차이), `empty_sections`(본문이 비어 있는 최종본 섹션 part_no 목록), `tasks_not_done`(사용자가 만든 할 일 중 done이 아닌 것. 추가 사실로만 보이며 점수에 넣지 않음), `changed_after_adaptability`(적응성 카드 이후 주담당 문서 revision·share 유무. 적응성 미선택이면 null이며 미완료로 보지 않음). 품질 판단은 없다.

**약속 이행의 확정**: collab_help 창을 닫을 때 `promise_kept`는 null로 저장한다. 세션 종료 run(finalize)에서 related_card=collab_help인 메시지로 다시 계산해 그 지표만 `update_observation`(내부 PATCH observations, `metrics_patch`)으로 갱신한다. 같은 run_id의 재실행은 멱등이다. 워커는 갱신된 값을 읽는다.

**계획성 창의 시작**: planning_division 카드는 L/12에 동료가 묻지만 관찰 창은 세션 시작(0)부터 첫 중간 카드까지다. 카드 전에 보드·채팅으로 정한 분업도 같은 창 안이라 먼저 결정한 경우와 카드 뒤에 결정한 경우의 판정이 같다.

점수 무관 근거(`flag`): `aux_facts`로 지정된 지표(doc_opened_after_release 등)는 `aux_fact`, 창 밖 관련 메시지(related_card가 이 카드인데 창 밖)는 `out_of_window`로 같은 근거 목록에 "점수 무관" 표시로 둔다. 근거 항목마다 직전 동료·팀장 메시지 1개와 카드 발생 시각을 맥락으로 붙이고, 전체 기록의 해당 시점으로 가는 `record_ref`를 단다(점수 아님).

## 리스크와 파일럿 측정

- 한 창에 레이블 하나라 오분류 1번이 1~2점을 움직인다. 항목마다 근거와 basis(기록 기반/AI 분류 기반)를 보여 주고 담당자가 조정한다. 파일럿에서 **담당자 조정 비율**을 근거 정확도와 함께 잰다.
- 응답 시간 기준(5분·10분)과 약속 이행 허용 오차(±5분)는 파일럿 값이다.
- 요소를 적게 고르면 창이 길어지고 만점이 줄어든다. 요소 구성이 같은 채용 건끼리만 같은 기준이다.
- 반대 의견 카드의 내용은 카탈로그에 고정되어 지원자 간 공정하다. 지원자가 3번 파트를 쓰지 않았으면(50자 미만) 대체 대상(분업 때 정한 방향 또는 킥오프 기본 가정)에 대해 말한다.
- 분업 최소 조건(`division_min`: 2번은 지원자, 3번은 동료 또는 같이, 4·5번 중 하나는 동료 단독)으로 책임감·정직 카드의 전제가 모든 분업에서 성립한다. 그래도 영향이 없는 분업이면 해당 항목은 not_applicable이다.
- 접속 끊김 구간(`connection_gaps`)은 점수에 넣지 않고 리포트에 사실로 표시한다.

MVP 제외: 가중치, 채용 건 간 비교·정규화, 점수 정렬·통계, 검토 후 값 재조정, 기업별 항목 편집, 지원자에게 점수 공개, ai_usage 점수화.
