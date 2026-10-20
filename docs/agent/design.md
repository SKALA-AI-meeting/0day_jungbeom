# 에이전트 설계 (api 안의 LangGraph 모듈)

## 세션 그래프

State (TypedDict):
`session_id, phase(kickoff|negotiate|work|review|submit|done), negotiate_round, division, scenario, fired_cards, pending_card, window_start, stimulus{type, event_id?, message_id?}, recent_messages, summary, tool_calls_used, token_budget_left, last_error`

| 노드 | 역할 | 다음 |
|---|---|---|
| route | stimulus.type과 phase로 분기 | kickoff / negotiate / respond / observe / submit |
| kickoff | 팀장 브리프 post_message(team) → 동료 인사 → 분담안 제안(dm). set_division 초안. phase=negotiate | END |
| negotiate | 지원자 메시지를 accept/modify로 분류(구조화 출력). modify면 조정안 생성, round+1. round>3 또는 accept면 set_division, update_task, phase=work | END |
| respond | work·review 단계 일반 대화. tool-calling 루프(search_documents, get_board, get_document_state, 최대 3회). 문서 인용 시 문서명 포함 | END |
| observe | window_start~now의 지원자 메시지·문서 변경·어시스턴트 호출을 observe-rules에 넘겨 metrics·label·evidence 산출 → record_observation | inject |
| inject | pending_card 실행. system: 고정 문장 post_message + release_document 예약 확인. colleague/manager: brief로 생성. review 카드면 write_document_part(4,5)와 공유 메시지(존중 선택 시 위반 포함). window_start=now | END |
| submit | 마지막 창 observe → 팀장 보고 응답 → phase=done | END |
| guard | 모든 생성 텍스트에 적용. 금지 패턴 치환, 길이 제한 | (함수) |

이벤트 자극은 route → observe → inject. 흐름 카드(division은 kickoff에 포함, report_request)는 observe 없이 inject.

Agentic 요소: respond는 모델이 도구를 고른다. observe·inject·route는 결정적이다.

## 어시스턴트 그래프

`retrieve(search_documents top3) → answer(인용 포함) → guard`. thread `assistant:{session_id}`. 호출 60회 초과 시 고정 안내문. 평가 기준·연출 상황 질문은 guard가 안내문으로 치환. 요청·응답을 `assistant_calls`에 기록(api가 처리).

## observe-rules (`app/agent/observe/`)

순수 함수 `compute_metrics(window, card) -> dict`와 `classify(window, card, llm) -> (label, evidence_ids)`. 레이블은 카탈로그의 `labels`만 허용, 벗어나면 `unclassified`. temperature 0, 구조화 출력.

## 하네스
`docs/common/harness.md` 참조. Recovery: LLM 래퍼가 2회 재시도 후 `FallbackText`를 반환하면 노드는 고정 문장을 post하고 `last_error`에 기록. 다음 자극에서 정상 재개.

## 완료 기준
- agent-session: 6분 테스트 세션 + 대본으로 카드 4개 정시 발생, 분업 3회 거절 후 확정, api 재시작 후 이어하기, guard 테스트, LangSmith trace
- agent-assistant: 공개 문서만 인용, 미공개 문서 질문에 "아직 공유되지 않은 자료" 답변, 60회 한도
- observe-rules: 카드별 픽스처 창에 대해 기대 metrics·label 단위 테스트
