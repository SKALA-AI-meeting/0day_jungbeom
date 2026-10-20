# 인터페이스 계약

병렬 트랙의 공용 기준. 트랙은 이 파일을 바꾸지 않는다. 바꿔야 하면 오케스트레이터에 올린다. 예시 JSON은 mock 서버와 테스트 픽스처의 정본이다.

## 공통

- 공개 베이스: `http://api:8000` (web이 호출). 내부 베이스: `http://api:8001` (`/internal/*`만, compose 네트워크 안에서만 열림, 포트 미공개).
- 응답 JSON. 오류는 `{"error": {"code": "...", "message": "..."}}`와 HTTP 4xx/5xx.
- CORS: 공개 앱(8000)만 `WEB_ORIGIN`(쉼표 구분, 기본 `http://localhost:3000`)을 허용한다. 메서드 전부, 헤더 `Authorization`·`Content-Type`. 내부 앱(8001)에는 두지 않는다.
- 인증 헤더: `Authorization: Bearer <jwt>`. 내부: `X-Internal-Token: <secret>`.
- 시각은 ISO 8601 UTC. 세션 상대 시각은 `t_min`(세션 시작 기준 분, 소수 허용)으로도 함께 준다.
- 멱등: MVP는 `Idempotency-Key` 헤더를 쓰지 않는다. 멱등은 도메인 규칙(세션 전이, 리뷰 본문 비교, 아래 내부 저장 키)으로만 보장하며 화면은 채용 건·초대 생성 POST를 자동 재시도하지 않는다. 내부 저장의 멱등 키: 메시지 `(session_id, run_id, seq)`, 문서 수정 `(session_id, part_no, run_id)`, 관찰 `(session_id, element, window_start)`. 같은 키의 재요청은 기존 행을 돌려준다.

## 인증 생명주기

| 단계 | 호출 | 상태 | 토큰 |
|---|---|---|---|
| 초대 생성 | 관리자 POST /invites | sessions 행이 `invited`로 함께 생성됨 | 초대 토큰(링크에만, DB에는 해시) |
| 링크 입장 | GET /s/{token} | 시작 전 만료(72h) → 410, 취소 → 410 `cancelled`. completed 이후·failed → 200에 `status`와 `debrief_token`(디브리핑·종료 안내만 읽는 JWT, 종료 후 7일). 입장 화면 고정 안내: 2시간 연속 진행·중간 휴식 없음·PC 권장·업무는 가상 회사 루프랩에서·지원자는 리드 역할 | 없음 |
| 동의 | POST /s/{token}/consent | `consented_at` 기록 | 세션 JWT 발급. 만료 = now + session_minutes + 120분 |
| 시작 | POST /s/{token}/start (Bearer) | `in_progress`, started_at·ends_at 확정, 이벤트·공개 예약·문서 파트 행 생성. 동의 후라도 시작 시점에 초대가 만료(72h)됐으면 410 `expired` | 같은 JWT |
| 재입장 | GET /s/{token} → status가 invited면 POST /s/{token}/consent 재호출, in_progress면 POST /s/{token}/resume | 변화 없음 | 세션 JWT 재발급(저장된 JWT가 없어도 링크만으로 이어감). 초대 72h 만료는 시작 후에는 적용하지 않음 |
| 종료 | submit 또는 timeout | `completed` | JWT는 디브리핑 조회까지 유효 |

검증: 다른 세션 id 접근 403, 동의 중복 호출은 멱등(새 JWT 재발급), 같은 초대의 동의는 시작 전까지 몇 번이든 허용하고 시작 후에는 409, 시작 전 JWT 만료는 `/consent` 재호출로, 시작 후 만료는 `/resume`으로 복구.

## 관리자 REST (`/admin`, 포트 8000)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | /admin/auth/signup | {email, password, company_name} | {token}. 이미 있는 이메일은 409 `conflict` |
| POST | /admin/auth/login | {email, password} | {token}. 실패는 401 `unauthorized` |
| GET | /admin/catalog | | {elements: [{id, name, situation_public, rubric: [{id, text, pilot_value}]}], timeline: {flow: [{card_id, at_fraction}], element_fraction_rule}, candidate_notice_template, session_minutes} (채용 건 생성 화면: 요소 설명·평가표 미리보기·선택 요소에 따른 타임라인(시각만)·지원자 안내 문안. pilot_value 항목은 툴팁 "시험 운영 기준") |

