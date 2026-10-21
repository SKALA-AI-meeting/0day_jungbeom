# report-worker 수정 보고

## 수정 내용
1. `infra/docker-compose.yml` report-worker에 `../scenarios:/scenarios:ro` 볼륨 추가.
2. ai_usage 원문: `assistant_calls` 행의 `request`·`response`를 쓰고 `api.all_messages`·`MESSAGE_PAGE`·graph의 messages 조회를 제거(`api.py`, `graph.py`, `report.py`). 가짜 api는 `assistant_calls`에 원문을 준다.
3. `position.name`: 읽기 코드(`report.py`)는 그대로, 가짜 api 세션에 name을 넣고 `test_graph.py`가 request_quote·response_quote·position.name 값을 검증한다.
4. 확인: `card.get("stage_id")`는 시나리오 카드 필드명(`cards.yaml`, 픽스처 position.scenario.cards)과 일치해 변경 없음.

## 명령·결과
- `cd services/report-worker && uv run pytest -q` : 28 passed
- `uv run --with ruff ruff check .` : All checks passed (프로젝트 venv에 ruff가 없어 --with 사용)
