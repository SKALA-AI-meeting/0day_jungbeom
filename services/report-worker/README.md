# report-worker

세션이 끝나면 큐 작업으로 리포트 그래프 `collect → aggregate → evaluate → draft → approval[interrupt] → finalize`(thread `report:{session_id}:{eval_round}`, PostgresSaver)를 돌리고, 큐 소비자 3개(`report.generate`, `report.approve`, `report.dlq`)를 둔다. 설계는 `docs/worker-infra/design.md`, 척도·검증 규칙은 `docs/common/rubric.md`, 형식은 `docs/common/contracts.md`.

| 모듈 | 내용 |
|---|---|
| `assessment.py` | assessment-mcp 클라이언트(`X-Assessment-Token`). `get_session_record`·`get_rubric`·`get_contributions`·`get_transcript_span`·`save_evaluation`만 |
| `api.py` | 내부 REST(X-Internal-Token): 세션 정보, 어시스턴트 호출(요청·응답 원문 포함), `GET /evaluations`, draft·final·report_failed |
| `evaluate.py` | 요소별 평가 호출(5회, 다른 요소 결과 없음), 워커 검증, 요소 단위 1회 재요청 → `evaluate_failed`, 확신도 clamp, 요소 수준(평균 .5 올림), 프롬프트 버전 맵 |
| `report.py` | aggregate(사실 지표 그대로, 칸·카드·관찰 창, 기여 대조 `contribution_check`)와 draft 조립(근거 원문·앞 5·뒤 3 맥락·record_ref, 카드 장면은 `report_template` 그대로, 총점 없음, LLM 없음) |
| `graph.py` | LangGraph 그래프, thread·run_id 규칙(`uuid5(session_id, "evaluate:"+eval_round)`) |
| `consumer.py` | 메시지 처리 규칙(같은 eval_round만 체크포인트 재개, 재시도 백오프 5·15·45초, attempt≥3 → DLQ, dlq는 api 복구까지 60초 간격)과 aio-pika 연결 |
| `llm.py` | `MODEL_EVALUATOR`(비면 `OPENAI_MODEL`), temperature 0.1, JSON 출력, 전송 실패 재시도 2회 뒤 예외(저장 없이 큐 재시도) |

평가 프롬프트(`prompts/evaluator/{common,<element>}.md`)와 금지어(`guard_patterns.yaml`의 `evaluator_forbidden`)는 `SCENARIOS_DIR/missions/<mission_id>/prompts/`에서 읽는다. 컨테이너는 `scenarios`를 `/scenarios`로 읽기 전용 마운트해야 한다.

```
uv run python -m report_worker   # heartbeat + 소비자. infra/.env.local → infra/.env를 읽는다
uv run pytest                    # FakeLLM·가짜 assessment·가짜 api·메모리 체크포인터. 외부 서비스 없이 돈다
```