`/admin/catalog` 필드 출처: `situation_public`=카탈로그 카드의 `situation`, `pilot_value`=항목에 없으면 false, `timeline.flow`=흐름 카드의 `at_fraction`, `element_fraction_rule`=배치 규칙 설명 문자열, `candidate_notice_template`=자리표시자 `{alias}`·`{virtual_company}`·`{expires_at}`·`{invite_url}`를 가진 문자열 상수. 분업 PUT(`/internal/.../division`)은 전 파트 지정을 요구하고 누락·`division_min` 위반은 422 `invalid_division`, 확정과 동시에 `tasks` 행을 만든다(한 트랜잭션). 같은 내용의 재요청은 저장된 값을 그대로 돌려준다. 내부 문서·task·분업 쓰기는 세션이 in_progress일 때만 받고 아니면 409 `conflict`(이미 저장된 run_id 재전달은 기존 결과).
| GET | /admin/positions | | [{id, name, elements, candidate_count, created_at}] |
| POST | /admin/positions | {name, elements: ["cooperation", ...]} (1~4개) | {id, name, elements, scenario, catalog_version} |
| GET | /admin/positions/{id}/candidates | | [{session_id, alias, status, display_status, invited_at, report_ready_at, failed_stage?, failed_reason?, previous_session_id?, score?: {met, judged, no_record, source: "auto"∣"reviewer", by_element: [{element, met, judged}]}}] (display_status는 status에 만료(invited이고 expires_at 지남)·취소를 더한 표시값. report 없으면 score null, 정렬은 초대순) |
| POST | /admin/positions/{id}/invites | {alias, email, previous_session_id?} | {session_id, invite_url, expires_at, notice_text}. 발송하지 않음. 화면은 링크 복사와 안내 문안 복사(2시간·PC 권장·중간 휴식 없음·72시간 만료·가상 회사 루프랩) 버튼. previous_session_id는 재응시 연결 |
| POST | /admin/sessions/{id}/cancel | | {status: "cancelled"}. invited 상태에서만, 아니면 409 |
| GET | /admin/sessions/{id}/report | | Report (아래) 또는 404(아직 없음) |
| POST | /admin/sessions/{id}/review | {adjustments: [{item_id, value: 1∣0∣null, memo}], memo?} | {status: "approving"}. 생략한 항목은 자동 값. item_id가 이 채용 건 rubric에 없으면 400 `invalid_item`, 자동 값과 다른데 memo 없으면 400 `memo_required`. 같은 item_id가 두 번이면 400 `duplicate_item`. 이미 approving·reviewed이고 본문 동일이면 200 멱등(현재 status를 돌려줌), 다르면 409 `already_reviewed`. **오류 우선순위**: 이미 제출된 세션은 `already_reviewed`(409)가 본문 검증 오류(400)보다 먼저다. report가 없거나 status가 report_ready·approving·reviewed가 아니면 409 `conflict` |

`elements` 검증: 카탈로그 id만, 중복 없음, 1~4개. 위반 시 400 `invalid_elements`. 모든 조회는 JWT의 company_id로 필터.

### Report

```json
{"session_id":"...","alias":"지원자A","stage":"draft",
 "position":{"name":"...","elements":["cooperation","responsibility"]},
 "deliverable":{"parts":[{"part_no":1,"title":"문제 정의와 대상 사용자","assignee":"candidate","content":"...","revisions":4,"empty":false}]},
 "rubric":{"elements":[{"element":"responsibility","name":"책임감",
    "auto":{"met":3,"judged":4,"no_record":0},"reviewer":null,
    "items":[{"id":"resp_notified_before_release","text":"자료가 공개되기 전에 지연을 팀에 알림","auto":1,"reviewer":null,"memo":null,
              "evidence":[{"type":"message","id":"...","t_min":52}]}]}],
   "auto_total":{"met":9,"judged":14,"no_record":2},"reviewer_total":null,"review":null,"history":[]},
 "sections":[
  {"element":"responsibility","name":"책임감","situation":"담당 파트에 필요한 인터뷰 자료 지연",
   "observed":"마감 전에 지연을 먼저 알리고 대안을 제시함",
   "evidence":[{"type":"message","id":"...","t_min":52,"channel":"team","quote":"인터뷰 자료가 늦어서..."},
              {"type":"revision","id":"...","t_min":74,"part_no":1,"summary":"1번 파트 수정(대상을 휴면 참여자로)"}]},
  {"element":"cooperation","name":"협력 태도","situation":"...","observed":null,"evidence":[],
   "note":"해당 상황에서 관련 행동이 기록되지 않음"}],
 "ai_usage":{"used":true,"summary":"...",
   "evidence":[{"call_id":"...","t_min":41,"quote":"..."},{"call_id":"...","t_min":47,"part_no":4,"reuse":"edited"}]},
 "generated_at":"...","reviewed_at":null}
```

