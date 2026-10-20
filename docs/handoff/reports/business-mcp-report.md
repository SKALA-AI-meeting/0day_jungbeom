# business-mcp 트랙 보고 (W1)

- worktree `Day-0_zaeho.worktrees/business-mcp`, 브랜치 `track/business-mcp`, 커밋 4772b8c (main 병합·push 안 함)

## 완료 기준 실행 결과
| 기준 | 명령 | 결과 |
|---|---|---|
| 도구 목록·설명 확인 | `uv run python -m business_mcp`(9101)를 잠깐 띄우고 fastmcp `Client("http://localhost:9101/mcp").list_tools()` 후 종료. 테스트 `test_tools_listed_with_descriptions`는 도구 10개 이름·설명·인자 설명을 검사 | **통과.** 도구 10개 전부 한 문단 설명 출력(전문: `scratchpad/tools-list.txt`). api 없이 get_session 호출 시 `{ok:false, error:{code:upstream_unavailable, retryable:true}}` |
| 오류 코드 매핑 | `uv run pytest` → `test_error_codes_mapped`(403 forbidden, 404 not_found, 409 conflict, 422 invalid_input; 4xx는 재시도 안 함) | **통과** |
| 연결 실패 재시도 1회 | `test_connection_failure_retried_once_then_upstream_unavailable`(요청 2회, retryable), `test_5xx_retry_recovers` | **통과** |
| 같은 run_id·seq 전달 | `test_post_message_forwards_idempotency_keys_and_meta`(동일 본문 2회 호출 → api에 run_id·seq·event_id·meta 그대로 2회 전달, 가공 없음). 중복 판단은 api | **통과** |
| 나머지 도구 경로·본문 | `test_mutation_tools_hit_contract_routes`, `test_get_session_forwards_token_and_wraps_data`(X-Internal-Token), `test_list_messages_passes_filters`, `test_invalid_input_returned_as_error_result` | **통과** |
| pytest | `cd services/business-mcp && uv run pytest` | 10 passed |
| 루트 | `make test`, `make lint` | 둘 다 exit 0 |

## 수정 파일
`services/business-mcp/`: `business_mcp/{client,config,tools}.py`(신규), `business_mcp/server.py`(검증 오류 미들웨어, 도구 등록), `tests/{conftest,test_tools}.py`, `README.md`. pyproject·lock은 기존 의존성(fastmcp, httpx, pydantic, python-dotenv)으로 충분해 변경 없음.

## 구현 메모
- 응답: 성공 `{ok:true,data}`, 실패 `{ok:false,error:{code,message,retryable}}`. 도구 호출 자체는 항상 성공으로 반환한다(`isError` 아님).
- 인자 검증 실패(Pydantic)는 미들웨어가 `invalid_input` 결과로 바꾼다(api 호출 없음).
- api 오류 본문의 `{error:{code,message}}`는 message에 `code: message`로 실어 `draft_mismatch` 등 세부 코드를 보존한다.
- 상태 매핑 외 4xx(예: 400 `invalid_elements`, 401)는 invalid_input으로, 410(만료·취소)은 conflict로, 423은 not_released로 옮긴다. 계약에 없는 선택이라 api 트랙과 맞출 것.
- 재시도는 5xx·연결 실패·타임아웃(10초) 모두 1회. 변경 도구도 같다(멱등 키는 api가 판단).
- `list_messages.limit`은 1~50으로 검증한다(하네스 "메시지 조회 50개").
- `set_division.parts`는 모양이 계약에 없어 `dict` 그대로 전달하고 api가 422로 판단한다.

## 남은 문제
- 내부 API 라우터가 아직 없어 실제 api 연동은 검증하지 못했다(MockTransport만). 통합은 agent-min/M3.
- `infra/.env`의 `API_INTERNAL_URL`이 8000이면 실제 호출이 실패한다(foundation 보고의 "어긋난 점 3"). 사용자가 8001로 고쳐야 한다.
- MCP Inspector(UI)는 쓰지 않고 fastmcp 클라이언트로 대체했다.

## 변경 요청
없음 (소유권 밖 파일 수정 없음). 선택 사항: contracts.md의 오류 코드 표에 410→conflict, 423→not_released 매핑을 적어 두면 api·MCP가 같은 규칙을 쓴다.

## 다른 트랙에 알릴 것
- api-admin/api-candidate: 내부 앱은 오류를 `{"error":{code,message}}` + 계약된 상태 코드(403/404/409/422)로 돌려주면 된다. 5xx는 MCP가 1회 재시도하므로 `messages`·`document`·`observations` PUT/POST의 멱등 키 처리가 필수다. `X-Internal-Token`은 `INTERNAL_TOKEN` 값.
- agent-min/session: MCP 결과는 `result.structured_content`에 `{ok,...}` 형태로 온다. `ok:false`를 예외가 아니라 값으로 처리해야 한다. `session_id`는 그래프가 주입한다.
