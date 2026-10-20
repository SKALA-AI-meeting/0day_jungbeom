# 테스트 픽스처

`contracts/`는 `docs/common/contracts.md`의 예시 JSON을 옮기고 빠진 경로를 같은 세션(sess-1, 120분, 5요소 전부, 카드 7장)으로 채운 것이다. 서비스 사이(MCP·api·web mock)가
같은 예시를 공유한다. 계약 예시가 바뀌면 이 폴더와 `apps/web/mocks/fixtures/`를 함께 갱신한다. 루트 `tests/conftest.py`의 `load_contract("<이름>")`으로 읽는다.

id는 파일 사이에서 같은 행을 가리킨다: 메시지 `m-*`, 지원자 문서 `doc-c1~5`, 동료 문서 `doc-k3~5`, 최종본 `doc-final`, 이벤트 `ev-1~9`, 보낸 버전 `sh-*`(지원자)·`ksh-*`(동료), 열기 `op-*`, 보드 변경 `te-*`, 자동 저장 `rev-*`, 회사 문서 열람 `dv-*`, 어시스턴트 `ac-*`, 관찰 `ob-*`.

## 관리자 REST

| 파일 | 계약 |
|---|---|
| `admin_auth_token.json` | POST /admin/auth/signup·login 응답 {token} |
| `admin_catalog.json` | GET /admin/catalog |
| `admin_positions.json` | GET /admin/positions |
| `admin_position_created.json` | POST /admin/positions 응답(scenario 포함) |
| `admin_candidates.json` | GET /admin/positions/{id}/candidates (report_ready·failed·재응시 invited) |
| `admin_invite.json` | POST /admin/positions/{id}/invites 응답 |
| `admin_cancel.json` | POST /admin/sessions/{id}/cancel 응답 |
| `report.json` | Report (GET /admin/sessions/{id}/report) |
| `admin_report_regenerate.json` | POST .../report/regenerate 응답 |
| `admin_review_request.json`, `admin_review_response.json` | POST .../review 요청·응답 |
| `admin_report_notes.json` | POST .../report/notes 응답 |
| `admin_record.json` | GET /admin/sessions/{id}/record (배열, `ref`는 Report 근거의 `record_ref`와 같은 값) |

## 지원자 REST

| 파일 | 계약 |
|---|---|
| `candidate_entry.json`, `candidate_entry_completed.json` | GET /s/{token} (invited, completed + debrief_token) |
| `candidate_session_token.json` | POST /s/{token}/consent·resume 응답 |
| `candidate_start.json` | POST /s/{token}/start 응답 |
| `state.json` | State 스냅샷(in_progress, 47.5분) |
| `state_reporting.json` | State 스냅샷(reporting, deadline_at) |
| `message.json` | Message (State의 첫 메시지) |
| `my_documents.json` | GET /sessions/{id}/my-documents |
| `my_document_save.json` | PUT .../my-documents/{part_no∣final} 응답 |
| `my_document_share.json` | POST .../my-documents/{part_no}/share 응답 |
| `document_open.json` | POST .../documents/{doc_id}/open 응답 |
| `final_section_import.json` | PUT .../final/sections/{part_no}/import 응답 |
| `task.json` | PUT .../tasks/{part_no} 응답 |
| `documents.json`, `document.json` | GET .../documents, GET .../documents/{doc_id} |
| `assistant_response.json` | POST .../assistant 응답 |
| `submit.json` | POST .../submit 응답 |
| `debrief.json`, `debrief_failed.json` | GET .../debrief (정상, failed_stage=session) |
| `debrief_survey.json` | POST .../debrief/survey 응답 |
| `error.json` | 공통 오류 형식 |

## WebSocket

| 파일 | 계약 |
|---|---|
| `ws_events.json` | 서버 프레임 `{at_ms, type, payload}` 재생 예시(ack → 동료 응답, 보드·분업 확정, 문서 보냄, 지연 알림·공개, 보고 대기, 종료) |
| `ws_client_frames.json` | 클라이언트 message.send(reply_to_doc 포함) |
| `ws_error.json`, `ws_session_replaced.json` | 오류 프레임, 연결 교체 |

## 내부 REST

| 파일 | 계약 |
|---|---|
| `internal_session.json` | GET /internal/sessions/{id} |
| `internal_messages.json`, `internal_message_post.json` | GET·POST /messages (meta.classification 포함) |
| `internal_classification.json` | PUT /messages/{id}/classification 요청 |
| `internal_board.json`, `internal_task_update.json` | GET /board, PUT /tasks/{part_no} 요청 |
| `internal_task_events.json` | GET /task_events |
| `internal_honesty_facts.json` | GET /honesty_facts |
| `internal_division_put.json`, `internal_division.json` | PUT /division 요청·응답 |
| `internal_docs.json` | GET /docs |
| `internal_document_revisions.json` | GET /document_revisions |
| `internal_docs_shared.json` | GET /docs/shared (지원자 문서는 보낸 버전만) |
| `internal_docs_send_request.json`, `internal_docs_send.json` | POST /docs/send 요청·응답(event_id·seq) |
| `internal_documents.json`, `internal_release.json` | GET /documents, POST /releases/{doc_id} 응답 |
| `observation.json`, `observation_collab_help.json`, `observation_created.json` | POST /observations 요청 2종·응답 |
| `observation_patch.json` | PATCH /observations 요청(metrics_patch) |
| `internal_observations.json` | GET /observations |
| `internal_assistant_calls.json`, `internal_assistant_reuse.json`, `internal_doc_views.json` | GET /assistant_calls, /assistant_reuse, /doc_views |
| `internal_complete.json` | POST /complete 응답 |
| `internal_report_draft.json`, `internal_report_usage.json` | POST /report/draft 응답, usage 형태 |
| `internal_report_final.json`, `internal_report_failed.json` | POST /report/final, /report_failed 응답 |
| `internal_test_session.json` | POST /internal/test/sessions 응답 |

## MCP·큐

| 파일 | 계약 |
|---|---|
| `mcp_ok.json`, `mcp_error.json` | MCP 공통 응답 형식 |
| `mcp_tools.json` | business-mcp·rag-mcp 도구별 입력·출력(출력이 문자열이면 같은 폴더의 그 파일) |
| `queue_messages.json` | report.generate·approve·dlq 본문 |