`rubric.elements[].items[]`는 `reviewer`·`memo`(조정된 항목만 값)와 `adjusted: bool`(null 조정과 무조정의 구분)을 갖고, 요소별 `reviewer {met, judged, no_record}`·`reviewer_total`·`review {memo, reviewed_at}`는 리뷰 제출(approving) 뒤에만 non-null이다. `history`는 `[{item_id, element, auto, reviewer, memo, created_at}]`. `stage`는 draft 또는 final. evidence 타입: message(quote), revision(part_no, summary), doc_view(doc_id), assistant_call(quote). `ai_usage.used=false`면 summary는 "사용하지 않음"이고 evidence는 빈 배열. 모든 evidence의 id는 같은 세션의 실제 행을 가리켜야 하며(워커가 검증), `rubric.auto`는 워커가 draft에 넣고 `reviewer`·`review`·`history`는 api가 GET 때 `rubric_adjustments`에서 병합한다. 해시 규칙은 저장된 `reports.content`(불변)에만 적용되고 GET 합성 응답과는 무관하다. `deliverable`은 api가 GET 때 붙이며 `{parts, division_decided_by, final_report_message: {id, t_min, content}}`를 포함한다. 각 요소 섹션에는 `no_record_reason`, `aux_facts`, `out_of_window_messages`(점수 무관), 근거마다 `context: {prev_persona_message, card_at_t_min}`, `event_fired: bool`(false면 "이벤트 미발생(조기 제출)")가 있다. `ai_usage`는 머리에 "판단 기준 없음, 면접 확인용"을 두고 위임·맥락·검증으로 나눠 보여 준다. 응답 시간 항목은 실제 분 값을 함께 보여 준다. `observed`·`note`·`summary` 텍스트 필드에는 합격·순위 표현과 평가표 밖의 점수 표현이 없어야 한다(워커 금지어 검사 범위는 텍스트 필드만).

## 지원자 REST (`/s`, `/sessions`, 포트 8000)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | /s/{token} | | {company_name, duration_minutes, status, elements_names, entry_notice, debrief_token?, failed_stage?} 또는 410 `expired`∣`cancelled`. debrief_token은 completed 이후·failed일 때만 |
| POST | /s/{token}/consent | | {session_token} |
| POST | /s/{token}/resume | | {session_token} (status in_progress일 때만, 아니면 409) |
| POST | /s/{token}/start | Bearer | {session_id, started_at, ends_at} (이미 시작했으면 같은 값 멱등) |
| GET | /sessions/{id}/state | Bearer | State 스냅샷 |
| PUT | /sessions/{id}/document/{part_no} | Bearer {content} | {updated_at, revision} |
| PUT | /sessions/{id}/tasks/{part_no} | Bearer {status} | task (지원자 담당 카드만, 아니면 403) |
| GET | /sessions/{id}/documents | Bearer | [{doc_id, title, released: bool}] |
| GET | /sessions/{id}/documents/{doc_id} | Bearer | {doc_id, title, content} 또는 423 `not_released`. 열람을 `doc_views`에 기록 |
| POST | /sessions/{id}/assistant | Bearer {prompt} | {call_id, message_id, content, cited_docs} 또는 429 `assistant_limit`(60회 초과) |
| POST | /sessions/{id}/submit | Bearer | {status: "completed"} (멱등). web은 "제출하면 세션이 끝납니다" 확인 창 뒤 대기 중인 문서 PUT을 끝내고 호출한다. submitted_at 이후의 문서 PUT·assistant·message.send는 409 `session_ending` |
| GET | /sessions/{id}/debrief | Bearer(세션 JWT 또는 debrief_token) | {events: [{element, name, description, rubric_items: [text]}] (실제 fired된 카드만, 평가표 항목 문장 포함), persona_note(동료가 회사 인재상 페르소나였다는 설명과 values), scoring_notice, failed_stage?: "session"∣"report"}. 세션 실패(failed_stage=session)면 events 없이 중단 안내만 돌려준다(연출 노출 방지, 재응시 가능) |

