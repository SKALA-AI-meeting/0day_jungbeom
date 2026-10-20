# 인터페이스 계약

병렬 트랙의 공용 기준. 트랙은 이 파일을 바꾸지 않는다. 바꿔야 하면 오케스트레이터에 올린다. 예시 JSON은 mock 서버와 테스트 픽스처의 정본이다.

## 공통

- 공개 베이스: `http://api:8000` (web이 호출). 내부 베이스: `http://api:8001` (`/internal/*`만, compose 네트워크 안에서만 열림, 포트 미공개).
- 응답 JSON. 오류는 `{"error": {"code": "...", "message": "..."}}`와 HTTP 4xx/5xx.
- 인증 헤더: `Authorization: Bearer <jwt>`. 내부: `X-Internal-Token: <secret>`.
- 시각은 ISO 8601 UTC. 세션 상대 시각은 `t_min`(세션 시작 기준 분, 소수 허용)으로도 함께 준다.
- 멱등: 변경 요청은 `Idempotency-Key` 헤더(선택)를 받으며 같은 키의 재요청은 같은 결과를 돌려준다. 내부 저장의 멱등 키: 메시지 `(session_id, run_id, seq)`, 문서 수정 `(session_id, part_no, run_id)`, 관찰 `(session_id, element, window_start)`. 같은 키의 재요청은 기존 행을 돌려준다.

## 인증 생명주기

| 단계 | 호출 | 상태 | 토큰 |
|---|---|---|---|
| 초대 생성 | 관리자 POST /invites | sessions 행이 `invited`로 함께 생성됨 | 초대 토큰(링크에만, DB에는 해시) |
| 링크 입장 | GET /s/{token} | 만료(72h) → 410, 세션이 completed 이후 → 409 | 없음 |
| 동의 | POST /s/{token}/consent | `consented_at` 기록 | 세션 JWT 발급. 만료 = now + session_minutes + 120분 |
| 시작 | POST /s/{token}/start (Bearer) | `in_progress`, started_at·ends_at 확정, 이벤트·공개 예약 | 같은 JWT |
| 재입장 | GET /s/{token} → status가 invited면 POST /s/{token}/consent 재호출, in_progress면 POST /s/{token}/resume | 변화 없음 | 세션 JWT 재발급(저장된 JWT가 없어도 링크만으로 이어감). 초대 72h 만료는 시작 후에는 적용하지 않음 |
| 종료 | submit 또는 timeout | `completed` | JWT는 디브리핑 조회까지 유효 |

검증: 다른 세션 id 접근 403, 동의 중복 호출은 멱등(새 JWT 재발급), 같은 초대의 동의는 시작 전까지 몇 번이든 허용하고 시작 후에는 409, 시작 전 JWT 만료는 `/consent` 재호출로, 시작 후 만료는 `/resume`으로 복구.

## 관리자 REST (`/admin`, 포트 8000)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | /admin/auth/signup | {email, password, company_name} | {token} |
| POST | /admin/auth/login | {email, password} | {token} |
| GET | /admin/positions | | [{id, name, elements, candidate_count, created_at}] |
| POST | /admin/positions | {name, elements: ["cooperation", ...]} (1~4개) | {id, name, elements, scenario, catalog_version} |
| GET | /admin/positions/{id}/candidates | | [{session_id, alias, status, invited_at, report_ready_at}] |
| POST | /admin/positions/{id}/invites | {alias, email} | {session_id, invite_url, expires_at} |
| GET | /admin/sessions/{id}/report | | Report (아래) 또는 404(아직 없음) |
| POST | /admin/sessions/{id}/review | | {status: "approving"}. 이미 approving·reviewed면 200 멱등 |

`elements` 검증: 카탈로그 id만, 중복 없음, 1~4개. 위반 시 400 `invalid_elements`. 모든 조회는 JWT의 company_id로 필터.

### Report

