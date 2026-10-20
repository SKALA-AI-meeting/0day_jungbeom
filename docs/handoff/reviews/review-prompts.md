# prompts 트랙 리뷰

검토 대상: `track/prompts`의 `c068e3c`, `git diff main..HEAD`. 판정: **수정 후 재리뷰 필요 — 병합 차단 4건**. 소스 수정 없이 이 리뷰 파일만 작성했다.

비교 범위 주의: 현재 main에는 분기 이후의 `99f2fff`, `502b88b`, `7b04ef8`이 있다. 따라서 두 끝점 비교에 보이는 `docs/handoff.md` 후퇴와 business-mcp 삭제는 prompts 커밋의 변경이 아니다. `git log main..HEAD`와 `git diff main...HEAD`로 실제 트랙 변경 10개 파일을 대조했으며, 소유권 밖 수정은 없다(`docs/plan.md:53`).

## 1. 반드시 고칠 것(병합 차단)

### R1. [P2] 업무 문장까지 금지 안내문으로 치환하는 guard 패턴을 좁힐 것

- 위치: `scenarios/prompts/guard_patterns.yaml:23`, `:25`, `:27`, `:51`.
- 근거: 사람 평가를 특정하지 않는 `(점수)…`, `평가 기준/결과`, `기록하고`, `테스트하려고`가 정상 업무 답변도 차단한다.
- Python `re.IGNORECASE`로 모든 그룹을 검사한 재현: `사용자 만족도 점수를 성공 지표로 쓰면 어떨까요?`, `가설 평가 기준을 재참여율로 정해요.`, `지난주 회의록 내용을 기록하고 있어요.`는 verdict에 걸리고, `가설을 테스트하려고 소규모 실험을 해요.`는 staging에 걸린다. 모두 현재 기획 과제에서 가능한 문장이다. 문장 전체를 안내문으로 바꾸므로 근거 있는 업무 대화와 검증 계획 안내를 잃는다.
- 권장 처리: 지원자·리드에 대한 판정 또는 현재 평가 운영을 드러내는 문맥을 요구하도록 패턴을 좁히고, 위 문장들을 miss 예문에 추가한다. 실제 LLM 없이 재현되므로 agent-min/live 단계로 미루지 않는다.

### R2. [P2] 일반적인 숫자 점수 발언이 guard를 그대로 통과함

- 위치: `scenarios/prompts/guard_patterns.yaml:21`, `:23`.
- 근거: 점수 단어 뒤 조사만 검사하여 숫자 점수와 콜론 표기를 놓치므로 F-24의 점수 발언 금지를 보강하지 못한다.
- 재현: `현재 4점입니다.`, `이번 응답은 80점이에요.`, `점수: 4/4입니다.`는 어느 그룹에도 매칭되지 않는다. 기존 hit 예문의 `지금 점수는 꽤 높아요`만 잡는 것으로는 흔한 점수 응답을 막지 못한다.
- 권장 처리: 지원자/응답 평가 문맥의 숫자 점수, 점수 표기 구문을 포함하고 hit 예문으로 고정한다. R1과 함께 업무 지표의 점수·비율을 보존하도록 조정한다. 모든 변형을 전수 검사하라는 요구는 아니다.

### R3. [P2] `silent`의 evidence 타입이 명시된 설계 계약과 다름

- 위치: `scenarios/prompts/observe_labels.md:23`, `:68`.
- 근거: 설계는 `silent`의 evidence를 revision으로 정했는데, 새 지시문은 revision이 없으면 다른 활동 id를 쓰도록 하고 assistant_call 예시까지 준다(`docs/agent/design.md:137`).
- 예: 창 안에 어시스턴트 질문만 있으면 이 프롬프트는 `silent + assistant_call`을 정상 출력한다. 계약대로 revision을 요구하는 소비 코드와 충돌하거나, 트랙마다 다른 의미의 관찰이 저장된다. 보고서의 “observe·레이블 규칙 반영”은 이 부분에서 성립하지 않는다.
- 권장 처리: 현재 계약에 맞추려면 revision이 없는 경우 허용 레이블로 분류할 수 없음을 명시하고 null 처리한다. 활동만 있으면 silent를 허용하려는 의도라면 오케스트레이터에게 설계 계약 변경 요청을 올려 양쪽을 함께 확정한다. prompts 트랙에서 임의로 계약을 완화하지 않는다.

