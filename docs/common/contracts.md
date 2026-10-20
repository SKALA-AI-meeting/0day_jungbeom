# 인터페이스 계약

병렬 트랙의 공용 기준. 트랙은 이 파일을 바꾸지 않는다. 바꿔야 하면 오케스트레이터에 올린다. 예시 JSON은 mock 서버와 테스트 픽스처의 정본이다.

## 공통

- 베이스: `http://api:8000`. 응답 JSON, 오류는 `{"error": {"code": "...", "message": "..."}}`와 HTTP 4xx/5xx.
- 인증 헤더: `Authorization: Bearer <jwt>`. 내부 API는 `X-Internal-Token: <secret>`.
- 시각은 ISO 8601 UTC. 세션 상대 시각은 `t_min`(세션 시작 기준 분, 소수 허용)으로도 함께 준다.

## 관리자 REST (`/admin`)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | /admin/auth/signup | {email, password, company_name} | {token} |
| POST | /admin/auth/login | {email, password} | {token} |
| GET | /admin/positions | | [{id, name, elements, candidate_count, created_at}] |
| POST | /admin/positions | {name, elements: ["cooperation", ...]} (1~4개) | {id, name, elements, scenario} |
| GET | /admin/positions/{id}/candidates | | [{session_id, alias, status, invited_at, report_ready_at}] |
| POST | /admin/positions/{id}/invites | {alias, email} | {invite_url, expires_at} |
| GET | /admin/sessions/{id}/report | | Report (아래) |
| POST | /admin/sessions/{id}/review | | {status: "approving"} (워커가 재개해 최종 저장하면 reviewed) |

`elements` 검증: 카탈로그 id만, 중복 없음, 1~4개. 위반 시 400 `invalid_elements`.

### Report

```json
{"session_id":"...","alias":"지원자A","position":{"name":"...","elements":["cooperation","responsibility"]},
 "sections":[
  {"element":"responsibility","name":"책임감","situation":"담당 파트에 필요한 인터뷰 자료 지연",
   "observed":"마감 전에 지연을 먼저 알리고 대안을 제시함",
   "evidence":[{"t_min":52,"channel":"team","quote":"인터뷰 자료가 늦어서..."}]},
  {"element":"cooperation","name":"협력 태도","situation":"...","observed":null,"evidence":[],
   "note":"해당 상황에서 관련 행동이 기록되지 않음"}],
 "ai_usage":{"used":true,"summary":"...","evidence":[{"t_min":41,"quote":"..."},{"t_min":47,"part_no":4,"reuse":"edited"}]},
 "stage":"draft","generated_at":"...","reviewed_at":null}
```

`ai_usage.used=false`면 `summary`는 "사용하지 않음"이고 evidence는 빈 배열. 어떤 필드에도 점수·합격·순위 표현이 없어야 한다(워커가 금지어 검사).

## 지원자 REST (`/s`)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | /s/{token} | | {company_name, duration_minutes, status, elements_names} 또는 410 `expired` / 409 `completed` |
| POST | /s/{token}/consent | | {session_token} (세션 JWT) |
| POST | /s/{token}/start | Bearer 세션 | {session_id, started_at, ends_at} |
| GET | /s/{token}/state | Bearer | 아래 State 스냅샷 (이어하기) |
| PUT | /sessions/{id}/document/{part_no} | Bearer {content} | {updated_at} |
| PUT | /sessions/{id}/tasks/{part_no} | Bearer {status} | {part_no, status} (지원자 담당 카드만) |
| GET | /sessions/{id}/documents | Bearer | [{doc_id, title, released: bool}] |
| GET | /sessions/{id}/documents/{doc_id} | Bearer | {doc_id, title, content} 또는 423 `not_released` |
| POST | /sessions/{id}/assistant | Bearer {prompt} | {message_id, content, cited_docs: ["metrics"]} |
| POST | /sessions/{id}/submit | Bearer | {status: "completed"} |
| GET | /sessions/{id}/debrief | Bearer | {events: [{element, name, description}], notice} |

같은 링크 재입장: `used_at`이 있어도 session.status가 in_progress면 `/consent` 없이 `/state`로 이어간다.

### State 스냅샷

```json
{"session":{"id":"...","status":"in_progress","started_at":"...","ends_at":"...","remaining_seconds":5400},
 "messages":[{"id":"...","channel":"team","sender":"manager","content":"...","t_min":0.0,"created_at":"..."}],
 "document":{"1":"...","2":"","3":"","4":"","5":""},
 "tasks":[{"part_no":1,"assignee":"candidate","status":"doing"}],
 "documents":[{"doc_id":"metrics","title":"지표 현황","released":true}],
 "assistant":[{"request":"...","response":"...","cited_docs":["metrics"],"t_min":41.2}],
 "persona":{"manager":"한서윤 팀장","colleague":"이도현"}}
```

