# 인터페이스 계약

병렬 트랙의 공용 기준. 트랙은 이 파일을 바꾸지 않는다. 바꿔야 하면 오케스트레이터에 올린다. 예시 JSON은 mock 서버와 테스트 픽스처의 정본이다. 관찰 레이블·aux·근거 타입의 이름은 `rubric.md`의 단일 표를 따른다.

## 공통

- 공개 베이스: `http://api:8000` (web이 호출). 내부 베이스: `http://api:8001` (`/internal/*`만, compose 네트워크 안에서만 열림, 포트 미공개).
- 응답 JSON. 오류는 `{"error": {"code": "...", "message": "..."}}`와 HTTP 4xx/5xx. 입력 검증 실패는 422.
- CORS: 공개 앱(8000)만 `WEB_ORIGIN`(쉼표 구분, 기본 `http://localhost:3000`)을 허용한다. 메서드 전부, 헤더 `Authorization`·`Content-Type`. 내부 앱(8001)에는 두지 않는다.
- 인증 헤더: `Authorization: Bearer <jwt>`. 내부: `X-Internal-Token: <secret>`.
- 시각은 ISO 8601 UTC. 세션 상대 시각은 `t_min`(세션 시작 기준 분, 소수 허용)으로도 함께 준다.
- 멱등: MVP는 `Idempotency-Key` 헤더를 쓰지 않는다. 멱등은 도메인 규칙(세션 전이, 리뷰 본문 비교, 아래 내부 저장 키)으로만 보장하며 화면은 채용 건·초대 생성 POST를 자동 재시도하지 않는다. 내부 저장의 멱등 키: 메시지 `(session_id, run_id, seq)`, 동료 문서 보내기 `(doc_id, run_id)`(문서 카드 메시지는 같은 run_id에 파트별 고정 seq = 파트 번호×10), 보드 변경 `(session_id, part_no, field, run_id)`, 관찰 `(session_id, card_id, window_start)`, 관찰 갱신 `(session_id, card_id, window_start, run_id)`. 같은 키의 재요청은 기존 행을 돌려준다.

## 인증 생명주기

| 단계 | 호출 | 상태 | 토큰 |
|---|---|---|---|
| 초대 생성 | 관리자 POST /invites | sessions 행이 `invited`로 함께 생성됨 | 초대 토큰(링크에만, DB에는 해시) |
| 링크 입장 | GET /s/{token} | 시작 전 만료(72h) → 410, 취소 → 410 `cancelled`. completed 이후·failed → 200에 `status`와 `debrief_token`(디브리핑·종료 안내·최종본 열람·설문만 읽고 쓰는 JWT, 종료 후 7일). 입장 화면 고정 안내: 2시간 연속 진행·중간 휴식 없음·PC 권장·업무는 가상 회사 루프랩에서·지원자는 이번 건의 주담당(파트를 나누고 최종본을 모아 보고)·끊겨도 시간은 흐름·외부 도구 사용은 막지 않되 안의 어시스턴트만 기록됨·문의 창구(담당자 이메일) | 없음 |
| 동의 | POST /s/{token}/consent | `consented_at` 기록 | 세션 JWT 발급. 만료 = now + session_minutes + 120분 |
| 시작 | POST /s/{token}/start (Bearer) | `in_progress`, started_at·ends_at 확정, 이벤트·공개 예약·지원자 파트 문서와 최종본 행·보드 5행(assignee=null) 생성. 동의 후라도 시작 시점에 초대가 만료(72h)됐으면 410 `expired` | 같은 JWT |
| 재입장 | GET /s/{token} → status가 invited면 POST /s/{token}/consent 재호출, in_progress·reporting이면 POST /s/{token}/resume | 변화 없음 | 세션 JWT 재발급(저장된 JWT가 없어도 링크만으로 이어감). reporting이면 state에 `deadline_at`이 있어 보고 대기 화면을 복원한다. 초대 72h 만료는 시작 후에는 적용하지 않음 |
| 종료 | submit 또는 timeout → `reporting`(보고 요청, 보고 메시지 또는 submitted_at+5분까지) → `completed`(completed_at 저장) | `completed` | JWT는 디브리핑 조회까지 유효 |

검증: 다른 세션 id 접근 403, 동의 중복 호출은 멱등(새 JWT 재발급), 같은 초대의 동의는 시작 전까지 몇 번이든 허용하고 시작 후에는 409, 시작 전 JWT 만료는 `/consent` 재호출로, 시작 후 만료는 `/resume`으로 복구(in_progress·reporting 모두).

