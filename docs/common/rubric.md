# 평가표 (관찰 체크리스트)

원칙: 점수는 **지원자 행동만** 센다. 산출 경로는 "LLM이 창 안 행동을 레이블·보조 판정으로 분류 → 규칙이 그 결과와 순수 지표를 평가표 조건에 대입해 1/0/기록 없음"이다. 즉 **AI 분류를 입력으로 규칙 점수를 계산하고 사람이 검토·확정**한다(AI가 점수를 '판단'하지는 않지만 분류 오류가 점수에 영향을 줄 수 있으므로 항목마다 근거를 보이고 담당자가 조정한다). 동의·디브리핑·리포트 문구도 이 표현을 쓴다. 항목 정의는 `scenarios/catalog.yaml`의 각 카드 `rubric`이 정본이고, 이 문서는 규칙과 지표 정의를 설명한다.

## 항목 값과 요소 점수

| 관찰 행 상태 | 레이블 기반 항목(`label_in` 포함) | metric 기반 항목 |
|---|---|---|
| 카드 레이블 | 조건대로 1/0 | 조건대로 1/0 |
| `unclassified` / null(LLM 실패) | 기록 없음(null) | 조건대로 1/0 (metrics는 순수 함수) |
| `no_evidence` / 관찰 행 없음 | 기록 없음 | 기록 없음 |
| metric 값이 null | — | 기록 없음. 단 `response_minutes`는 창 안 활동이 있는데 관련 메시지가 없으면 0 |
| `only_if` 불충족 | 기록 없음(사유 not_applicable) | 동일 |
| 카드 메시지가 창 끝에 늦게 전달됨 | 기록 없음(사유 window_missed) | 동일 |

기록 없음에는 항상 사유를 붙인다: `no_activity`(지원자 활동 없음), `classify_failed`(LLM 실패·unclassified), `event_not_fired`(조기 제출 등으로 카드 미발생), `not_applicable`, `window_missed`. 리포트와 화면은 사유를 함께 보여 준다. 0점(미충족)은 근거 행을 요구하지 않는다.

- 요소 점수 = 충족 수 / 판정된 항목 수. 표기 `3/4 · 기록 없음 0`, `2/3 · 기록 없음 1`. 전부 기록 없음이면 `–/0 · 기록 없음 4`.
- 합계 = 선택 요소의 충족 합 / 판정 합. 표기 `9/14 · 기록 없음 2 (요소 4개)`. 가중치·정규화 없음. 만점은 선택 요소 수 × 4이므로 같은 채용 건 안에서만 비교한다.
- 담당자 조정: 항목을 1/0/null로 바꿀 수 있고 바꾸면 메모 필수. 최종값 = 조정 행이 있으면 reviewer_value(null 포함), 없으면 자동 값. 요청에 같은 item_id가 두 번 오면 400. 조정 저장·합계·approving 전이는 한 트랜잭션. 검토 완료 뒤 재조정은 409. 조정 메모는 해당 관찰 문장 옆에도 표시해 자동 서술과 담당자 정정이 함께 보이게 한다.
- 지원자 목록: 요소별 "충족/4" 칩(기록 없음은 회색)과 합계, 출처(`auto`/`reviewer`). 헤더에 "기록 없음은 분모에서 빠지므로 비율만으로 비교하지 않는다" 한 줄. 점수 정렬 없음.
- ai_usage와 산출물 품질은 점수화하지 않는다.

## 조건 문법 (`when`)

`label_in: [..]`, `metric: <이름>` + `eq: <값>` 또는 `lte: <수>`, `all: [조건, ...]`. 세 가지뿐이다. 한 항목에 `label_in`과 `metric`이 함께 있으면 둘 다 충족해야 한다.

## 지표 정의 (observe `compute_metrics`)

입력: 창 안의 지원자 메시지(각 메시지의 `meta.classification`: recipient, kind, related_card 포함), revision, doc_view, assistant_call. "관련 메시지" = classification.related_card가 이 카드이거나 LLM 분류의 `aux.related_message_ids`에 든 메시지. 각 지표는 `{value, evidence_ids}`를 돌려준다.

| 지표 | 타입 | 정의 |
|---|---|---|
| response_minutes | float·null | 카드 메시지 시각부터 **관련** 지원자 메시지 중 첫 것까지 분. 관련 메시지 없으면 null(활동은 있으면 0점 처리) |
| first_recipient | manager·colleague·null | 첫 관련 메시지의 recipient |
| responded_to_request | bool | 협력: 관련 메시지가 1건 이상 |
| response_specific | bool·null | 협력: aux.is_specific (돕는 방식·시점 또는 이유가 구체적) |
| notified_before_release | bool | 책임감: 자료 공개 시각 전에 지연을 언급한 관련 메시지가 있음 |
| notified_in_team | bool | 책임감: 팀 채널에 지연을 언급한 관련 메시지가 있음(팀장이 보는 곳) |
| proposes_alternative | bool·null | 책임감: aux.has_alternative (먼저 할 일·대안 제시) |
| doc_opened_after_release | bool | 공개 뒤 해당 문서 doc_view가 있음 |
| document_changed_after | bool | 카드 이후 지원자 revision이 있음(대상 변경 반영은 레이블 우선순위가 판단) |
| mentions_scope_or_division | bool | 관련 메시지가 범위·일정·분담 재조정을 언급(키워드 + aux) |
| redirected_colleague | bool | 유연성: recipient=colleague이고 kind ∈ {redivide, instruction}인 메시지가 창 안에 있음(동료 수락 여부 무관, 팀장에게 한 제안은 제외) |
| policy_doc_opened | bool | 운영 정책 doc_view (사실 표시만) |
| mentions_policy | bool | 관련 메시지가 운영 정책 문서명이나 "유료 기능 없음"을 언급 |
| proposes_fix | bool·null | 존중: aux.has_fix |
| colleague_revised_after_feedback | bool | 지원자 첫 지적 이후 위반 파트에 by=colleague revision (사실 표시만, `aux_facts`) |

`aux_facts`로 지정된 지표와 창 밖 관련 메시지(related_card가 이 카드인데 창 밖)는 점수와 무관하게 리포트 섹션에 사실로 표시한다. 근거 항목마다 직전 동료·팀장 메시지 1개와 카드 발생 시각을 맥락으로 붙인다(점수 아님).

## 리스크와 파일럿 측정

- 한 창에 레이블 하나라 오분류 1번이 1~2점을 움직인다. 항목마다 근거를 보여 주고 담당자가 조정한다. 파일럿에서 **담당자 조정 비율**을 근거 정확도와 함께 잰다.
- 응답 시간 기준(5분·10분)은 파일럿 값이다.
- 요소를 적게 고르면 창이 길어지고 만점이 줄어든다. 채용 건 안 비교만 허용한다.

MVP 제외: 가중치, 채용 건 간 비교·정규화, 점수 정렬·통계, 검토 후 재조정, 기업별 항목 편집, 지원자에게 점수 공개, ai_usage 점수화.
