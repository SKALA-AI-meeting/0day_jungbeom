# prompts 트랙 보고 (W1)

브랜치 `track/prompts`, 커밋 `c068e3c`. main 병합·push 없음.

## 완료 기준 실행 결과

| 기준 | 명령 | 결과 |
|---|---|---|
| 파일 전부 존재, README 표와 일치 | README 표의 8개 경로마다 `test -f`, `find scenarios/prompts -type f` | 8/8 ok. 폴더에는 표의 8개 + README.md만 있음 |
| catalog.yaml 파싱 | `uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('scenarios/catalog.yaml'))"` | parsed |
| 카탈로그 구조·키·시점·rubric 불변 | 원본 대비 brief·debrief·label_texts 값만 빼고 비교(스크래치 스크립트) | `structure_equal True` |
| 페르소나 표 대응표 | 아래 "대응표" | 각 행 반영 위치 표시 |
| 루트 `make lint` | `make lint` | ruff `All checks passed!`, `45 files already formatted`, web `eslint`·`prettier` 통과, exit 0 |
| (추가 확인) guard 예문 | 각 그룹 hit 예문이 걸리고, miss 예문과 안내문 3개는 어떤 패턴에도 걸리지 않는지 검사 | `bad 0` |
| (추가 확인) 픽스처 | YAML 파싱 + 정규식 컴파일 | grounding 10건, preemption 5건, regex ok |
| (추가 확인) 카탈로그 소비 코드 | `cd services/api && uv run pytest -q tests/test_scenario.py` | 1 passed |

`make lint`는 `apps/web`에서 `pnpm install`을 돌렸지만(node_modules, git 무시) 추적 파일은 바뀌지 않았다.

## 수정 파일

- 추가: `scenarios/prompts/colleague.md`, `manager.md`, `assistant.md`, `common_rules.md`, `guard_patterns.yaml`, `observe_labels.md`, `fixtures/preemption.yaml`, `fixtures/grounding.yaml`
- 수정: `scenarios/prompts/README.md`(표 8행, 로더용 블록 이름), `scenarios/catalog.yaml`(문구만)

카탈로그 문구 변경:
- cooperation `debrief`: "00:30 무렵" 삭제(세션 길이에 따라 시각이 달라짐). label_texts `acknowledge_only`·`ignore` 다듬음
- responsibility label_texts 4개 다듬음(`notify_with_alternative`를 rubric 조건과 같게 "자료가 공개되기 전에 … 팀이나 동료에게"), debrief에 "지원자님에게만" 추가
- flexibility label_texts `refuse_or_ignore`·`apply_silently`, debrief
- respect label_texts `not_noticed`, debrief
- `review`·`report_request` brief: 공유 문장 예시, 판정 금지 추가
- 세 카드의 label_texts에 "판정 우선순위와 예시는 prompts/observe_labels.md" 주석

## 대응표 (agent/design.md 페르소나 표 → 파일·절)

### 3층 표

| 층 | 동료 | 팀장 | 어시스턴트 |
|---|---|---|---|
| 성향(values·style) | colleague.md §1 성향, §2 말투 | manager.md §1, §2 | assistant.md §8 말투 |
| 의무 액션(must) | colleague.md §4 의무 액션, §5 카드 brief, §6 자기 파트, §8 문서 인용 | manager.md §5 카드 brief | assistant.md §2 근거와 인용 |
| 금지 – 평가 보호(must_not_preempt) 5개 | colleague.md §9 1~5, in_window_help는 §9 하위절 / fixtures/preemption.yaml 5건 | manager.md §3, §10 마지막 줄(리드 결정 선점 금지) | — |
| 금지 – 공통(must_not) | colleague.md §11, common_rules.md §2·§4·§5 / guard_patterns.yaml verdict·staging·future | manager.md §10 | assistant.md §6 |

### 항목 표

| 항목 | 동료(이도현) | 팀장(한서윤) | 어시스턴트 |
|---|---|---|---|
| 리드에 대한 태도 | colleague.md §3 | manager.md §3 | — |
| 대행 범위 | colleague.md §3(both), §9-5(대필 금지) | manager.md §4 | assistant.md §1 |
| 자기 파트 | colleague.md §6, §7(work_notes·progress 일관성) | — | — |
| 평가 기준·연출 질문 | common_rules.md §3 안내문, colleague.md §11 | common_rules.md §3, manager.md §8 | common_rules.md §3, assistant.md §5 |
| 추가 자료 요청 | colleague.md §8 마지막 줄 | manager.md §6 고정 대응 | assistant.md §2(공개 문서 범위 밖) / grounding g10 |
| 업무 외 요청 | colleague.md §10 마지막 줄 | manager.md §9 | assistant.md §4 |
| 보는 기록 | colleague.md §12 | manager.md §11 | assistant.md §7 |