## 관리자 REST (`/admin`, 포트 8000)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | /admin/auth/signup | {email, password, company_name} | {token}. 이미 있는 이메일은 409 `conflict` |
| POST | /admin/auth/login | {email, password} | {token}. 실패는 401 `unauthorized` |
| GET | /admin/catalog | | {missions: [{id, name, company_name, deliverable, documents: [{doc_id, title}]}], elements: [{id, name, meaning, how_we_see, if_unselected}], candidate_notice_template, candidate_faq: [{q, a}], session_minutes} (채용 건 생성 화면: 요소 카드 5장에 이름·한 줄 뜻·"이렇게 봅니다"·요소를 뺐을 때 달라지는 것 한 줄. 기본은 전체 선택. 상황·시점·평가표 항목은 보여 주지 않는다) |
| GET | /admin/positions | | [{id, name, mission_id, elements, candidate_count(초대된 사람 수, 세션 수 아님), created_at}] |
| POST | /admin/positions | {name, elements: ["responsibility", ...], mission_id?: "planning"} (요소 1~5개, mission_id 기본 `planning`) | {id, name, mission_id, elements, scenario, catalog_version} |
| GET | /admin/positions/{id}/candidates | | [{session_id, alias, email, status, display_status, display_group, invited_at, started_at?, ends_at?, last_activity_at?, message_count, report_ready_at?, purge_at?, failed_stage?, failed_reason?, next_action?, previous_session_id?, previous_relation?: "retry"∣"reissue", met?, unmet?, no_record?, score_source?: "auto"∣"reviewer", by_element?: [{element, met, unmet, no_record}]}] (display_status는 status에 만료(invited이고 expires_at 지남)·취소를 더한 표시값, display_group ∈ waiting∣in_progress∣needs_review∣done∣problem은 화면의 다섯 묶음·필터 키. purge_at은 completed_at+90일. next_action은 failed일 때 담당자 행동 안내 문자열("새 초대를 만들어 보내세요"∣"리포트를 다시 생성하세요"). report 없으면 met·unmet·no_record·score_source·by_element는 null, 정렬은 초대순) |
| POST | /admin/positions/{id}/invites | {alias, email, previous_session_id?} | {session_id, invite_url, expires_at, notice_text}. 발송하지 않음. 화면은 링크 복사와 안내 문안 복사(2시간·PC 권장·중간 휴식 없음·72시간 만료·가상 회사 루프랩) 버튼과 별칭 설명("지원자에게 이 이름으로 안내되고 리포트에 이 이름이 남습니다"). 같은 채용 건 안 같은 별칭은 409 `conflict`. previous_session_id는 그 세션이 failed(failed_stage=session)·만료(invited이고 expires_at 지남)·cancelled일 때만 허용하고 아니면 422 `invalid_previous_session`. 만료 초대의 재발행은 previous_relation=reissue(연장), 실패·취소 뒤는 retry(재응시)로 목록에 표시 |
| POST | /admin/sessions/{id}/cancel | | {status: "cancelled"}. invited·in_progress·reporting에서 허용(시작 후 취소 = 중도 포기, 리포트 없음, WS `session.ended{cancelled}`), 그 외 409 |
| GET | /admin/sessions/{id}/report | | Report (아래) 또는 404(아직 없음) |
| POST | /admin/sessions/{id}/report/regenerate | | {status: "completed"}. failed_stage=report인 세션만. 상태를 completed로 되돌리고 `report.generate`를 다시 발행(attempt 1). 그 외 409 |
| POST | /admin/sessions/{id}/review | {adjustments: [{item_id, value: 1∣0∣null, memo}], memo?, reviewer_name} | {status: "approving"}. 생략한 항목은 자동 값. item_id가 이 채용 건 rubric에 없으면 400 `invalid_item`, 자동 값과 다른데 memo 없으면 400 `memo_required`. 같은 item_id가 두 번이면 400 `duplicate_item`. reviewer_name이 비어 있으면 422. 이미 approving·reviewed이고 본문 동일이면 200 멱등(현재 status를 돌려줌), 다르면 409 `already_reviewed`. **오류 우선순위**: 이미 제출된 세션은 `already_reviewed`(409)가 본문 검증 오류(400)보다 먼저다. report가 없거나 status가 report_ready·approving·reviewed가 아니면 409 `conflict`. 화면은 "검토 완료 후 점수는 바꿀 수 없습니다" 확인 창을 거치고, 확정 실패 시 "조정은 저장되어 있고 확정만 다시 시도합니다"를 보여 준다 |
| POST | /admin/sessions/{id}/report/notes | {text, reviewer_name} | {notes: [{id, text, reviewer_name, created_at}]}. 검토 완료 뒤(approving·reviewed) 메모 추가. 값은 바꾸지 않는다. 그 외 상태는 409 |
| GET | /admin/sessions/{id}/record | | [{t_min, type: message∣share∣open∣task_event∣assistant_call∣notice∣connection_gap, channel?, by, summary, ref: {type, id, t_min}}] (전체 기록 읽기 전용. 대화(채널별, 카드 메시지 포함)·문서 보내기/열기·보드 변경·어시스턴트 호출·알림·접속 끊김을 t_min 순 한 목록으로. `ref`는 리포트 근거의 `record_ref`와 같은 값이라 화면이 그 위치로 이동(하이라이트)할 수 있다) |

`elements` 검증: 카탈로그 id만, 중복 없음, 1~5개. 위반 시 422 `invalid_elements`. `mission_id`가 카탈로그에 없으면 422 `invalid_mission`. 모든 조회는 JWT의 company_id로 필터. 샘플 리포트는 API가 아니라 web의 정적 픽스처(`apps/web/fixtures/sample-report.json`, Report 형식과 동일)이며 생성 화면과 리포트 목록에서 링크한다. 인쇄·PDF 내보내기는 web의 인쇄 CSS(브라우저 PDF)다.

### Report

```json
{"session_id":"...","alias":"지원자A","stage":"draft",
 "position":{"name":"...","mission_id":"planning","elements":["responsibility","collaboration"]},
 "summary":[{"element":"responsibility","name":"책임감/성실성","line":"공개 전에 지연을 알리고 대안을 제시함","met":3,"unmet":1,"no_record":0},
            {"element":"collaboration","name":"협업/조율","line":null,"met":0,"unmet":0,"no_record":4}],
 "deliverable":{
   "final":{"sections":[{"part_no":1,"title":"문제 정의와 대상 사용자","content":"...","source_doc_id":"...","source_owner":"candidate","source_version":2,"edited":true,"source_content":null},
                        {"part_no":4,"title":"비슷한 서비스 사례","content":"...","source_doc_id":"...","source_owner":"colleague","source_version":2,"edited":true,"source_content":"(동료 v2 원문)"}],
            "submitted_version":1},
   "documents":[{"doc_id":"...","owner":"candidate","part_no":2,"title":"사용자 인터뷰에서 찾은 근거","versions":2,"shares":[{"version":1,"channel":"dm","t_min":48}],"empty":false},
                {"doc_id":"...","owner":"colleague","part_no":4,"title":"비슷한 서비스 사례","versions":2,"shares":[{"version":1,"channel":"team","t_min":45},{"version":2,"channel":"team","t_min":90}],"opened_by_candidate":[1,2]}],
   "division_decided_by":"candidate",
   "final_report_message":{"id":"...","t_min":112,"content":"..."}},
 "rubric":{"elements":[{"element":"responsibility","name":"책임감/성실성",
    "auto":{"met":3,"unmet":1,"no_record":0},
    "cards":[{"card_id":"responsibility_delay","name":"내 자료 지연",
      "items":[{"id":"resp_notified_before_release","text":"자료가 공개되기 전에 지연을 팀이나 동료에게 알림","basis":"metric","auto":1,"reviewer":null,"memo":null,"adjusted":false,"no_record_reason":null,
                "evidence":[{"type":"message","id":"...","t_min":62,"record_ref":{"type":"message","id":"...","t_min":62}}]}]}]}],
   "auto_total":{"met":12,"unmet":4,"no_record":2},"reviewer_total":null,"review":null},
 "sections":[
  {"element":"responsibility","name":"책임감/성실성",
   "cards":[{"card_id":"responsibility_delay","name":"내 자료 지연","situation":"담당 파트에 필요한 인터뷰 자료 지연","event_fired":true,"card_at_t_min":60,"window":{"start_min":60,"end_min":70},
     "observed":"공개 전에 지연을 먼저 알리고 대안을 제시함","no_record_reason":null,"note":null,
     "evidence":[{"type":"message","id":"...","t_min":62,"channel":"team","quote":"인터뷰 자료가 늦어서...",
                  "context":{"prev_persona_message":"한서윤 · 60분: ...","card_at_t_min":60},"record_ref":{"type":"message","id":"...","t_min":62}},
                 {"type":"share","id":"...","t_min":84,"doc_id":"...","part_no":1,"version":2,"summary":"1번 파트 v2 보냄(84분)","context":{"prev_persona_message":null,"card_at_t_min":60},"record_ref":{"type":"share","id":"...","t_min":84}},
                 {"type":"doc_view","id":"...","t_min":71,"doc_id":"interview_summary","summary":"인터뷰 요약 열람(71분)","flag":"aux_fact","context":{"prev_persona_message":null,"card_at_t_min":60},"record_ref":null}]}]},
  {"element":"collaboration","name":"협업/조율",
   "cards":[{"card_id":"collab_help","name":"도움 요청","situation":"...","event_fired":true,"card_at_t_min":30,"observed":null,"no_record_reason":"no_activity","evidence":[],
             "note":"지원자 활동 없음"},
            {"card_id":"collab_disagree","name":"반대 의견","situation":"...","event_fired":true,"card_at_t_min":90,"observed":"...","no_record_reason":null,"note":null,"evidence":[]}]}],
 "ai_usage":{"used":true,
   "events":[{"call_id":"...","t_min":41,"request_quote":"...","response_quote":"...","cited_doc_ids":["metrics"],"applied_part":4},
            {"call_id":"...","t_min":47,"request_quote":"...","response_quote":"...","cited_doc_ids":[],"applied_part":null}]},
 "notes":[],
 "connection_gaps":[{"from_t_min":31.2,"to_t_min":46.0}],
 "generated_at":"...","reviewed_at":null,"purge_at":"..."}
```

