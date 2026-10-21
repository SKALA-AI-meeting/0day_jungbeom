# api 트랙 CR (2026-10-21)

어느 것도 구현을 멈추게 하지는 않았다. 계약 본문은 바꾸지 않았다.

| # | 대상 | 내용 | 영향 | 제안 |
|---|---|---|---|---|
| CR-1 | `docs/common/testing.md` "단계 시드" | 토론형 단계 시드의 step 키가 정의돼 있지 않다("e2e 대본과 같은 문법"이라고만 적혀 있고 `scenarios/e2e/*.yaml`은 아직 옛 업무형 키). api 재생기는 `at`(절대 분·`+분`), `say`(+선택 `intent`: 의도 분류 고정 결과), `ai`(`seat`·`content`·`propose`·`support`·`oppose`·`card_ids`·`is_invite`), `confirm`(`phase`·`option_key`·`value`), `proposal`(칸 일부 덮어쓰기), `submit`를 읽는다(`services/api/app/services/test_sessions.py` 머리말). | stage-kit이 같은 키로 시드를 써야 한다 | testing.md "단계 시드"에 이 키 표를 정본으로 올리고 e2e 대본도 같은 키를 쓴다 |
| CR-2 | `tests/fixtures/contracts/internal_rubric.json`, `internal_assistant_calls.json`, `internal_session.json`, `report.json` | S1 계약과 픽스처가 다르다: rubric `cards[].window`가 문자열(`"stage"` 등, 계약은 cards.yaml 객체 그대로 + `stage_id`), assistant_calls에 `request`·`response` 없음, internal session `position.name` 없음, report `review`가 null만 있음(계약 `{reviewer_name, reviewed_at}`). api는 계약 본문을 따랐다 | 픽스처를 읽는 mcp·워커 테스트가 옛 형태를 기대할 수 있다 | 오케스트레이터가 픽스처를 S1 계약으로 갱신 |
| CR-3 | `docs/common/contracts.md` "칸 상태" 정규화 | "앞뒤 공백·구두점 제거"가 가장자리만인지 중간 구두점(`·`)까지인지 모호하다. 구현은 WIP대로 모든 구두점을 지우고 공백을 하나로 접는다(`도심 폭우·침수` = `도심 폭우침수`) | 지원자 확정 값의 안 연결 범위 | 의도가 가장자리만이면 알려 주면 한 줄로 고친다 |