### R4. [P2] 자료 공개 전/후를 판정하면서 실제 공개 시각을 입력받지 않음

- 위치: `scenarios/prompts/observe_labels.md:8`, `:65`, `:70`.
- 근거: 입력 정의에는 카드 메시지 시각과 알림 본문만 있고 자료 공개 시각이 없는데, 책임감 레이블은 “자료 공개 전” 여부로 갈린다.
- 책임감 알림은 “약 15분 늦어집니다”라는 고정 text이고 실제 공개 시각은 조립된 `effects.at_min`에 따른다(`scenarios/catalog.yaml:112`, `docs/common/scenario-model.md:49`). 6분 대본에서는 공개 지연이 0.75분이므로 알림의 15분으로 추정하면 공개 뒤 메시지를 공개 전 알림으로 오분류할 수 있다. doc_view가 없는 창에서는 활동 목록으로 공개 시각을 알아낼 수도 없다.
- 권장 처리: observe 전용 `[카드]` 입력에 실제 `release_at`과 일관된 시간 기준을 명시하거나, 코드가 계산한 공개 전/후 사실을 전달하도록 입력 계약을 정의한다. `README.md:27`과 agent-session 인계에도 반영한다. 페르소나 입력으로 관찰 지표를 흘려보내지는 않는다.

## 2. 고치면 좋은 것

1. **[P2] 어시스턴트의 요청 형식 준수와 공통 규칙을 일치시킬 것.** `scenarios/prompts/common_rules.md:50`은 목록 기호를 문서 파트에만 허용하고 우선 적용되므로, “세 항목 목록으로 요약해 줘” 같은 정상 요청에서 `scenarios/prompts/assistant.md:51`의 형식 준수를 막는다. 메신저 페르소나에만 제한하거나 어시스턴트의 사용자 지정 형식을 예외로 둔다.

2. **[P2] 공개 뒤 지연 공유의 레이블 의미를 명확히 할 것.** `scenarios/prompts/observe_labels.md:70`은 공개 전 알림이 없으면 notify_only도 금지하지만 `scenarios/catalog.yaml:121`의 notify_only는 “지연 사실만 알리고 대안은 제시하지 않음”이다. 공개 후 “자료가 늦었는데 이제 받았습니다”라고 알린 행동은 silent도 아니어서 null로 빠진다. 권장: notify_only는 사실 알림으로 유지하고 공개 전 여부는 별도 metric으로 센다. 시간 제한을 유지한다면 label_texts도 그 의미에 맞춰 확정한다.

3. **[P3] 보조 정규식이 정상 응답을 거절하거나 금지 응답을 놓치는 범위를 명시할 것.** `scenarios/prompts/fixtures/preemption.yaml:22`는 자체 금지 예시인 “그동안 지표로 2번을 채우죠”를 잡지 못하고, `:103`은 정상적인 “대신 쓰기는 어려워요. 인터뷰 요약의 관계 형성 문제를 중심으로 묶어 보세요”를 통과시키지 못한다. 정규식은 문구의 보조 검사로만 쓰고, 본문 보존·대필 여부 같은 의미 조건은 명시된 기대 행동과 함께 확인한다.

## 3. 보고서의 결정·남은 문제·변경 요청에 대한 의견

보고서에는 별도 “내가 정한 것” 절이 없어, 실제 추가한 우선순위와 조립 규약을 해당 결정으로 검토했다. 아래 줄은 저장소 파일 기준이며 보고서 쟁점은 항목명으로 식별한다.