### State 스냅샷

```json
{"session":{"id":"...","status":"in_progress","started_at":"...","ends_at":"...","remaining_seconds":5400},
 "messages":[{"id":"...","channel":"team","sender":"manager","content":"...","event_id":null,"run_id":"...","t_min":0.0,"created_at":"..."}],
 "document":{"1":{"content":"...","revision":3,"updated_by":"candidate"},"2":{"content":"","revision":0,"updated_by":null}},
 "tasks":[{"part_no":1,"assignee":"candidate","status":"doing"}],
 "documents":[{"doc_id":"metrics","title":"지표 현황","released":true}],
 "assistant":[{"call_id":"...","request":"...","response":"...","cited_docs":["metrics"],"t_min":41.2}],
 "active_runs":[{"run_id":"...","actor":"colleague","node":"respond"}],
 "persona":{"manager":"한서윤 팀장","colleague":"이도현"}}
```

재접속 복구 범위: 스냅샷이 전체 상태이고 WS는 증분만 보낸다. `active_runs`는 `agent_runs`에서 status=started인 행이다. 완료된 실행은 messages의 run_id로 식별한다. ack 뒤 실행 시작 전에 api가 죽은 메시지는 `agent_runs`에 started로 남아 있으므로 스케줄러가 120초 뒤 같은 run_id로 재실행한다.

### 지원자 경로 보충 (2026-10-20 api-candidate 리뷰 반영)

- 알 수 없는 초대 토큰: `/s/{token}` 계열 전부 404 `not_found`.
- 디브리핑 기한 = 세션 종료 시각 + 7일. 종료 시각은 submitted_at(제출·만료), 진행 중 실패면 실패 시각(`fail(session)`이 ends_at을 그 시각으로 당긴다). `debrief_token`의 exp는 이 기한으로 고정되고(발급할 때마다 늘어나지 않음), 기한이 지나면 `GET /s/{token}`과 `GET /sessions/{id}/debrief`는 410 `expired`.
- 세션 실패(failed_stage=session) 디브리핑: `{"events": [], "persona_note": null, "scoring_notice": "<중단 안내>", "failed_stage": "session"}`. 연출·페르소나 설명은 비운다.
- 지원자 문서 PUT 권한: 분업 확정 전에는 모든 파트, 확정 뒤에는 `division.parts`에서 candidate·both인 파트만. colleague 단독 파트는 403 `forbidden`. 저장은 세션 Lock 안에서 하므로 제출 처리와 겹치면 저장되지 않고 409 `session_ending`.
- 시작 공개 문서(`releases_at_start`)는 start 응답 시점에 이미 released다. 지연 공개만 스케줄러가 기록하고 `document.released`를 보낸다.

## WebSocket `/ws/sessions/{id}?token=<세션 JWT>`

서버 → 클라이언트:

| type | payload |
|---|---|
| message.ack | {client_msg_id, message_id, run_id} (지원자 메시지 접수 확인. run_id는 이 메시지로 시작된 에이전트 실행) |
| message.new | Message = {id, channel, sender, content, event_id, run_id, t_min, created_at} |
| agent.progress | {run_id, actor: "colleague"∣"manager"∣"assistant", node, status: "started"∣"tool_start"∣"tool_end"∣"finished"∣"failed", tool?} |
| document.released | {doc_id, title} |
| document.part_updated | {part_no, content, revision, by: "colleague"} |
| task.updated | {part_no, assignee, status} |
| session.ended | {reason: "submitted"∣"timeout"∣"failed"} |

클라이언트 → 서버:

| type | payload |
|---|---|
| message.send | {client_msg_id, channel: "team"∣"dm", content}. 같은 client_msg_id 재전송은 기존 메시지로 ack(저장 시 (session_id, client_msg_id) unique). submitted_at 이후는 `error{code: session_ending}` |

프레임은 서버·클라이언트 모두 봉투 `{"type": <위 표의 이름>, "payload": {...}}`다. 예: `{"type": "message.ack", "payload": {"client_msg_id": "c-1", "message_id": "...", "run_id": "..."}}`.

같은 세션에 WS가 둘 이상 붙으면 마지막 연결만 유효하고 이전 연결은 `{"type": "session.replaced", "payload": {}}`를 받은 뒤 close code 4000으로 닫힌다. `notice` 채널 메시지(책임감 알림)는 지원자에게만 전달되고 페르소나 컨텍스트에는 들어가지 않는다.