`summary`는 요소별 한 줄 관찰(`line`: 그 요소 카드의 observed를 이은 한 문장, 전부 기록 없음이면 null)과 met·unmet·no_record 세 수다(목록·요소 합계와 같은 표기). `rubric.elements[].cards[].items[]`는 `basis`(`metric`∣`label`, 리포트 표시 "기록 기반 / AI 분류 기반"), `reviewer`·`memo`(조정된 항목만 값), `adjusted: bool`(null 조정과 무조정의 구분), `no_record_reason`을 갖고, basis가 label인 항목은 판정 창의 지원자 메시지를 met·unmet과 무관하게 `evidence[]`에 싣는다(없으면 no_record). 카드 소섹션의 `window {start_min, end_min}`은 관찰 창이며 화면이 `connection_gaps`와 겹침을 표시한다. `reviewer_total`·`review {memo, reviewer_name, reviewed_at}`는 리뷰 제출(approving) 뒤에만 non-null이고, 최상위 `notes[] {id, text, reviewer_name, created_at}`는 검토 완료 뒤 추가한 메모다. 요소별 reviewer 소계와 조정 이력 배열은 없다(항목의 reviewer·memo로 충분). 요소의 `auto`는 그 요소 카드 항목의 합이다. `stage`는 draft 또는 final. evidence 타입은 `rubric.md`의 7개: message(quote, channel, `reply_to_doc`가 있으면 문서에 매인 답글), document(doc_id, part_no∣"final", revision, summary: 자동 저장), share(doc_id, part_no, version, summary), open(doc_id, version, summary), task_event(part_no, field, summary), doc_view(doc_id, summary), assistant_call(quote). 모든 evidence는 `context`와 `record_ref {type, id, t_min}`(전체 기록 `GET /admin/sessions/{id}/record`의 `ref`와 같은 값. 기록 목록에 없는 document·doc_view 타입은 null)를 가지고, 점수 무관 근거는 `flag ∈ aux_fact∣out_of_window`(선택 필드, 점수에 쓰인 근거에는 없음)로 표시한다. `ai_usage.used=false`면 events는 빈 배열이고 화면은 "사용하지 않음"을 보여 준다. `ai_usage`는 머리에 "판단 기준 없음, 면접 확인용"을 두고 `events[] {call_id, t_min, request_quote, response_quote, cited_doc_ids, applied_part}`(반영된 파트는 제출 시 재사용 추정으로 계산, 없으면 null)를 시간순 사실로만 보여 준다(분류 라벨·비율 없음). 모든 evidence의 id는 같은 세션의 실제 행을 가리켜야 하며(워커가 검증), `rubric.auto`는 워커가 draft에 넣고 `reviewer`·`review`·`notes`는 api가 GET 때 `rubric_adjustments`·`report_notes`에서 병합한다. 해시 규칙은 저장된 `reports.content`(불변)에만 적용되고 GET 합성 응답과는 무관하다. `deliverable`은 api가 GET 때 붙이며 `{final, documents, division_decided_by, final_report_message: {id, t_min, content}}`를 포함한다(최종본 섹션별 "어느 문서 v몇에서 가져옴"·주담당 편집 여부·편집한 섹션은 동료 원문 `source_content`를 나란히, 주고받은 문서 목록). honesty_report 소섹션은 `facts`(내부 `GET /honesty_facts` 응답 그대로)를 사실로 함께 보여 주고 "미완료는 보드 기준" 주석을 붙인다. 응답 시간 항목은 실제 분 값을 함께 보여 준다. `connection_gaps`와 `purge_at`(삭제 예정일, completed_at+90일)은 api가 GET 때 붙인다. `observed`·`note`·`summary[].observed` 텍스트 필드에는 합격·순위 표현과 평가표 밖의 점수 표현이 없어야 한다(워커 금지어 검사 범위는 텍스트 필드만).

워커 산출 필드 형태 (실제 출력 예: `services/report-worker/tests/fixtures/report_sample.json`):