## WebSocket `/ws/sessions/{id}?token=<세션 JWT>`

서버 → 클라이언트:

| type | payload |
|---|---|
| message.new | Message (위 messages 항목과 동일) |
| agent.progress | {actor: "colleague"∣"manager"∣"assistant", node: "respond", status: "started"∣"tool_start"∣"tool_end"∣"finished"∣"failed", tool?: "search_documents"} |
| document.released | {doc_id, title} |
| document.part_updated | {part_no, content, by: "colleague"} |
| task.updated | {part_no, assignee, status} |
| session.ended | {reason: "submitted"∣"timeout"} |

클라이언트 → 서버:

| type | payload |
|---|---|
| message.send | {channel: "team"∣"dm", content} |

재연결 시 클라이언트는 `/s/{token}/state`를 다시 받는다. WS는 증분만 보낸다.

## 내부 REST (`/internal`, X-Internal-Token)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | /internal/sessions/{id} | | {id, status, position: {elements, scenario}, division, started_at, ends_at, t_min_now} |
| GET | /internal/sessions/{id}/messages?since_t_min=&channel= | | [Message] |
| POST | /internal/sessions/{id}/messages | {channel, sender, content, event_id?, meta?} | Message |
| GET | /internal/sessions/{id}/board | | {tasks: [...]} |
| PUT | /internal/sessions/{id}/tasks/{part_no} | {assignee?, status?} | task |
| PUT | /internal/sessions/{id}/division | {parts: {"1": "candidate", ...}} | {division} |
| GET | /internal/sessions/{id}/document | | {"1": "...", ...} |
| PUT | /internal/sessions/{id}/document/{part_no} | {content, by: "colleague"} | {updated_at} |
| POST | /internal/sessions/{id}/releases/{doc_id} | | {released_at} |
| POST | /internal/sessions/{id}/observations | {element, window_start, window_end, metrics, label, evidence_message_ids} | {id} |
| GET | /internal/sessions/{id}/observations | | [...] |
| GET | /internal/sessions/{id}/assistant_calls | | [...] |
| POST | /internal/sessions/{id}/report/draft | {content} | {status: "report_ready"} |
| POST | /internal/sessions/{id}/report/final | {content} | {status: "reviewed", reviewed_at} |
| POST | /internal/sessions/{id}/report_failed | {error} | {status: "failed"} |
| POST | /internal/test/sessions | {elements, session_minutes, alias?} | {session_id, token, invite_url} (테스트 전용, `ENABLE_TEST_API=1`일 때만) |

## MCP 도구

### business-mcp (`http://business-mcp:9101/mcp`)

| 도구 | 입력 | 출력 data | 구분 |
|---|---|---|---|
| get_session | {session_id} | 내부 GET /sessions/{id} | 조회 |
| list_messages | {session_id, since_t_min?, channel?, limit?=50} | [Message] | 조회 |
| get_board | {session_id} | {tasks} | 조회 |
| get_document_state | {session_id} | {"1": ...} | 조회 |
| post_message | {session_id, channel, sender ∈ colleague∣manager∣system, content, event_id?} | Message | 변경 |
| set_division | {session_id, parts} | {division} | 변경 |
| update_task | {session_id, part_no, status} | task. 동료 담당 카드만, 아니면 `forbidden` | 변경 |
| write_document_part | {session_id, part_no, content} | {updated_at}. 동료 담당 파트만 | 변경 |
| release_document | {session_id, doc_id} | {released_at} | 변경 |
| record_observation | {session_id, element, window_start, window_end, metrics, label, evidence_message_ids} | {id} | 변경 |

### rag-mcp (`http://rag-mcp:9102/mcp`)

| 도구 | 입력 | 출력 data | 구분 |
|---|---|---|---|
| search_documents | {query, session_id, top_k?=3} | [{doc_id, title, chunk, score}]. 세션에 공개된 문서만 | 조회 |
| get_document | {doc_id, session_id} | {doc_id, title, content}. 공개 전이면 `not_released` | 조회 |
| list_documents | {session_id} | [{doc_id, title, released}] | 조회 |
| index_documents | {path?} | {indexed: n}. 시드·관리용 | 변경 |

### 공통 응답 형식

```json
{"ok": true, "data": {...}}
{"ok": false, "error": {"code": "not_found", "message": "session not found", "retryable": false}}
```

코드: `invalid_input`, `not_found`, `forbidden`, `not_released`, `upstream_unavailable`(retryable), `internal`. 입력은 Pydantic으로 검증하고 모든 도구에 한 문단 설명과 인자 설명을 단다.