`event_id`가 있는 message.new는 이벤트 카드 실행의 결과다(러너가 카드 발생을 감지하는 기준). 진행 상태 이름은 위 다섯 가지로 고정한다.

연결 거절과 오류 프레임 (2026-10-20 api-candidate 리뷰 반영):

| close code | 뜻 | 클라이언트 동작 |
|---|---|---|
| 4401 | 토큰 없음·만료·위조 | `POST /s/{token}/resume`으로 세션 JWT를 다시 받고 재연결 |
| 4403 | 다른 세션의 토큰 | 재연결하지 않음 |
| 4000 | 같은 세션의 새 연결로 교체됨(`session.replaced` 뒤) | 재연결하지 않음 |

클라이언트 프레임 처리 오류는 `{"type": "error", "payload": {"code": ..., "message": ...}}`. code: `session_ending`(submitted_at 이후 message.send, 상태가 completed 이후여도 같음), `conflict`(진행 중이 아님), `invalid_input`(JSON 아님·알 수 없는 type·payload 검증 실패).

## 내부 REST (`/internal`, 포트 8001, X-Internal-Token)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | /internal/sessions/{id} | | {id, status, position: {elements, scenario, catalog_version}, division, started_at, ends_at, t_min_now, current_element} |
| GET | /internal/sessions/{id}/messages?since_t_min=&channel=&limit= | | [Message + `meta`] (내부 API 전용으로 `meta`(classification 포함)를 더함. 공개 API의 Message에는 meta가 없다. since_t_min은 소수 분) |
| POST | /internal/sessions/{id}/messages | {channel, sender, content, event_id?, run_id, seq, meta?} | Message (같은 run_id+seq 재요청은 기존 행) |
| GET | /internal/sessions/{id}/board | | {tasks} |
| PUT | /internal/sessions/{id}/tasks/{part_no} | {status} | task. 동료 담당이 아니면 403 `forbidden`. 동료 카드는 분업 확정 시 doing, 리뷰 공유 시 done으로 그래프가 바꾼다 |
| PUT | /internal/sessions/{id}/division | {parts, decided_by: "candidate"∣"colleague_default"} | {division}. in_progress가 아니면 409. 최소 조건(2번 candidate, 4·5 중 하나 이상 colleague 단독) 위반은 422 |
| GET | /internal/sessions/{id}/document | | {"1": {content, revision, updated_by}, ...} |
| PUT | /internal/sessions/{id}/document/{part_no} | {content, by: "colleague", run_id} | {updated_at, revision}. 같은 part_no+run_id 재요청은 기존 revision. 동료 담당이 아니면 403 |
| GET | /internal/sessions/{id}/documents | | {catalog_version, documents: [{doc_id, title, released}]} (rag-mcp가 공개 여부와 색인 버전 확인에 사용) |
| POST | /internal/sessions/{id}/releases/{doc_id} | | {released_at} (멱등) |
| POST | /internal/sessions/{id}/observations | {element, window_start, window_end, metrics, label, evidence: [{type: message∣revision∣doc_view∣assistant_call, id}], run_id} | {id}. 같은 element+window_start 재요청은 기존 행. evidence의 각 id가 이 세션의 해당 테이블 행이 아니면 422 |
| GET | /internal/sessions/{id}/observations | | [...] |
| GET | /internal/sessions/{id}/assistant_calls | | [{id, request_message_id, response_message_id, cited_doc_ids, created_at}] |
| PUT | /internal/sessions/{id}/messages/{message_id}/classification | {recipient, kind, instruction?, related_card?} | Message. 그래프가 respond 앞 분류 결과를 저장(meta.classification). 멱등 |
| GET | /internal/sessions/{id}/assistant_reuse | | [{call_id, part_no, reuse, ratio}] (제출 후에만 값이 있음) |
| GET | /internal/sessions/{id}/document_revisions | | [{id, part_no, revision, by, content, length, diff_ratio, created_at}] |
| GET | /internal/sessions/{id}/doc_views | | [{id, doc_id, viewed_at}] |
| POST | /internal/sessions/{id}/report/draft | {content} | {status: "report_ready"} (멱등) |
| POST | /internal/sessions/{id}/report/final | {content} | {status: "reviewed", reviewed_at}. content의 정규화 JSON 해시(`reports.content_hash`, 키 정렬·공백 제거)가 승인된 draft 해시와 다르면 409 `draft_mismatch`. 이미 reviewed이고 해시가 같으면 200 기존 값(재전달 멱등). draft가 없거나 status가 approving·reviewed가 아니면 409 |
| POST | /internal/sessions/{id}/report_failed | {error} | {status: "failed"} |
| POST | /internal/test/sessions | {elements, session_minutes, alias?} | {session_id, token, invite_url} (`ENABLE_TEST_API=1`일 때만. `token`은 초대 토큰 원문이며 세션 JWT가 아니다. consent·start를 거쳐야 한다) |