| 위치 | 필드 | 형태 |
|---|---|---|
| 요약 | `summary[]` | `{element, name, line, met, unmet, no_record}` |
| 카드 소섹션 | `event_fired` | bool. 세션 조회 `events`에서 그 카드 행의 status가 fired·done이면 true |
| 카드 소섹션 | `card_at_t_min` | 실제 카드 메시지 시각(분). 그 이벤트 id의 첫 메시지 시각이며 지연 전달이면 지연된 시각. 미발생이면 null |
| 카드 소섹션 | `no_record_reason` | `no_activity`∣`classify_failed`∣`event_not_fired`∣`window_missed`∣`document_missing`∣null |
| 카드 소섹션 | `note` | 기록 없음·미분류·미발생일 때만 `rubric.md` 사유 표시 문장 |
| 카드 소섹션(honesty_report) | `facts` | 내부 `GET /honesty_facts` 응답 그대로 |
| 섹션 근거 | `flag` | `aux_fact`(aux_facts 지표의 근거)∣`out_of_window`(창 밖 관련 메시지). 점수에 쓰인 근거에는 없음 |
| 섹션 근거 | `context.prev_persona_message` | 문자열 `"<보낸이 이름> · <t>분: <본문>"`(근거 직전의 동료·팀장 메시지), 없으면 null |
| 섹션 근거 | `context.card_at_t_min` | 카드 소섹션의 `card_at_t_min`과 같은 값 |
| 섹션 근거 | `record_ref` | `{type, id, t_min}`. 근거와 같은 type·id, document·doc_view는 null |
| 섹션 근거 | document `summary`, share `summary`, open `summary`, task_event `summary`, doc_view `summary` | `"n번 파트 편집(t분)"`, `"n번 파트 v2 보냄(t분)"`, `"동료 n번 v1 열람(t분)"`, `"n번 <필드 한국어> → <새 값>(t분)"`(예: "1번 담당 → 지원자(12분)", "1번 언제까지 → 40분(15분)"), `"<문서명> 열람(t분)"` |
| 평가표 항목 | `basis` | `metric`∣`label` (카탈로그 rubric의 basis). 카탈로그가 `by_source`인 항목(plan_stated_schedule)은 워커가 충족시킨 근거로 정한다: task_event면 `metric`, 메시지 레이블·aux면 `label` |
| 평가표 항목 | `no_record_reason` | auto가 null일 때 사유(`not_applicable` 포함), 아니면 null |
| 평가표 항목 | `minutes` | 응답 시간(response_minutes) 항목에만. 실제 분, 관련 메시지가 없으면 null(0점 처리와 구분) |
| AI 활용 | `events[]` | `{call_id, t_min, request_quote, response_quote, cited_doc_ids, applied_part: part_no∣"final"∣null}` 시간순. applied_part는 내부 `GET /assistant_reuse`에서 applied=true인 파트(여러 개면 ratio 최대) |

## 지원자 REST (`/s`, `/sessions`, 포트 8000)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | /s/{token} | | {company_name, duration_minutes, status, elements_names, entry_notice, contact_email, debrief_token?, failed_stage?} 또는 410 `expired`∣`cancelled`. debrief_token은 completed 이후·failed일 때만 |
| POST | /s/{token}/consent | | {session_token} |
| POST | /s/{token}/resume | | {session_token} (status in_progress·reporting일 때만, 아니면 409) |
| POST | /s/{token}/start | Bearer | {session_id, started_at, ends_at} (이미 시작했으면 같은 값 멱등) |
| GET | /sessions/{id}/state | Bearer | State 스냅샷 |
| GET | /sessions/{id}/my-documents | Bearer | {documents: [{doc_id, part_no, title, content, updated_at, revision, versions: [{version, revision, channel, message_id, t_min}]}], received: [{doc_id, owner: "colleague", part_no, title, versions: [{version, channel, message_id, t_min, opened: bool}]}], final: {sections: [{part_no, title, content, source_doc_id, source_version, edited}], updated_at}} |
| GET | /sessions/{id}/my-documents/{part_no∣final} | Bearer | 파트 문서 {doc_id, part_no, title, content, updated_at, revision, versions} 또는 최종본 {sections, updated_at} |
| PUT | /sessions/{id}/my-documents/{part_no∣final} | Bearer {content} (final은 {sections: [{part_no, content}]}) | {updated_at, revision}. 디바운스 저장이며 version을 만들지 않는다. 저장마다 `document_revisions`에 스냅샷을 append(최종본 섹션 편집·가져오기 포함). final은 바뀐 섹션만 edited=true |
| POST | /sessions/{id}/my-documents/{part_no}/share | Bearer {channel: "team"∣"dm", note?} | {version, message_id}. 현재 content로 새 version을 만들고(현재 revision을 가리킴) 채널에 문서 카드 메시지(meta.shared_doc)를 올린다. 메시지 본문은 지원자가 쓴 `note`뿐이며 없으면 빈 문자열(시스템이 지원자 발화를 만들지 않는다) |
| POST | /sessions/{id}/documents/{doc_id}/open | Bearer {version} | {doc_id, owner, part_no, title, version, content, t_min}. 동료가 보낸 버전만(아니면 404 `not_found`), `document_opens`에 기록. doc_id는 받은 문서의 UUID(회사 문서 id가 아님). 화면은 최신 버전을 기본으로 열고 이전 버전은 목록에서 열람만 한다(버전 비교 없음) |
| PUT | /sessions/{id}/final/sections/{part_no}/import | Bearer {source_doc_id, version} | section. 그 버전 내용을 최종본 섹션에 덮어쓰고 source_doc_id·source_version 기록, edited=false("가져오기", 동료 문서는 보낸 버전만, 내 문서는 아무 버전이며 `version: null`이면 보내지 않은 현재 저장본). 이미 내용이 있으면 화면이 덮어쓰기 확인을 받는다. `document_revisions`에도 남는다 |
| PUT | /sessions/{id}/tasks/{part_no} | Bearer {assignee?: "candidate"∣"colleague"∣"both"∣null, status?, order?, due_min?} | task. 모든 카드 변경 가능(주담당). 바뀐 필드마다 `task_events`(by=candidate) 기록. 5행의 assignee가 다 차고 `division_min`을 만족하는 순간 api가 division을 확정한다(decided_by=candidate, WS `division.confirmed`, 동료 그래프 stimulus). 다 채우는 PUT이 `division_min`을 어기면 422 `invalid_division`(조건 문장 포함)이고 저장하지 않는다. 확정 뒤 재배정도 같은 규칙으로 기록·검증한다. due_min은 세션 분이며 화면은 남은 시간 프리셋("30분 뒤", "마감 10분 전")으로 입력받는다 |
| GET | /sessions/{id}/documents | Bearer | [{doc_id, title, released: bool, release_at_min: number∣null}] (회사 문서. release_at_min은 지연 공개 예정 시각, 공개됐거나 시작 공개면 null) |
| GET | /sessions/{id}/documents/{doc_id} | Bearer | {doc_id, title, content} 또는 423 `not_released`. 열람을 `doc_views`에 기록 |
| POST | /sessions/{id}/assistant | Bearer {prompt} | {call_id, message_id, content, cited_docs} 또는 429 `assistant_limit`(60회 초과) |
| POST | /sessions/{id}/submit | Bearer | {status: "reporting"∣"completed", deadline_at?} (멱등. 이미 completed 이후면 현재 status). web은 "제출 후에는 수정할 수 없고 남은 시간과 상관없이 세션이 끝납니다. 팀장에게 보고한 뒤 종료됩니다" 확인 창 뒤 대기 중인 저장을 끝내고 호출한다. 만료 2분 전에는 "지금 상태 그대로 제출됩니다" 경고. submitted_at 이후의 문서·최종본·보드 PUT·share·import·open·assistant는 409 `session_ending`. 메시지는 모든 채널에서 계속 보낼 수 있다. 보고 요청 뒤 팀 채널 또는 팀장 DM의 지원자 메시지가 `meta.classification.kind = report`로 저장되거나 submitted_at+5분(deadline_at)이 지나면 `completed`. 요청 뒤 제출 전에 이미 보고했으면 제출 즉시 completed |
| GET | /sessions/{id}/debrief | Bearer(세션 JWT 또는 debrief_token) | {events: [{card_id, element, name, description, rubric_items: [text]}] (실제 fired된 카드만, 평가표 항목 문장 포함), persona_note(동료가 회사 인재상 페르소나였다는 설명과 values), scoring_notice(점수를 보여 주지 않는 이유·기업이 보는 것·리모트 맥락), connection_gaps: [{from_t_min, to_t_min}], retention_notice, contact_email, final: {sections: [{part_no, title, content}]}∣null, final_view_until(종료 후 7일), survey: {submitted: bool, questions: [{q, text}]}, failed_stage?: "session"∣"report"}. 세션 실패(failed_stage=session)면 events·final 없이 중단 안내와 재응시 안내만 돌려준다(연출 노출 방지, 재응시 가능) |
| POST | /sessions/{id}/debrief/survey | Bearer(세션 JWT 또는 debrief_token) {answers: [{q: "natural"∣"fair", value: 1~5}]} | {submitted: true}. 종료 설문 2문항(자연스러웠는지·공정했는지). 한 번만 저장하고 재요청은 기존 값(멱등) |

