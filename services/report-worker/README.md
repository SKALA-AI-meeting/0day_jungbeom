# report-worker

리포트 그래프 `collect → draft → approval[interrupt] → finalize`(thread `report:{session_id}`, PostgresSaver)와 큐 소비자 3개(`report.generate`, `report.approve`, `report.dlq`). 설계는 `docs/worker-infra/design.md`, 평가표 규칙은 `docs/common/rubric.md`, 형식은 `docs/common/contracts.md`.

| 모듈 | 내용 |
|---|---|
| `rubric.py` | `evaluate(card, observation, event_fired=)` 순수 함수. 항목 1/0/None과 기록 없음 사유, 요소 합계 |
| `report.py` | draft 조립(섹션·평가표·AI 활용 요약), 같은 세션 근거만 남김, 텍스트 필드 금지어 문장 제거 |
| `graph.py` | LangGraph 그래프와 thread 상태 판정(멈춤·완료) |
| `consumer.py` | 메시지 처리 규칙(재시도 백오프 5·15·45초, attempt≥3 → DLQ, dlq는 api 복구까지 60초 간격 재시도)과 aio-pika 연결 |
| `api.py` | 내부 REST 클라이언트(X-Internal-Token) |
| `llm.py` | gpt-4o-mini temperature 0, 재시도 2회 뒤 고정 문장, 사용량 집계 |

```
uv run python -m report_worker   # heartbeat + 소비자. infra/.env.local → infra/.env를 읽는다
uv run pytest                    # LLM은 FakeLLM. postgres·rabbitmq가 떠 있으면 실제 체크포인터·브로커 테스트도 돈다
```

테스트는 공용 인프라를 쓰되 겹치지 않게 Postgres는 임시 스키마, RabbitMQ는 `test-worker-<랜덤>.` 접두사의 exchange·큐를 만들고 끝나면 지운다.
