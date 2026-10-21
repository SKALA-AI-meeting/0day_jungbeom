# 큐 메시지 (RabbitMQ)

교환기·큐 설정과 소비 순서는 [report-worker](../services/report-worker.md).

| 큐 | 본문 | 발행 | 소비 |
|---|---|---|---|
| report.generate | {session_id, attempt, eval_round} (attempt는 1부터, 실패 시 +1 재발행, 3에서도 실패하면 DLQ. eval_round는 위 EvaluationSave `run_id` 규칙) | api `submit()` 직후(eval_round 1)와 regenerate. 미발행은 스케줄러가 60초마다 재발행 | 워커. 리포트 그래프 `collect → aggregate → evaluate → draft` → draft 저장 성공 후 ack(`interrupt`에서 멈춤) |
| report.approve | {session_id, attempt, eval_round} (eval_round = 승인한 draft를 만든 `sessions.eval_round`) | api `/admin/sessions/{id}/review`. 미발행은 60초마다 재발행 | 워커. 그 eval_round thread의 `interrupt` 재개 → `finalize`(승인된 draft content를 그대로 final로 저장, 해시 동일) 성공 후 ack |
| report.dlq | 원본 + error | 워커(attempt ≥ 3) | dlq 소비자가 `report_failed` 호출 뒤 ack |

리포트 그래프 thread_id = `report:{session_id}:{eval_round}`. 새 eval_round는 새 thread라 이전 회차의 interrupt 체크포인트(이전 draft)를 재사용하지 않고 collect부터 다시 실행한다. 같은 eval_round의 큐 재시도만 그 thread의 체크포인트에서 이어 간다(interrupt에 멈춰 있으면 draft 저장부터).

persistent, publisher confirm 뒤 `*_enqueued_at` 기록, manual ack, 같은 session_id 중복은 stage로 멱등. 재시도는 `attempt+1` 재발행 후 원본 ack(백오프 5·15·45초).