### State 스냅샷

```json
{"session":{"id":"...","alias":"지원자A","status":"in_progress","started_at":"...","ends_at":"...","remaining_seconds":5400,"deadline_at":null,"completed_at":null},
 "division":{"parts":{"1":"candidate","2":"candidate","3":"both","4":"colleague","5":"colleague"},"decided_by":"candidate","decided_at":"..."},
 "messages":[{"id":"...","channel":"team","sender":"manager","content":"...","event_id":null,"run_id":"...","t_min":0.0,"created_at":"...","reply_to_doc":null,"shared_doc":null}],
 "my_documents":[{"doc_id":"...","part_no":1,"title":"문제 정의와 대상 사용자","content":"...","updated_at":"...","revision":3,"versions":[]}],
 "received":[{"doc_id":"...","owner":"colleague","part_no":4,"title":"비슷한 서비스 사례","versions":[{"version":1,"channel":"team","message_id":"...","t_min":45.0,"opened":false}]}],
 "final":{"sections":[{"part_no":1,"title":"문제 정의와 대상 사용자","content":"","source_doc_id":null,"source_version":null,"edited":false}],"template":{"length":"섹션당 5~10줄, 1~2쪽"}},
 "tasks":[{"part_no":1,"assignee":"candidate","status":"doing","order":1,"due_min":40,"depends_on":[]},{"part_no":3,"assignee":null,"status":"todo","order":3,"due_min":null,"depends_on":[2]}],
 "documents":[{"doc_id":"metrics","title":"지표 현황","released":true,"release_at_min":null},{"doc_id":"interview_summary","title":"사용자 인터뷰 요약","released":false,"release_at_min":70}],
 "assistant":[{"call_id":"...","request":"...","response":"...","cited_docs":["metrics"],"t_min":41.2}],
 "active_runs":[{"run_id":"...","actor":"colleague","node":"respond"}],
 "connection_gaps":[{"from_t_min":31.2,"to_t_min":46.0}],
 "channels":{"team":{"members":["manager","colleague","candidate"]},"dm":{"members":["colleague","candidate"]},"manager_dm":{"members":["manager","candidate"]},"notice":{"members":["candidate"]}},
 "persona":{"manager":"한서윤 팀장","colleague":"이도현","candidate_role":"주담당"}}
```

재접속 복구 범위: 스냅샷이 전체 상태이고 WS는 증분만 보낸다. `division`은 미확정이면 null이다. `active_runs`는 `agent_runs`에서 status=started인 행이다. 완료된 실행은 messages의 run_id로 식별한다. ack 뒤 실행 시작 전에 api가 죽은 메시지는 `agent_runs`에 started로 남아 있으므로 스케줄러가 120초 뒤 같은 run_id로 재실행한다. `connection_gaps`는 in_progress·reporting 동안 WS 연결이 없던 구간(끊김부터 재연결 또는 종료까지)이며 화면은 재접속 시 시스템 줄("00:31~00:46 연결이 끊겼어요")로 보여 준다. 점수에 넣지 않는다.

### 지원자 경로 보충

