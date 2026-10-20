# business-mcp 리뷰 반영 보고
- 커밋 dbd26bc (브랜치 track/business-mcp)
- 401 → forbidden(retryable=false). 400·기타 4xx는 invalid_input, 410 conflict, 423 not_released 유지. `client.py` docstring에 매핑 표, `test_error_codes_mapped`에 401 추가
- 2xx 비JSON 본문 → `{ok:false, upstream_unavailable, retryable:true}`(재시도 없음). 테스트 `test_non_json_success_body_becomes_upstream_unavailable`
- `cd services/business-mcp && uv run pytest`: 11 passed
- 루트 `make lint`: exit 0
- 변경 파일: `business_mcp/client.py`, `tests/test_tools.py`
