# api

토론형 세션의 상태·단계·칸·메일박스·스케줄러와 공개(8000)·내부(8001) REST·WS. 설계 `docs/services/api.md`, 계약 `docs/contracts/README.md`.

## 실행

```
cd services/api && uv run python -m app.run --reload    # 8000 + 8001 + 스케줄러(한 프로세스)
uv run pytest -q -m "not live"                          # 격리 임시 DB(infra postgres 필요), LLM·MCP·RabbitMQ 없음
```

env: `AGENT_RUNNER=session`(기본, 토론 그래프) · `fake`(단위 테스트 주입용). `LLM_FAKE=1`은 LLM 호출만 고정 응답. `ENABLE_TEST_API=1`이면 `/internal/test/*`가 열린다.

## 구조

- `services/session.py`·`phases.py`: 상태·단계 전이(SessionService), 누적 마감, 전환 프레임.
- `services/debate.py`: 지원자 메시지 저장·generation, 의도 분류 반영, 안·입장, 칸 확정·합의 채우기, DebateState. `consensus.py`는 순수 판정 함수, `timeout.py`는 마감 채우기.
- `mailbox.py`: 세션별 직렬 메일박스(agent_runs 상태로 멱등). `scheduler.py`: 5초 틱(마감·임박 안내·idle·card_due·자동 제출·run 재실행·outbox·purge).
- `services/test_sessions.py`: 테스트 API. 단계 시드 `scenarios/e2e/stages/<이름>.yaml`(stage-kit 소유)을 서비스 함수로 재생한다. 시드 step 키는 모듈 docstring(`say`+`intent`, `ai`, `confirm`, `proposal`, `submit`, `at`).
- 테스트 도구: `tests/kit.py`(가짜 시계·기록 runner·고정 의도 분류·httpx ASGI 클라이언트).