### 카탈로그 persona 키

| 키 | 위치 |
|---|---|
| colleague.values / style / self_note | colleague.md §1·§2 |
| manager.values / style | manager.md §1·§2 |
| must | colleague.md §4 |
| must_not_preempt | colleague.md §9 |
| in_window_help | colleague.md §9 "이 창에서도 해도 되는 것" |
| identity | colleague.md §10, common_rules.md §3 정체 질문 |
| must_not | colleague.md §11, common_rules.md §2·§4 |
| (design) 작업 기억 | colleague.md §7 |
| (design) observe·레이블 규칙 | observe_labels.md §1(evidence·하지 않음 레이블), §2(aux), §3(요소별) |

## 남은 문제

1. guard 패턴은 예문 기준으로만 검증했다. 실제 생성문에서의 오탐·미탐은 agent-min의 guard 단위 테스트와 live 실행에서 확인해야 한다. 업무 용어와 겹치는 단어(시나리오, 테스트, 평가, 점수)는 문맥 결합형으로만 걸었다.
2. observe 판정 우선순위(협력: negotiate_timing 먼저, 책임감: ask_colleague가 notify_only보다 먼저, 존중: blaming 먼저)는 이 트랙이 정했다. 카탈로그에는 유연성만 우선순위 주석이 있었다. 리뷰에서 확인 필요. e2e `all_four`의 기대 레이블 4개와는 맞춰 두었다.
3. preemption의 `must_not_regex`·`should_regex`는 live·리뷰용 보조 검사다. mock 테스트에서는 FakeLLM 응답이 고정이므로 프롬프트·컨텍스트 조립 검사로 써야 한다.

## 변경 요청

- 없음(소유권 밖 파일은 수정하지 않음).
- 제안: `docs/common/harness.md` Context 행의 "미래 상황 유도 질문 3건·미공개 문서 질문·역할 사칭 질문 픽스처"는 아직 담당 파일이 없다. 미공개 문서 질문은 grounding g05·g09로 덮었고, 나머지는 guard_patterns.yaml future·staging 예문으로 일부만 덮는다. 별도 픽스처가 필요하면 prompts 트랙 범위로 추가할지 정해 달라.

## 다른 트랙에 알릴 것

- **agent-session / agent-assistant (로더)**: 프롬프트 본문에는 치환 변수가 없다. system = `common_rules.md` + 페르소나 파일. 실행 맥락은 `[실행할 카드]`, `[작업 기억]`, `[문서 검색 결과]`, `[최근 대화]`, `[보드·문서 상태]` 블록 이름으로 붙인다(README "조립 방식"). observe는 `observe_labels.md`만 쓰고 입력 블록은 `[카드]`·`[창 안 지원자 활동]`·`[맥락]`, 출력은 `{label|null, evidence, aux}` JSON. 허용 밖이면 `label: null` → unclassified.
- **agent-min (guard)**: `guard_patterns.yaml` 형식: `groups[].patterns`(Python re, IGNORECASE), `groups[].replacement` → `notices` 키, 문장 단위 치환(`sentence_split`), 같은 안내문 중복 제거, `max_chars: 600`. `examples.hit/miss`를 단위 테스트 픽스처로 쓰면 된다. 인용 검사는 `citation.titles[].aliases`(동료 말투 인용 허용)와 `assistant_source_line`(어시스턴트 출처 줄).
- **agent-session (테스트)**: `fixtures/preemption.yaml` 5건(id: delay_alternative, flexibility_redivide, polish_keeps_violation, cooperation_withdraw, ghostwrite_candidate_part), `fixtures/grounding.yaml` 10건(persona colleague 5, assistant 5. g05·g09는 인터뷰 미공개 상태, 기대 도구 `get_document`, 답 "아직 공유되지 않은 자료").
- **report-worker**: label_texts 문장이 바뀌었다(리포트 observed 문장). 합격·순위 표현 없음. cooperation debrief에서 시각("00:30 무렵")을 뺐다.
- **api (foundation)**: `prompts/fixtures/`가 하위 폴더로 생겨 `read_prompts`(rglob)가 `fixtures/preemption.yaml` 같은 키로 scenario에 복사하고 catalog_version 해시에도 들어간다. 의도대로면 그대로 두고, 픽스처를 scenario 복사에서 빼고 싶으면 foundation 쪽 결정이 필요하다.
