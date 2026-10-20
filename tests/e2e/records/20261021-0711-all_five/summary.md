# e2e all_five

- session_id: `5f05217d-c1a8-4a76-856d-9421f9be36a8`
- 요소: responsibility, planning, adaptability, collaboration, honesty
- 종료 상태: failed
- 토큰 합(agent_runs + reports): 172798
- 접수→응답 지연 p95: 10.1초
- LangSmith: https://smith.langchain.com/ 프로젝트 `day-zero`에서 metadata session_id = `5f05217d-c1a8-4a76-856d-9421f9be36a8` (run_id별 필터는 아래 표의 run_id)

## 단언

| 번호 | 함수 | 결과 | 실패 |
|---|---|---|---|
| steps | 대본 진행 | 실패 | review: POST /documents/4af8f5c6-c479-4618-98ac-4e8a862b7007/open → 404 {"error":{"code":"not_found","message":"shared version not found"}}<br>0.1: no ack for 4번 사례 하나는 후속 모임 제안 기능이 있는 서비스로<br>collab_disagree: card message not received<br>collab_disagree: no ack for 말씀 일리 있어요. 다만 2·8번처럼 일정을 놓친 경우<br>0.3: PUT /final/sections/1/import → 409 {"error":{"code":"conflict","message":"session is failed"}}<br>honesty_report: card message not received<br>honesty_report: no ack for 1·2번은 제가 썼고, 3번은 도현님 골격에 제가 보탰<br>report: report_ready not reached |
| 1 | assert_1_cards | 실패 | review status failed<br>collab_disagree status failed<br>honesty_report status pending |
| 2 | assert_2_report | 실패 | no report draft<br>no report final |
| 2a | assert_2a_review | 실패 | review not reached |
| 3e | assert_3e_windows | 실패 | adaptability_change observations 0 |
| 4 | assert_4_report_flow | 실패 | draft → final not reached |
| 2b | assert_2b_no_preempt | 실패 | planning_checkin: colleague asked about 2번 2 times<br>collab_disagree opinion not one of fixed_opinions |
| 3a | assert_3a_labels | 실패 | planning_checkin label acknowledge != feedback<br>adaptability_change label None != replan_and_apply<br>collab_disagree label None != explain_with_reason<br>honesty_report label None != fair_report<br>planning_division evidence types ['message'] lack ['task_event']<br>planning_checkin evidence types ['message'] lack ['open']<br>adaptability_change evidence types [] lack ['document']<br>adaptability evidence has no document/share |
| 3c | assert_3c_work_memory | 실패 | part 4 v2 lacks 재참여<br>part 5 v2 lacks 이번 분기<br>part 4 has no v3<br>board part 3 moves ['doing']<br>board part 4 moves ['doing']<br>board part 5 moves ['doing'] |
| 3f | assert_3f_documents | 실패 | no final report |
| 3g | assert_3g_delay_notice | 통과 |  |
| 9 | assert_9_cost | 통과 |  |

## 카드 시각(분, 오차는 초)

| 카드 | 상태 | 예정 | fired | 첫 메시지 | fired 오차 | 메시지 지연 |
|---|---|---|---|---|---|---|
| kickoff | done | 0.0 | 0.018 | 0.09 | 1.1 | 4.3 |
| planning_division | done | 0.5 | 0.521 | 0.55 | 1.3 | 1.7 |
| collab_help | done | 1.5 | 1.525 | 1.55 | 1.5 | 1.5 |
| planning_checkin | done | 2.25 | 2.28 | 2.34 | 1.8 | 3.6 |
| responsibility_delay | done | 3.0 | 3.033 | 3.04 | 2.0 | 0.4 |
| adaptability_change | done | 3.75 | 3.787 | 3.81 | 2.2 | 1.4 |
| review | failed | 4.5 | 4.541 | 4.59 | 2.4 | 3.0 |
| collab_disagree | failed | 4.5 | 4.541 | None | 2.4 | None |
| honesty_report | pending | 5.5 | None | None | None | None |

## run_id별 도구 호출

| run_id | 자극 | 상태 | 도구 | 토큰(in/out) |
|---|---|---|---|---|
| `96e6a8e7-cfd3-4c89-9d70-39e31c568b6a` | event | finished | - | 7898/323 |
| `b3a7a7d3-ab6d-4c8a-99b1-5a687f6c7748` | message | finished | - | 5990/125 |
| `a8bee3d4-e10b-4e89-ad33-9162df4fcaf6` | division | finished | - | 5450/35 |
| `75869a62-9713-43cb-9dc3-60a9a7d327e0` | event | finished | - | 5738/59 |
| `bfb10286-dc65-4ec9-ac3f-0bf06944ab41` | message | finished | search_documents | 7483/346 |
| `e3d19920-fc5d-4735-867b-36d9a828ce01` | event | finished | - | 11974/156 |
| `be8c7d0a-a887-478f-909d-d8a25eb5948b` | message | finished | search_documents | 7595/107 |
| `62b2244d-5195-4d54-9af0-23435417f49a` | message | finished | - | 5660/77 |
| `a781547b-ef22-4685-933c-e3f76b49308d` | message | finished | - | 602/64 |
| `515c8385-a090-42e5-8c34-7072e77cf02f` | event | finished | - | 39964/1266 |
| `a55f5b54-5a60-46df-ba66-ba292e6b9937` | message | finished | search_documents | 8269/96 |
| `25c5c743-a74e-4dfd-9816-4b1155653061` | message | finished | search_documents | 8593/188 |
| `2e3247c8-9f19-4b6d-b179-a942b644fc85` | message | finished | search_documents | 8688/109 |
| `adff3dc6-f408-405b-b3a9-039615ad022c` | event | finished | - | 5275/103 |
| `b1354593-759d-4814-944a-db0f3c9ee809` | message | finished | search_documents | 8843/159 |
| `e9e789a1-f845-4860-a4eb-38c73ab7424d` | event | finished | - | 9158/209 |
| `c122349d-d99e-4597-9671-b50346a80342` | message | finished | search_documents | 9283/172 |
| `0123fb55-f618-414a-b6ae-72b9b4067336` | event | failed | - | 12330/411 |

## 실패한 step

- {'index': 13, 'at': 'review', 'action': 'open', 'error': 'POST /documents/4af8f5c6-c479-4618-98ac-4e8a862b7007/open → 404 {"error":{"code":"not_found","message":"shared version not found"}}'}
- {'index': 14, 'at': 0.1, 'action': 'say', 'error': 'no ack for 4번 사례 하나는 후속 모임 제안 기능이 있는 서비스로'}
- {'at': 'collab_disagree', 'error': 'card message not received'}
- {'index': 15, 'at': 'collab_disagree', 'action': 'say', 'error': 'no ack for 말씀 일리 있어요. 다만 2·8번처럼 일정을 놓친 경우'}
- {'index': 16, 'at': 0.3, 'action': 'import', 'error': 'PUT /final/sections/1/import → 409 {"error":{"code":"conflict","message":"session is failed"}}'}
- {'at': 'honesty_report', 'error': 'card message not received'}
- {'index': 17, 'at': 'honesty_report', 'action': 'say', 'error': 'no ack for 1·2번은 제가 썼고, 3번은 도현님 골격에 제가 보탰'}
- {'at': 'report', 'error': 'report_ready not reached'}
