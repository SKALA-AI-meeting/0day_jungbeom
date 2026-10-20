# e2e division_refuse

- session_id: `3c0e2b2d-0f4b-47a5-82cd-ba7d201e9a28`
- 요소: planning, responsibility
- 종료 상태: report_ready
- 토큰 합(agent_runs + reports): 124620
- 접수→응답 지연 p95: 9.7초
- LangSmith: https://smith.langchain.com/ 프로젝트 `day-zero`에서 metadata session_id = `3c0e2b2d-0f4b-47a5-82cd-ba7d201e9a28` (run_id별 필터는 아래 표의 run_id)

## 단언

| 번호 | 함수 | 결과 | 실패 |
|---|---|---|---|
| 1 | assert_1_cards | 통과 |  |
| 2 | assert_2_report | 통과 |  |
| 2a | assert_2a_review | 통과 |  |
| 3e | assert_3e_windows | 통과 |  |
| 4 | assert_4_report_flow | 통과 |  |
| 2b | assert_2b_no_preempt | 통과 |  |
| 3a | assert_3a_labels | 통과 |  |
| 3g | assert_3g_delay_notice | 통과 |  |
| 9 | assert_9_cost | 통과 |  |

## 카드 시각(분, 오차는 초)

| 카드 | 상태 | 예정 | fired | 첫 메시지 | fired 오차 | 메시지 지연 |
|---|---|---|---|---|---|---|
| kickoff | done | 0.0 | 0.042 | 0.09 | 2.5 | 2.9 |
| planning_division | done | 0.5 | 0.544 | 0.57 | 2.7 | 1.5 |
| planning_checkin | done | 1.5 | 1.547 | 1.6 | 2.8 | 3.2 |
| responsibility_delay | done | 3.0 | 3.051 | 3.05 | 3.1 | -0.1 |
| review | done | 4.5 | 4.557 | 4.8 | 3.4 | 14.6 |
| report_request | done | 5.5 | 5.562 | 5.59 | 3.7 | 1.7 |

## run_id별 도구 호출

| run_id | 자극 | 상태 | 도구 | 토큰(in/out) |
|---|---|---|---|---|
| `54644f64-e83a-4152-8c4e-472e9fee5d9e` | event | finished | - | 7898/259 |
| `e11fe6ee-0ddc-4d96-840f-215be074d2cc` | message | finished | search_documents | 6641/105 |
| `63cbafc0-2deb-42e4-b8a0-f5e3dc1230cf` | event | finished | - | 5528/71 |
| `b05a637c-6f6b-46af-b9dc-53c943a6f53a` | message | finished | - | 6175/157 |
| `371a2090-42de-4f3d-8f41-3834ba6ab293` | message | finished | - | 6274/135 |
| `3e39c3d5-d050-4a02-a611-92a37ad151c5` | event | finished | - | 27243/894 |
| `6e9a6a6b-1dbd-44a3-a5d6-388c03e83c1c` | event | finished | - | 0/0 |
| `015357b3-6c40-4f80-b363-21c2586bc55f` | message | finished | search_documents | 7665/147 |
| `feb47c4b-2305-4bab-bf89-cf3328b6ad24` | event | finished | - | 28603/1102 |
| `eb3db51c-e08a-4580-8e96-f22a74fd6955` | message | finished | search_documents | 7989/85 |
| `e7e6ef3d-fc69-41fb-ab59-3ba09f27561d` | event | finished | - | 3729/133 |
| `23493c57-65c5-4bf1-bc8a-a2e7ed09f134` | message | finished | search_documents | 8181/104 |
| `bb2afc26-f50d-52c8-bc3c-5fae8a76ba24` | end | finished | - | 5383/119 |
