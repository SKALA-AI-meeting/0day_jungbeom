# 시나리오 모델

## 요소 카탈로그 (`scenarios/catalog.yaml`)

MVP는 인성 요소 4개만 둔다. 카드 하나의 필드:

| 필드 | 뜻 |
|---|---|
| `id` | `cooperation`, `responsibility`, `flexibility`, `respect` |
| `name` | 협력 태도, 책임감, 유연성, 존중·소통 |
| `order` | 배치 순서. 1~4 고정 |
| `actor` | `colleague`, `system`, `manager` |
| `channel` | `team` 또는 `dm` |
| `brief` | 페르소나에게 주는 전달 내용 골격 (문장은 LLM이 생성). system은 고정 문장 |
| `effects` | 카드 실행 시 부수 효과. 예: `release_document: interview_summary, delay_fraction: 0.125` |
| `labels` | 관찰 레이블 목록. 예: 협력 `help / decline / negotiate_timing / ignore` |
| `metrics` | 규칙 지표 목록. 예: `first_recipient, response_minutes, doc_opened` |
| `unselected` | 미선택 시 처리. 예: 책임감 `release_at_start: interview_summary`, 존중 `review_without_violation` |
| `requires_docs` | 필요한 회사 문서 id |

흐름 카드(`kickoff`, `division`, `review`, `report_request`)는 `flow: true`로 항상 포함된다. 존중 카드는 `attach_to: review`로 리뷰와 같은 시점에 실행된다.

## 조립 (`positions.scenario`)

채용 건 생성 시 api가 한 번 계산해 저장한다.

```
L = session_minutes
flow: kickoff 0, division L/12, review 3L/4, report_request 11L/12
selected = elements를 order로 정렬
non_review = selected 중 attach_to가 없는 카드
n = len(non_review)
시점: n==1 → L/4; n>=2 → L/4 + i*(L/2)/(n)  (i=0..n-1)
```

L=120, 4개 선택: cooperation 30, responsibility 50, flexibility 70, respect 90(=review). PRD와 동일.
L=120, 3개(협력·책임·유연): 30, 50, 70. L=6, 4개: 1.5, 2.5, 3.5, 4.5분.

저장 형식:

```json
{"session_minutes": 120,
 "cards": [
  {"card_id":"kickoff","at_min":0},
  {"card_id":"division","at_min":10},
  {"card_id":"cooperation","at_min":30},
  {"card_id":"responsibility","at_min":50,"effects":{"release_document":"interview_summary","at_min":65}},
  {"card_id":"flexibility","at_min":70},
  {"card_id":"review","at_min":90,"with":"respect"},
  {"card_id":"report_request","at_min":110}],
 "releases_at_start": ["company_intro","metrics","policy","meeting_notes"]}
```

세션 시작 시 api가 `cards`를 `session_events`로, `releases_at_start`와 지연 공개를 `document_releases`로 펼친다.

## 관찰 창

카드 i의 창은 `fired_at(i)`부터 다음 카드의 `fired_at` 또는 세션 종료까지. 창 안의 지원자 메시지, 문서 변경, 어시스턴트 호출이 observe의 입력이다. 흐름 카드는 관찰하지 않는다. AI 활용은 창과 무관하게 세션 전체를 본다.

## 회사 문서 (`scenarios/documents/`)

| id | 파일 | 역할 |
|---|---|---|
| `company_intro` | company_intro.md | 루프랩·모아런 소개 |
| `metrics` | metrics.md | 재참여율 22% 등 지표 |
| `interview_summary` | interview_summary.md | 첫 참여자 8명 인터뷰. 책임감 카드의 지연 대상 |
| `policy` | policy.md | 올해 유료 기능 없음, 위치는 동네 단위. 존중 카드의 근거 |
| `meeting_notes` | meeting_notes.md | 재참여율을 최우선 과제로 정한 회의 |

## 디브리핑

`session_events`에서 `fired_at`이 있는 요소 카드만 골라 카탈로그의 `debrief` 문장을 보여 준다.