- 알 수 없는 초대 토큰: `/s/{token}` 계열 전부 404 `not_found`.
- 디브리핑 기한 = 세션 종료 시각 + 7일. 종료 시각은 completed_at(보고 종료), 진행 중 실패면 실패 시각(`fail(session)`이 ends_at을 그 시각으로 당긴다). `debrief_token`의 exp는 이 기한으로 고정되고(발급할 때마다 늘어나지 않음), 기한이 지나면 `GET /s/{token}`과 `GET /sessions/{id}/debrief`는 410 `expired`. 최종본 열람·설문도 같은 기한이다.
- 세션 실패(failed_stage=session) 디브리핑: `{"events": [], "persona_note": null, "scoring_notice": "<중단 안내·재응시 안내>", "final": null, "final_view_until": null, "survey": {"submitted": false, "questions": []}, "failed_stage": "session"}`. 연출·페르소나 설명은 비운다.
- 지원자 문서 권한: 편집·보내기는 내 문서(owner=candidate)만이고 분업과 무관하다(동료 단독 파트의 지원자 문서도 존재하지만 쓰지 않으면 빈 채로 남는다). 동료 문서는 보낸 버전만 읽을 수 있다. 저장은 세션 Lock 안에서 하므로 제출 처리와 겹치면 저장되지 않고 409 `session_ending`.
- 문서에 매인 답글: `message.send`에 `reply_to_doc {doc_id, version}`를 붙이면 채널에 "n번 vK에 대한 답" 표시가 붙은 일반 메시지로 저장된다(`meta.reply_to_doc`). 공유로 올라간 문서 카드 메시지는 `meta.shared_doc {doc_id, version}`를 가진다. 인라인 코멘트·스레드는 없다.
- 팀장 DM(`manager_dm`)은 상시 열려 있다. 팀장은 과제 맥락·조건·배경 질문에 답하고, 정답·판단 요청은 "주담당이 정해 주세요"로 돌린다.
- 시작 공개 문서(`releases_at_start`)는 start 응답 시점에 이미 released다. 지연 공개만 스케줄러가 기록하고 `document.released`를 보낸다. `notice` 채널의 지연 알림은 보낸 사람 "리서치 담당"·수신자 "나에게만"으로 표시하고, 공개 시 같은 채널에 "공개됨" 줄이 온다.
- 편집 중 새 메시지는 토스트(보낸 사람·첫 줄)로 보여 주고, 어시스턴트 응답에는 복사 버튼을 둔다. 오피스 안 "?"로 대기 화면 설명을 다시 볼 수 있다.

## WebSocket `/ws/sessions/{id}?token=<세션 JWT>`

서버 → 클라이언트:

| type | payload |
|---|---|
| message.ack | {client_msg_id, message_id, run_id} (지원자 메시지 접수 확인. run_id는 이 메시지로 시작된 에이전트 실행) |
| message.new | Message = {id, channel, sender, content, event_id, run_id, t_min, created_at, reply_to_doc?: {doc_id, version}, shared_doc?: {doc_id, version}} |
| agent.progress | {run_id, actor: "colleague"∣"manager"∣"assistant", node, status: "started"∣"tool_start"∣"tool_end"∣"finished"∣"failed", tool?} |
| document.released | {doc_id, title} |
| document.shared | {doc_id, version, part_no, by: "candidate"∣"colleague", channel, message_id} (문서를 보냄. 활동 줄 "도현님이 4번 v1을 보냈어요". 열람은 WS 없이 REST open만) |
| task.updated | {part_no, assignee, status, order, due_min, by: "candidate"∣"colleague"} |
| division.confirmed | {parts, decided_by: "candidate"∣"colleague_default", t_min} (5행이 다 차고 조건을 만족해 확정됨, 또는 동료 기본안 확정) |
| session.reporting | {deadline_at} (보고 대기 시작, submitted_at+5분 상한) |
| session.ended | {reason: "submitted"∣"timeout"∣"failed"∣"cancelled"} |

클라이언트 → 서버:

| type | payload |
|---|---|
| message.send | {client_msg_id, channel: "team"∣"dm"∣"manager_dm", content, reply_to_doc?: {doc_id, version}}. 같은 client_msg_id 재전송은 기존 메시지로 ack(저장 시 (session_id, client_msg_id) unique). reporting 중에도 모든 채널을 허용하고(채널 잠금 없음), completed 이후는 전부 `session_ending` |

프레임은 서버·클라이언트 모두 봉투 `{"type": <위 표의 이름>, "payload": {...}}`다. 예: `{"type": "message.ack", "payload": {"client_msg_id": "c-1", "message_id": "...", "run_id": "..."}}`.

같은 세션에 WS가 둘 이상 붙으면 마지막 연결만 유효하고 이전 연결은 `{"type": "session.replaced", "payload": {}}`를 받은 뒤 close code 4000으로 닫힌다. `notice` 채널 메시지(책임감 알림)는 지원자에게만 전달되고 페르소나 컨텍스트에는 들어가지 않는다. 연결이 없는 구간은 api가 `connection_gaps`에 기록한다.

`event_id`가 있는 message.new는 이벤트 카드 실행의 결과다(러너가 카드 발생을 감지하는 기준). 진행 상태 이름은 위 다섯 가지로 고정한다.

연결 거절과 오류 프레임:

| close code | 뜻 | 클라이언트 동작 |
|---|---|---|
| 4401 | 토큰 없음·만료·위조 | `POST /s/{token}/resume`으로 세션 JWT를 다시 받고 재연결 |
| 4403 | 다른 세션의 토큰 | 재연결하지 않음 |
| 4000 | 같은 세션의 새 연결로 교체됨(`session.replaced` 뒤) | 재연결하지 않음 |

클라이언트 프레임 처리 오류는 `{"type": "error", "payload": {"code": ..., "message": ...}}`. code: `session_ending`(completed 이후 전부), `conflict`(진행 중이 아님), `invalid_input`(JSON 아님·알 수 없는 type·payload 검증 실패·reply_to_doc가 보낸 버전이 아님).