```json
{"session_id":"...","alias":"지원자A","stage":"draft",
 "position":{"name":"...","elements":["cooperation","responsibility"]},
 "sections":[
  {"element":"responsibility","name":"책임감","situation":"담당 파트에 필요한 인터뷰 자료 지연",
   "observed":"마감 전에 지연을 먼저 알리고 대안을 제시함",
   "evidence":[{"message_id":"...","t_min":52,"channel":"team","quote":"인터뷰 자료가 늦어서..."}]},
  {"element":"cooperation","name":"협력 태도","situation":"...","observed":null,"evidence":[],
   "note":"해당 상황에서 관련 행동이 기록되지 않음"}],
 "ai_usage":{"used":true,"summary":"...",
   "evidence":[{"call_id":"...","t_min":41,"quote":"..."},{"call_id":"...","t_min":47,"part_no":4,"reuse":"edited"}]},
 "generated_at":"...","reviewed_at":null}
```

`stage`는 draft 또는 final. `ai_usage.used=false`면 summary는 "사용하지 않음"이고 evidence는 빈 배열. 모든 evidence의 message_id·call_id는 같은 세션의 실제 행을 가리켜야 하며(워커가 검증), 어떤 필드에도 점수·합격·순위 표현이 없어야 한다.

## 지원자 REST (`/s`, `/sessions`, 포트 8000)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | /s/{token} | | {company_name, duration_minutes, status, elements_names} 또는 410 `expired` / 409 `completed` |
| POST | /s/{token}/consent | | {session_token} |
| POST | /s/{token}/resume | | {session_token} (status in_progress일 때만, 아니면 409) |
| POST | /s/{token}/start | Bearer | {session_id, started_at, ends_at} (이미 시작했으면 같은 값 멱등) |
| GET | /sessions/{id}/state | Bearer | State 스냅샷 |
| PUT | /sessions/{id}/document/{part_no} | Bearer {content} | {updated_at, revision} |
| PUT | /sessions/{id}/tasks/{part_no} | Bearer {status} | task (지원자 담당 카드만, 아니면 403) |
| GET | /sessions/{id}/documents | Bearer | [{doc_id, title, released: bool}] |
| GET | /sessions/{id}/documents/{doc_id} | Bearer | {doc_id, title, content} 또는 423 `not_released`. 열람을 `doc_views`에 기록 |
| POST | /sessions/{id}/assistant | Bearer {prompt} | {call_id, message_id, content, cited_docs} 또는 429 `assistant_limit`(60회 초과) |
| POST | /sessions/{id}/submit | Bearer | {status: "completed"} (멱등) |
| GET | /sessions/{id}/debrief | Bearer | {events: [{element, name, description}], notice} |

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

재접속 복구 범위: 스냅샷이 전체 상태이고 WS는 증분만 보낸다. `active_runs`로 진행 중 표시를 복원한다. 완료된 실행은 messages의 run_id로 식별한다.

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
| message.send | {client_msg_id, channel: "team"∣"dm", content} |

`event_id`가 있는 message.new는 이벤트 카드 실행의 결과다(러너가 카드 발생을 감지하는 기준). 진행 상태 이름은 위 다섯 가지로 고정한다.

## 내부 REST (`/internal`, 포트 8001, X-Internal-Token)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | /internal/sessions/{id} | | {id, status, position: {elements, scenario, catalog_version}, division, started_at, ends_at, t_min_now, current_element} |
| GET | /internal/sessions/{id}/messages?since_t_min=&channel=&limit= | | [Message] |
| POST | /internal/sessions/{id}/messages | {channel, sender, content, event_id?, run_id, seq, meta?} | Message (같은 run_id+seq 재요청은 기존 행) |
| GET | /internal/sessions/{id}/board | | {tasks} |
| PUT | /internal/sessions/{id}/tasks/{part_no} | {status} | task. 동료 담당이 아니면 403 `forbidden` |
| PUT | /internal/sessions/{id}/division | {parts} | {division}. in_progress가 아니면 409. 최소 조건(2번 candidate, 4·5 중 하나 이상 colleague 단독) 위반은 422 |
| GET | /internal/sessions/{id}/document | | {"1": {content, revision, updated_by}, ...} |
| PUT | /internal/sessions/{id}/document/{part_no} | {content, by: "colleague", run_id} | {updated_at, revision}. 같은 part_no+run_id 재요청은 기존 revision. 동료 담당이 아니면 403 |
| GET | /internal/sessions/{id}/documents | | {catalog_version, documents: [{doc_id, title, released}]} (rag-mcp가 공개 여부와 색인 버전 확인에 사용) |
| POST | /internal/sessions/{id}/releases/{doc_id} | | {released_at} (멱등) |
| POST | /internal/sessions/{id}/observations | {element, window_start, window_end, metrics, label, evidence_message_ids, run_id} | {id}. 같은 element+window_start 재요청은 기존 행. evidence가 이 세션의 메시지가 아니면 422 |
| GET | /internal/sessions/{id}/observations | | [...] |
| GET | /internal/sessions/{id}/assistant_calls | | [{id, request_message_id, response_message_id, cited_doc_ids, created_at}] |
| GET | /internal/sessions/{id}/assistant_reuse | | [{call_id, part_no, reuse, ratio}] (제출 후에만 값이 있음) |
| GET | /internal/sessions/{id}/document_revisions | | [{part_no, revision, by, content, length, diff_ratio, created_at}] |
| GET | /internal/sessions/{id}/doc_views | | [{doc_id, viewed_at}] |
| POST | /internal/sessions/{id}/report/draft | {content} | {status: "report_ready"} (멱등) |
| POST | /internal/sessions/{id}/report/final | {content} | {status: "reviewed", reviewed_at}. draft가 없거나 status가 approving이 아니면 409 |
| POST | /internal/sessions/{id}/report_failed | {error} | {status: "failed"} |
| POST | /internal/test/sessions | {elements, session_minutes, alias?} | {session_id, token, invite_url} (`ENABLE_TEST_API=1`일 때만) |

