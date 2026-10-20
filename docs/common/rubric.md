# 평가표 (관찰 체크리스트)

원칙: 점수는 **지원자 행동만** 세고, **규칙으로** 산출한다. LLM은 창 안 행동을 레이블로 분류하는 데까지만 쓰이고, 레이블·지표를 점수로 바꾸는 건 카탈로그의 `rubric` 조건이다. 담당자가 항목별로 조정해 확정한다. 항목 정의는 `scenarios/catalog.yaml`의 각 카드 `rubric`이 정본이고, 이 문서는 규칙과 지표 정의를 설명한다.

## 항목 값과 요소 점수

| 관찰 행 상태 | 레이블 기반 항목(`label_in` 포함) | metric 기반 항목 |
|---|---|---|
| 카드 레이블 | 조건대로 1/0 | 조건대로 1/0 |
| `unclassified` / null(LLM 실패) | 기록 없음(null) | 조건대로 1/0 (metrics는 순수 함수) |
| `no_evidence` / 관찰 행 없음 | 기록 없음 | 기록 없음 |
| metric 값이 null | — | 기록 없음. 단 `response_minutes`는 창 안 활동이 있는데 메시지가 없으면 0 |

- 요소 점수 = 충족 수 / 판정된 항목 수. 표기 `3/4 · 기록 없음 0`, `2/3 · 기록 없음 1`. 전부 기록 없음이면 `–/0 · 기록 없음 4`.
- 합계 = 선택 요소의 충족 합 / 판정 합. 표기 `9/14 · 기록 없음 2 (요소 4개)`. 가중치·정규화 없음. 만점은 선택 요소 수 × 4이므로 같은 채용 건 안에서만 비교한다.
- 담당자 조정: 항목을 1/0/null로 바꿀 수 있고 바꾸면 메모 필수. 조정 안 한 항목은 자동 값. 검토 완료 뒤 재조정은 409.
- 지원자 목록: reviewed면 담당자 합계, 아니면 자동 합계 + 출처(`auto`/`reviewer`). 점수 정렬 없음.
- ai_usage와 산출물 품질은 점수화하지 않는다.

## 조건 문법 (`when`)

`label_in: [..]`, `metric: <이름>` + `eq: <값>` 또는 `lte: <수>`, `all: [조건, ...]`. 세 가지뿐이다. 한 항목에 `label_in`과 `metric`이 함께 있으면 둘 다 충족해야 한다.

## 지표 정의 (observe `compute_metrics`)

| 지표 | 타입 | 정의 (창 안 데이터만) |
|---|---|---|
| response_minutes | float·null | 카드 메시지 시각부터 지원자의 첫 메시지(어느 채널이든)까지 분. 메시지 없으면 null |
| first_recipient | manager·colleague·null | 지원자 첫 메시지의 수신자(수신자 규칙) |
| notified_before_release | bool | 자료 공개 시각 전에 지연을 언급한 지원자 메시지가 있음 |
| notified_manager (신규) | bool | 창 안 지원자 메시지 중 팀장이 수신자인 것이 있고 지연·일정을 언급함. 순서 무관 |
| doc_opened_after_release | bool | 공개 뒤 해당 문서 doc_view가 있음 |
| document_changed_after | bool | 카드 이후 지원자 revision이 있음 |
| mentions_scope_or_division | bool | 범위·일정·분담 재조정을 언급(키워드 + 분류 보조) |
| redivide_requested (신규) | bool | 창 안 지원자 메시지 중 respond 앞 분류가 `redivide`인 것이 1건 이상(동료 수락 여부 무관) |
| policy_doc_opened | bool | 운영 정책 문서 doc_view가 있음(근거 표시만) |
| mentions_policy | bool | 운영 정책 문서명이나 "유료 기능 없음"을 언급 |
| proposes_fix (신규) | bool | 동료 파트의 문제를 언급한 메시지에 대안·수정 방향이 있음(분류 보조 출력 `has_fix`) |
| colleague_revised_after_feedback (신규) | bool | 지원자 첫 지적 이후 위반 파트에 by=colleague revision이 있음. 근거 표시만, 점수 아님 |
| response_specific (신규) | bool | 도움 요청 응답에 방식·시점 또는 이유가 구체적으로 있음(분류 보조 출력 `is_specific`) |

분류 보조 출력: observe의 LLM 분류는 레이블과 함께 `has_fix`, `is_specific` 두 bool을 구조화 출력으로 내고, 각각 proposes_fix·response_specific에 쓴다. 레이블이 null이면 둘도 null이다.

## 리스크와 파일럿 측정

- 한 창에 레이블 하나라 오분류 1번이 1~2점을 움직인다. 항목마다 근거를 보여 주고 담당자가 조정한다. 파일럿에서 **담당자 조정 비율**을 근거 정확도와 함께 잰다.
- 응답 시간 기준(5분·10분)은 파일럿 값이다.
- 요소를 적게 고르면 창이 길어지고 만점이 줄어든다. 채용 건 안 비교만 허용한다.

MVP 제외: 가중치, 채용 건 간 비교·정규화, 점수 정렬·통계, 검토 후 재조정, 기업별 항목 편집, 지원자에게 점수 공개, ai_usage 점수화.