## 내부 REST (`/internal`, 포트 8001, X-Internal-Token)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | /internal/sessions/{id} | | {id, status, position: {mission_id, elements, scenario, catalog_version}, division, started_at, ends_at, submitted_at, reported_at, completed_at, deadline_at, t_min_now, current_card, connection_gaps: [{from_t_min, to_t_min}], events: [{id, card_id, element, status, due_at, fired_at, document_missing: bool}]} (events는 session_events 전 행, due_at 순. 워커가 카드 발생·실제 카드 시각(같은 event_id의 메시지)·전달 지연·문서 미제공을 판단) |
| GET | /internal/sessions/{id}/messages?since_t_min=&channel=&limit=&offset= | | [Message + `meta`] (내부 API 전용으로 `meta`(classification 포함)를 더함. 공개 API의 Message에는 meta가 없다. since_t_min은 소수 분. 정렬 created_at·seq·id, limit 기본 200·최대 1000, offset 기본 0. 워커는 limit 500으로 offset 페이지를 끝까지 읽는다) |
| POST | /internal/sessions/{id}/messages | {channel, sender, content, event_id?, run_id, seq, meta?} | Message (같은 run_id+seq 재요청은 기존 행) |
| GET | /internal/sessions/{id}/board | | {tasks: [{part_no, assignee, status, order, due_min, depends_on}]} (assignee는 미배정이면 null) |
| PUT | /internal/sessions/{id}/tasks/{part_no} | {status, run_id} | task. 동료 담당(colleague·both)이 아니면 403 `forbidden`. 동료 카드는 분업 확정 시 doing, 리뷰 공유 시 done으로 그래프가 바꾼다. `task_events`에 by=colleague로 기록, (part_no, field, run_id) 멱등 |
| GET | /internal/sessions/{id}/task_events | | [{id, part_no, by, field, old_value, new_value, created_at}] |
| GET | /internal/sessions/{id}/honesty_facts | | {shares: [{doc_id, owner, part_no, versions: [{version, channel, t_min}]}], final_sections: [{part_no, source_doc_id, source_version, edited}], tasks: [{part_no, assignee, status}], empty_sections: [part_no], tasks_not_done: [part_no], changed_after_adaptability: bool∣null} (정직 사실 입력. api가 계산하고 observe가 honesty_report 창에서 읽어 LLM에 주고 `observations.facts`에 저장, 워커는 리포트 `facts`에 그대로 싣는다. changed_after_adaptability는 적응성 미선택이면 null) |
| PUT | /internal/sessions/{id}/division | {parts, decided_by: "candidate"∣"colleague_default", run_id} | {division}. in_progress가 아니면 409. 전 파트 지정을 요구하고 누락·`division_min`(2번 candidate, 3번 colleague 또는 both, 4·5 중 하나 이상 colleague 단독) 위반은 422 `invalid_division`. 확정과 동시에 `tasks`의 assignee를 채우고 바뀐 행마다 `task_events`(by=colleague, run_id 멱등)를 기록하며 WS `division.confirmed`를 보낸다(한 트랜잭션). 같은 내용의 재요청은 저장된 값을 그대로 돌려준다. 보드 PUT으로 지원자가 이미 확정한 뒤의 호출은 재배정으로 처리한다 |
| GET | /internal/sessions/{id}/docs | | {documents: [{doc_id, owner, part_no, final, title, content, revision, updated_at, versions: [{id, version, revision, content, created_at}], shares: [{id, version, channel, message_id, created_at}], opens: [{id, version, by, created_at}]}], final: {sections}} (워커·observe용 전체) |
| GET | /internal/sessions/{id}/document_revisions?doc_id=&since_t_min= | | [{id, doc_id, part_no∣"final", revision, by, length, diff_ratio, content, created_at, t_min}] (자동 저장 스냅샷 이력. observe와 재사용 추정이 읽는다) |
| GET | /internal/sessions/{id}/docs/shared | | {documents: [{doc_id, owner, part_no, title, versions: [{version, content, created_at}]}]} (지원자 문서는 **보낸 버전만**, 동료 문서는 전부. 페르소나 컨텍스트용) |
| POST | /internal/sessions/{id}/docs/send | {doc_id∣part_no, content, channel: "team"∣"dm", run_id, event_id?, seq} | {doc_id, version, message_id}. 동료 문서(part_no만 주면 없을 때 생성)에 새 version을 만들고 문서 카드 메시지 1건(event_id·run_id·seq)을 올린다. seq는 파트별 고정(파트 번호×10). 같은 doc_id+run_id 재요청은 기존 version·메시지. 동료 문서가 아니거나 part_no가 동료 담당(colleague·both)이 아니면 403 `forbidden` |
| GET | /internal/sessions/{id}/documents | | {catalog_version, documents: [{doc_id, title, released, release_at_min}]} (rag-mcp가 공개 여부와 색인 버전 확인에 사용) |
| POST | /internal/sessions/{id}/releases/{doc_id} | | {released_at} (멱등). 공개 시 `notice` 채널에 "공개됨" 시스템 메시지도 저장한다 |
| POST | /internal/sessions/{id}/observations | {card_id, element, window_start, window_end, metrics, label, aux?, evidence: [{type: message∣document∣share∣open∣task_event∣doc_view∣assistant_call, id}], facts?, run_id} | {id}. 같은 card_id+window_start 재요청은 기존 행. evidence의 각 id가 이 세션의 해당 테이블 행(`rubric.md` 근거 타입 표)이 아니면 422. metrics는 `{<지표>: {value, evidence_ids}}`. 카드 메시지 전달이 늦어 창을 놓쳤으면 `metrics.window_missed: {value: true, evidence_ids: []}`(bool true도 허용)를 남기고, 워커는 그 카드 항목 전부를 사유 window_missed로 둔다 |
| PATCH | /internal/sessions/{id}/observations | {card_id, window_start, metrics_patch: {<지표>: {value, evidence_ids}}, run_id} | observation. 지정한 지표만 갱신(세션 종료 finalize의 `promise_kept`). 같은 card_id+window_start+run_id 재요청은 멱등. 관찰 행이 없으면 404 |
| GET | /internal/sessions/{id}/observations | | [...] |
| GET | /internal/sessions/{id}/assistant_calls | | [{id, request_message_id, response_message_id, cited_doc_ids, created_at}] |
| PUT | /internal/sessions/{id}/messages/{message_id}/classification | {recipient, kind, instruction?, related_card?, reply_to_doc?: {document_id, version}} | Message. 그래프가 respond 앞 분류 결과를 저장(meta.classification). 멱등 |
| GET | /internal/sessions/{id}/assistant_reuse | | [{call_id, doc_id, part_no∣"final", applied: bool}] (제출 후에만 값이 있음. 응답이 그 호출 이후 지원자 문서 revision에 반영됐는지 추정. 비율은 내부 계산값이며 응답에 싣지 않는다) |
| GET | /internal/sessions/{id}/doc_views | | [{id, doc_id, viewed_at}] |
| POST | /internal/sessions/{id}/complete | | {status: "completed", completed_at} (reporting 세션을 보고 종료로 넘김. 보고 메시지(`meta.classification.kind = report`) 저장 뒤 그래프가, deadline_at 경과 시 스케줄러가 호출. 멱등) |
| POST | /internal/sessions/{id}/report/draft | {content, usage?} | {status: "report_ready"} (멱등). usage(워커 LLM 사용량 `{model, llm_calls, retries, tokens_in, tokens_out, latency_ms, fallback_used}`)는 `reports.usage`에 저장, 재전달은 최초 값 유지. 해시는 content에만 |
| POST | /internal/sessions/{id}/report/final | {content} | {status: "reviewed", reviewed_at}. content의 정규화 JSON 해시(`reports.content_hash`, 키 정렬·공백 제거)가 승인된 draft 해시와 다르면 409 `draft_mismatch`. 이미 reviewed이고 해시가 같으면 200 기존 값(재전달 멱등). draft가 없거나 status가 approving·reviewed가 아니면 409 |
| POST | /internal/sessions/{id}/report_failed | {error} | {status: "failed"} |
| POST | /internal/test/sessions | {elements, session_minutes, mission_id?, alias?} | {session_id, token, invite_url} (`ENABLE_TEST_API=1`일 때만. `token`은 초대 토큰 원문이며 세션 JWT가 아니다. consent·start를 거쳐야 한다) |