| 쟁점 | 의견·권장 처리 | 파일:줄 · 한 줄 근거 |
|---|---|---|
| 내가 정한 것: 협력 negotiate_timing 우선 | **동의.** 뒤에 도울 시점을 제안하면서 짧은 조언도 한 all_four 발화는 negotiate_timing이 적절하다. 다만 나중에 실제로 도운 경우까지 어떤 행동을 대표로 삼을지는 agent-session 분류 예시에서 명확히 한다. | `scenarios/prompts/observe_labels.md:44`, `scenarios/e2e/all_four.yaml:14` · 일정 조율과 즉석 조언이 함께 있는 기준 대본의 기대값을 보존한다. |
| 내가 정한 것: 책임감 ask_colleague 우선 | **동의.** 대안을 내지 않고 도움을 청한 행동을 단순 통보와 구분할 수 있다. 공개 시점·팀 통보·대안은 aux/metrics로 별도 계산한다. | `scenarios/prompts/observe_labels.md:61`, `docs/common/rubric.md:38` · 책임감 점수 조건은 레이블 서열이 아니라 개별 사실이다. |
| 내가 정한 것: 존중 blaming 우선 | **동의.** “비난 중심” 여부를 기준으로 적용하고 근거·수정 제시 여부는 독립적으로 남긴다. 근거가 있다는 이유로 비난을 숨겨서는 안 된다. | `scenarios/prompts/observe_labels.md:92`, `scenarios/catalog.yaml:173` · respect_no_blame 항목은 레이블에 직접 의존한다. |
| 내가 정한 것: 프롬프트 조립 블록·JSON 출력 | **대체로 동의.** 파일별 system 조립과 observe 분리는 적절하다. 단 R3·R4를 해결한 입력/근거 규약으로 인계한다. | `scenarios/prompts/README.md:18`, `scenarios/prompts/observe_labels.md:15` · 현재 정의가 그대로 후속 로더·검증 코드의 기준이 된다. |
| 남은 문제 1: guard는 실제 생성·live에서 추가 확인 | **후속 검증 필요에는 동의, 현재 결함 이월에는 반대.** R1·R2는 패턴 자체의 문제라 이 트랙에서 먼저 수정하고 인계한다. | `scenarios/prompts/guard_patterns.yaml:6` · 기존 hit/miss가 모두 통과해도 추가한 일반 업무·점수 문장에서 실패한다. |
| 남은 문제 2: 우선순위 리뷰 필요 | **위 세 순서에 동의.** 순서와 별개인 silent 계약 및 공개 시각 문제는 병합 전에 해결한다. | `scenarios/prompts/observe_labels.md:39` · 우선순위가 옳아도 입력 정보·근거 타입이 틀리면 판정이 달라진다. |
| 남은 문제 3: mock은 프롬프트·컨텍스트 조립 확인 | **동의.** FakeLLM 고정 답으로 모델의 선점 방지 성능을 증명했다고 보고하지 않는다. live는 live 마커로 분리한다. | `scenarios/prompts/fixtures/preemption.yaml:3`, `docs/dev-process.md:36` · 보조 regex와 실제 모델 행동 검증은 다른 검증이다. |
| 변경 요청 없음·소유권 준수 | **소유권 준수에는 동의.** 실제 변경은 prompts 폴더와 catalog 문구뿐이다. 다만 silent 예외를 유지한다면 R3에 따른 명시적 계약 변경 요청이 필요하다. | `docs/plan.md:53`, `scenarios/prompts/observe_labels.md:23` · 문구 추가가 공용 evidence 계약을 바꾸는 효과까지 허용하지는 않는다. |
| 제안: 미래 유도 3건·역할 사칭 픽스처 담당 미정 | **추가 필요에 동의.** 오케스트레이터가 작성 담당을 지정하고 agent-min/session 완료 검사에 연결한다. 응답 금지 패턴의 예문은 입력 유도 질문·컨텍스트 유출 검사를 대신하지 않는다. 현 W1의 10+5건 수량 미달로 세지는 않는다. | `docs/common/harness.md:7`, `docs/agent/design.md:146` · harness의 컨텍스트 검증 요구와 이번 트랙의 15건 완료 기준은 별도다. |
| 카탈로그 문구만 변경 | **동의.** brief·debrief·label_texts를 제외한 YAML 객체가 main과 동일함을 직접 비교했다. 시점·키·조건·레이블 목록·rubric 변경은 없다. | `scenarios/catalog.yaml:119`, `:139`, `:163` · 책임감 공개 전 표현과 유연성/존중 문구는 항목·상황 설명을 구체화한다. |
| 픽스처 15건으로 완료 기준 대응 | **구성에는 동의.** 근거 10건, 선점 5종 각 1건이 있으며 기대 도구·문서·인용·핵심 사실이 있다. 모델 행동의 실제 통과 여부는 아직 확인된 것이 아니다. | `scenarios/prompts/fixtures/grounding.yaml:1`, `scenarios/prompts/fixtures/preemption.yaml:1`, `docs/agent/design.md:146` · YAML 존재·regex 컴파일과 live 행동 검증을 구분해야 한다. |