권한·상태 검증(담당자, 세션 상태, 문서 공개 여부)은 모두 api가 최종 판단한다. MCP는 전달만 한다.

## MCP 도구

### business-mcp (`http://business-mcp:9101/mcp`)

| 도구 | 입력 | 출력 data | 구분 |
|---|---|---|---|
| get_session | {session_id} | 내부 GET /sessions/{id} | 조회 |
| list_messages | {session_id, since_t_min?, channel?, limit?=50} | [Message] | 조회 |
| get_board | {session_id} | {tasks} | 조회 |
| get_document_state | {session_id} | 내부 GET /document | 조회 |
| post_message | {session_id, channel, sender ∈ colleague∣manager∣system, content, event_id?, run_id, seq} | Message | 변경 |
| set_division | {session_id, parts} | {division} | 변경 |
| update_task | {session_id, part_no, status} | task | 변경 |
| write_document_part | {session_id, part_no, content, run_id} | {updated_at, revision} | 변경 |
| release_document | {session_id, doc_id} | {released_at} | 변경 |
| record_observation | {session_id, element, window_start, window_end, metrics, label, evidence_message_ids, run_id} | {id} | 변경 |

### rag-mcp (`http://rag-mcp:9102/mcp`)

| 도구 | 입력 | 출력 data | 구분 |
|---|---|---|---|
| search_documents | {query, session_id, top_k?=3} | [{doc_id, title, chunk, score}]. 내부 GET /documents로 공개 여부 확인 후 공개된 문서만 | 조회 |
| get_document | {doc_id, session_id} | {doc_id, title, content}. 공개 전이면 `not_released` | 조회 |
| list_documents | {session_id} | [{doc_id, title, released}] | 조회 |
| reindex_documents | {} | {indexed: n, model, dim, catalog_version}. 현재 카탈로그 버전으로 고정 문서 5개를 색인(관리용). 다른 버전의 청크는 지우지 않음. 에이전트에는 노출하지 않음 | 변경 |

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
| report.generate | {session_id, attempt} | api `complete()` 직후. 미발행 세션은 스케줄러가 60초마다 재탐색해 재발행 | 워커. draft 저장 성공 후 ack |
| report.approve | {session_id, attempt} | api `/admin/sessions/{id}/review`. 미발행(approve_enqueued_at null)은 스케줄러가 60초마다 재발행 | 워커. final 저장 성공 후 ack |
| report.dlq | 원본 + error | 워커(attempt ≥ 3) | 워커의 dlq 소비자가 `POST /internal/.../report_failed`를 호출한 뒤 ack(api가 내려가 있으면 ack하지 않고 60초 뒤 재시도). 메시지는 사람이 확인할 때까지 관리 UI에 남지 않으므로 error는 워커 로그에도 남김 |

메시지는 persistent, 소비는 manual ack, 같은 session_id의 중복 메시지는 stage로 멱등 처리. 재시도는 nack 없이 `attempt+1`로 재발행한 뒤 원본을 ack한다(지연은 워커의 백오프 대기).