권한·상태 검증(담당자, 세션 상태, 문서 공개 여부)은 모두 api가 최종 판단한다. MCP는 전달만 한다. 내부 문서·task·분업 쓰기는 세션이 in_progress일 때만 받고 아니면 409 `conflict`(이미 저장된 run_id 재전달은 기존 결과).

## MCP 도구

### business-mcp (`http://business-mcp:9101/mcp`)

| 도구 | 입력 | 출력 data | 구분 |
|---|---|---|---|
| get_session | {session_id} | 내부 GET /sessions/{id} | 조회 |
| list_messages | {session_id, since_t_min?, channel?, limit?=50} | [Message] | 조회 |
| get_board | {session_id} | {tasks} | 조회 |
| get_shared_documents | {session_id} | 내부 GET /docs/shared (지원자 문서는 보낸 버전만) | 조회 |
| post_message | {session_id, channel, sender ∈ colleague∣manager∣system, content, event_id?, run_id, seq, meta?} | Message | 변경 |
| set_division | {session_id, parts, decided_by, run_id} | {division} (tasks도 함께 채움) | 변경 |
| update_task | {session_id, part_no, status, run_id} | task (상태만) | 변경 |
| send_document | {session_id, doc_id∣part_no, content, channel, run_id, event_id?, seq} | {doc_id, version, message_id} (동료 문서 쓰기·보내기, doc_id+run_id 멱등, seq는 파트 번호×10) | 변경 |
| release_document | {session_id, doc_id} | {released_at} | 변경 |
| record_observation | {session_id, card_id, element, window_start, window_end, metrics, label, aux?, evidence: [{type, id}], facts?, run_id} | {id} | 변경 |
| update_observation | {session_id, card_id, window_start, metrics_patch, run_id} | observation (내부 PATCH observations. 종료 finalize의 promise_kept 갱신) | 변경 |

### rag-mcp (`http://rag-mcp:9102/mcp`)

| 도구 | 입력 | 출력 data | 구분 |
|---|---|---|---|
| search_documents | {query, session_id, top_k?=3} | [{doc_id, title, chunk, score}]. 내부 GET /documents로 공개 여부 확인 후 공개된 문서만 | 조회 |
| get_document | {doc_id, session_id} | {doc_id, title, content}. 공개 전이면 `not_released` | 조회 |
| list_documents | {session_id} | [{doc_id, title, released}] | 조회 |
| reindex_documents | {mission_id?} | {indexed: n(색인된 청크 수), model, dim, catalog_version}. 미션(기본 `planning`)의 현재 카탈로그 버전으로 회사 문서를 색인(관리용). 다른 버전의 청크는 지우지 않음. 에이전트에는 노출하지 않음 | 변경 |

### 에이전트별 도구 허용 목록

| 그래프 | 허용 도구 | session_id |
|---|---|---|
| 세션 그래프 respond(동료) | search_documents, get_document, get_board, get_shared_documents | 그래프가 주입(모델이 바꿀 수 없음) |
| 세션 그래프 respond(팀장) | search_documents, get_board, get_shared_documents (회사 문서의 뜻 질문에 답하기 위한 검색) | 주입 |
| 세션 그래프 결정적 노드 | 나머지 business-mcp 변경 도구 (코드가 직접 호출) | 주입 |
| 어시스턴트 | search_documents, get_document | 주입 |
| 워커 | 없음 (내부 REST만) | — |

### 공통 응답 형식

```json
{"ok": true, "data": {...}}
{"ok": false, "error": {"code": "not_found", "message": "session not found", "retryable": false}}
```

코드: `invalid_input`, `not_found`, `forbidden`, `conflict`, `not_released`, `upstream_unavailable`(retryable), `internal`. 입력은 Pydantic으로 검증하고 모든 도구에 한 문단 설명과 인자 설명을 단다.

## 큐 메시지

| 큐 | 본문 | 발행 | 소비 |
|---|---|---|---|
| report.generate | {session_id, attempt} (attempt는 1부터. 최초 발행 1, 실패 시 +1로 재발행, 3에서도 실패하면 DLQ: 최초 포함 총 3회. approve도 같음) | api `complete()` 직후와 `POST /admin/sessions/{id}/report/regenerate`. 미발행 세션은 스케줄러가 60초마다 재탐색해 재발행 | 워커. draft 저장 성공 후 ack |
| report.approve | {session_id, attempt} | api `/admin/sessions/{id}/review`. 미발행(approve_enqueued_at null)은 스케줄러가 60초마다 재발행 | 워커. final 저장 성공 후 ack |
| report.dlq | 원본 + error | 워커(attempt ≥ 3) | 워커의 dlq 소비자가 `POST /internal/.../report_failed`를 호출한 뒤 ack(api가 내려가 있으면 ack하지 않고 60초 뒤 재시도). 메시지는 사람이 확인할 때까지 관리 UI에 남지 않으므로 error는 워커 로그에도 남김 |

메시지는 persistent, 발행은 publisher confirm을 켜고 브로커 확인을 받은 뒤에야 `*_enqueued_at`을 기록하거나(api) 원본을 ack한다(워커 재발행). 소비는 manual ack, 같은 session_id의 중복 메시지는 stage로 멱등 처리. 재시도는 nack 없이 `attempt+1`로 재발행(확인 후) → 원본 ack(지연은 워커의 백오프 대기: attempt 1·2·3 실패 뒤 각 5·15·45초, 3 실패는 대기 뒤 DLQ). RabbitMQ 데이터는 `rabbitdata` 볼륨에 남고, 브로커를 재생성해 큐가 비면 api 스케줄러의 outbox 재탐색이 미처리 세션을 다시 발행한다.
