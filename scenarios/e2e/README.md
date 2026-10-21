# e2e 대본

`tests/e2e/run.py`가 읽는 세션 대본이다. 형식·단언은 `docs/guides/testing.md` e2e 절이 정본이고, 단계 시드(`stages/`)는 stage-kit 소유다. 문장은 결정적 LLM 모드(`LLM_FAKE=1`)의 의도 분류 규칙(안 라벨이 문장에 있으면 그 안, "좋아요" agree, "아니·반대" oppose, 물음표 question)에 맞춰 쓴다.

| 대본 | 우선순위 | 내용 |
|---|---|---|
| `all_five` | P0 | 5요소 전부. 키워드 지원자 확정, 문제 상황 수용 카드 승복, 해결책 소극형 지명 후 합의 채우기, 제출 → 리포트 → 검토 → final |
| `timeout_all` | P0 | 세 단계 모두 시간 초과 채우기, 기획안 자동 제출 |
| `honesty_claim` | P0 | C7 정직 대조(비판형이 처음 낸 해결책을 본인 제안으로 적음) |
| `restart` | P1 | 문제 상황 단계 중 api 재시작 |

## 최상위 키

- `name`, `priority`, `minutes`(15 고정)
- `expect.slots`: 단계별 `resolution`·`filled_by`(생략하면 확인 안 함)
- `expect.cards`: 발동·전달돼야 할 카드 id. 단계가 카드 예정 시각 전에 끝나 미발생인 카드는 적지 않는다
- `expect.dimensions`: 차원별 기대. `evidence`(근거로 나와야 할 참조 문자열), `no_record_reason`, `level`(결정적 LLM 모드에서만 확인). 총점 기대값은 없다
- `expect.contribution`: 단계별 `first_proposer`, `credited`(기획안에 최초 제안자 표기가 있는지)
- `expect.observations`: 관찰이 1건씩 있어야 할 카드 id
- `expect.restart`: `reconnect_within_seconds`
- `review`: `reviewer_name`, `adjust: {dimension_id, level, memo}`. 있으면 러너가 단언 6의 검토 흐름을 돈다

## step

`at`은 필수다. 한 step에 동작이 여러 개면 아래 순서로 실행한다.

| `at` 값 | 뜻 |
|---|---|
| `12.5` | 세션 시작 기준 절대 분 |
| `"+0.2"` | 직전 step을 끝낸 시각에서 분 (YAML이 숫자로 읽지 않게 따옴표로 쓴다) |
| `card:<id>` | 그 카드 관찰이 생길 때까지 |
| `phase:<id>` | 그 단계가 시작될 때까지(가짜 시계 모드는 마감까지 시간을 당긴다) |
| `msg:<seat>` | 지금부터 그 자리(`p1`~`p3`)의 새 메시지가 올 때까지 |
| `ended` | 세션 종료(`session.ended`)까지 |

| 키 | 호출 |
|---|---|
| `say: 문장` | WS `typing` start(5초 갱신) → `message.send` → ack 대기 → `typing` stop |
| `confirm: {phase, value, option_key?}` | `POST /sessions/{id}/slots/{phase}/confirm` |
| `material: material_id` | `GET /sessions/{id}/materials/{material_id}` |
| `assistant: 질문` | `POST /sessions/{id}/assistant` |
| `proposal: {필드: 문장}` | 현재 기획안을 읽어 필드를 덮고 `PUT /sessions/{id}/proposal` |
| `restart: api` | api 재시작(`E2E_RESTART_CMD` 또는 관리 스택) 뒤 resume → `/state` → WS 재연결 |
| `submit: true` | `POST /sessions/{id}/proposal/submit` |

시계는 러너 옵션 `--clock real|fake`다. `real`은 벽시계로 기다리고(실 스택 15분), `fake`는 내부 테스트 API `advance`로 시간을 당긴다(`ENABLE_TEST_API=1`).

이 러너는 단계 시드 전용 키 `ai`·`say.intent`를 지원하지 않는다(실 스택 대본은 지원자 행동만 쓴다).