권한·상태 검증(담당자, 세션 상태, 문서 공개 여부)은 모두 api가 최종 판단한다. MCP는 전달만 한다.

## MCP 도구

### business-mcp (`http://business-mcp:9101/mcp`)

| 도구 | 입력 | 출력 data | 구분 |
|---|---|---|---|
| get_session | {session_id} | 내부 GET /sessions/{id} | 조회 |
| list_messages | {session_id, since_t_min?, channel?, limit?=50} | [Message] | 조회 |
| get_board | {session_id} | {tasks} | 조회 |
| get_document_state | {session_id} | 내부 GET /document | 조회 |
| post_message | {session_id, channel, sender ∈ colleague∣manager∣system, content, event_id?, run_id, seq, meta?} | Message | 변경 |
| set_division | {session_id, parts, decided_by} | {division} | 변경 |
| update_task | {session_id, part_no, status} | task | 변경 |
| write_document_part | {session_id, part_no, content, run_id} | {updated_at, revision} | 변경 |
| release_document | {session_id, doc_id} | {released_at} | 변경 |
| record_observation | {session_id, element, window_start, window_end, metrics, label, evidence: [{type, id}], run_id} | {id} | 변경 |

### rag-mcp (`http://rag-mcp:9102/mcp`)

| 도구 | 입력 | 출력 data | 구분 |
|---|---|---|---|
| search_documents | {query, session_id, top_k?=3} | [{doc_id, title, chunk, score}]. 내부 GET /documents로 공개 여부 확인 후 공개된 문서만 | 조회 |
| get_document | {doc_id, session_id} | {doc_id, title, content}. 공개 전이면 `not_released` | 조회 |
| list_documents | {session_id} | [{doc_id, title, released}] | 조회 |
| reindex_documents | {} | {indexed: n(색인된 청크 수), model, dim, catalog_version}. 현재 카탈로그 버전으로 고정 문서 5개를 색인(관리용). 다른 버전의 청크는 지우지 않음. 에이전트에는 노출하지 않음 | 변경 |

### 에이전트별 도구 허용 목록

| 그래프 | 허용 도구 | session_id |
|---|---|---|
| 세션 그래프 respond | search_documents, get_document, get_board, get_document_state | 그래프가 주입(모델이 바꿀 수 없음) |
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
| report.generate | {session_id, attempt} (attempt는 1부터. 최초 발행 1, 실패 시 +1로 재발행, 3에서도 실패하면 DLQ: 최초 포함 총 3회. approve도 같음) | api `complete()` 직후. 미발행 세션은 스케줄러가 60초마다 재탐색해 재발행 | 워커. draft 저장 성공 후 ack |
| report.approve | {session_id, attempt} | api `/admin/sessions/{id}/review`. 미발행(approve_enqueued_at null)은 스케줄러가 60초마다 재발행 | 워커. final 저장 성공 후 ack |
| report.dlq | 원본 + error | 워커(attempt ≥ 3) | 워커의 dlq 소비자가 `POST /internal/.../report_failed`를 호출한 뒤 ack(api가 내려가 있으면 ack하지 않고 60초 뒤 재시도). 메시지는 사람이 확인할 때까지 관리 UI에 남지 않으므로 error는 워커 로그에도 남김 |

메시지는 persistent, 발행은 publisher confirm을 켜고 브로커 확인을 받은 뒤에야 `*_enqueued_at`을 기록하거나(api) 원본을 ack한다(워커 재발행). 소비는 manual ack, 같은 session_id의 중복 메시지는 stage로 멱등 처리. 재시도는 nack 없이 `attempt+1`로 재발행(확인 후) → 원본 ack(지연은 워커의 백오프 대기). RabbitMQ 데이터는 `rabbitdata` 볼륨에 남고, 브로커를 재생성해 큐가 비면 api 스케줄러의 outbox 재탐색이 미처리 세션을 다시 발행한다.