## 4. 다른 트랙 주의사항

1. **agent-min:** `scenarios/prompts/guard_patterns.yaml:9`, `:19`, `:97` — Python re의 문장 분리·그룹별 notice 치환·중복 제거 규약을 따르되, source_line은 여러 줄 답변의 마지막 줄에 적용해야 한다. R1·R2 수정 예문을 guard 검사에 반영한다.

2. **agent-session/assistant:** `scenarios/prompts/README.md:18`, `docs/common/harness.md:7` — 파일명으로 필요한 프롬프트만 골라 조립하고, catalog 전체나 fixture 전체를 system에 붙이지 않는다. 미래 카드·미공개 문서·관찰 레이블이 페르소나에게 새지 않도록 한다. 어시스턴트는 자기 대화와 공개 문서만 본다.

3. **agent-session observe:** `scenarios/prompts/observe_labels.md:22`, `docs/agent/design.md:135` — LLM의 근거 id가 실제 창 안 지원자 활동인지 코드가 검증하고, aux는 레이블과 독립적으로 지표에 병합한다. R3·R4의 합의 없이 현재 문구를 검증 스키마로 확정하지 않는다.

4. **agent-session/오케스트레이터:** `scenarios/prompts/observe_labels.md:102`, `docs/agent/design.md:70`, `:131`, `docs/common/scenario-model.md:62` — 기존 설계 자체에서 report_request가 창을 닫는다는 전이표/시나리오 모델과, 마지막 요소 창을 제출까지 둔다는 observe 절이 충돌한다. 이번 프롬프트는 제출 전 보고의 첫 지적도 포함하는 쪽을 따른다. 구현 전 오케스트레이터가 문서 충돌을 확정해야 하며 prompts 트랙의 신규 소유권 위반으로 보지는 않는다.

5. **report-worker:** `scenarios/catalog.yaml:97`, `:120`, `:167` — 고정된 scenario의 label_texts를 사용하고 변경된 “다른 활동은 있었지만 답하지 않음”, “공개 전 알림”, “유료 멤버십 문제 미언급” 문구와 실제 label/evidence가 맞는지 확인한다. 디브리핑만 연출 설명을 표시하고 페르소나 응답에는 넣지 않는다.

6. **foundation/오케스트레이터:** `services/api/app/services/scenario.py:192`, `scenarios/prompts/README.md:14` — rglob에 따라 픽스처도 scenario 복사본·버전 해시에 포함되는 현재 동작은 계약에 부합하므로 당장 제외할 필요는 없다. 후속 로더가 실행용 파일만 선택하면 된다. 제외 정책 변경은 foundation 담당에게 요청한다.

7. **페르소나·MVP 범위 확인:** `scenarios/prompts/colleague.md:5`, `:81`, `:98`, `scenarios/prompts/manager.md:1` — 카탈로그 values·must·must_not_preempt 5개·in_window_help·identity·must_not 대응은 존재하고 이도현/한서윤의 이름·역할도 일관된다. 허용 정보 제공 예시는 카탈로그와 같아 새로운 선점 정책으로 보지 않는다. 코드·새 서비스·불필요한 전수 테스트 추가는 없다.

## 검증 기록

- YAML 파싱, grounding 10건/preemption 5건 수량, 픽스처 정규식 컴파일 확인.
- 기존 guard hit/miss 예문 전부 통과. 위 추가 재현에서 오탐·미탐 확인.
- 모든 catalog labels의 정의 행 존재 확인. 단 타입·시각·의미 규칙의 문제는 R3·R4와 권장 사항에 명시했다.
- catalog의 brief·debrief·label_texts 제외 구조가 main과 동일함을 확인.
- 읽기 전용 리뷰이므로 lint·전체 테스트·실제 LLM·네트워크 호출은 재실행하지 않았다. 개발자 보고서의 lint/pytest 통과는 보고된 결과이며 이 리뷰에서 독립 재검증한 결과와 구분한다.
