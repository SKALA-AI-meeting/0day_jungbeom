# agent 트랙 계약 변경 요청(CR)

## CR-A1 문제 상황 기준안 잠금의 주체와 경로

- 계약: `contracts.md` "그래프 자극" `session_cards` 항목은 "`card_due` 첫 처리 때 행을 만들고 `locked_option_id`로 잠근다, 그 안의 행이 없으면 잠금 트랜잭션에서 만든다(proposer = 첫 담당 자리)"라고 적는다. `agent/design.md` cards 노드는 "`flexibility_majority`면 여기서 기준안을 계산해 잠근다"라고 적는다.
- 어긋남: 그래프에서 api로 가는 길은 MCP뿐인데 debate-mcp 도구 7개에 잠금 도구나 `post_message`·`propose_option`의 잠금 인자가 없다. 그래서 그래프가 계산한 기준안을 `session_cards`에 쓸 수 없다. 반대로 api 메일박스가 그래프 전에 잠근다면 그 단계를 api 설계에 적어야 한다.
- 현재 agent 구현(멈추지 않고 진행): DebateState `card_progress[].locked_option_id`가 있으면 그 값을 쓴다. 없으면 카드 시점에 같은 규칙("지원자의 현재 지지 안이 아닌 첫 시나리오 안")으로 계산하고, 첫 담당(고집형)의 발언 뒤 `propose_option`으로 행을 만든다. 그 뒤 run에서는 고집형의 현재 지지 안(확정 전 불변)을 기준안으로 이어 쓴다.
- 영향: api가 잠그지 않으면 `session_cards.locked_option_id`가 비어 시간 초과 선택의 문제 상황 기준안 단계(`locked_lead_or_p1`)가 P1로 떨어질 수 있다. C5의 "`session_cards.locked_option_id` = P2" 단언도 api 쪽에서만 성립한다.
- 제안(택1): (a) api 메일박스가 `card_due{flexibility_majority|listening_pressure}`를 꺼낼 때 그래프 실행 전에 `session_cards` 행 생성·잠금을 한다(계약 문구 그대로, agent 변경 없음). (b) `post_message`에 `locked_option_id?`를 더해 카드 첫 발언 게시 트랜잭션에서 api가 잠근다. agent는 (a)를 권한다.

**처리(2026-10-21)**: (a)로 정리됐다. api 메일박스(track/api 8135002)가 `card_due`를 꺼내면 그래프 실행 전 한 트랜잭션에서 `session_cards` 행 생성·기준안 잠금(안 행이 없으면 proposer p1로 생성)을 한다. 그래프는 `card_progress[].locked_option_id`를 우선 쓰고, 대체 규칙은 잠금 값이 없는 경우(단위 테스트의 가짜 서버 등)에만 탄다. agent 코드 변경 없음.
