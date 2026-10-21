# rw-consistency 보고서 (report-worker, Opus)

playtest(관리자 페르소나, 실 LLM) 심각도 상 2건·중 1건 수정. 브랜치 `track/rw-consistency`(track/debate 기준).

## 바꾼 것

1. **요소 summary와 최종 차원 상태 일치** (`services/report-worker/report_worker/evaluate.py`)
   - 검증으로 차원 행이 모델 출력과 달라진 요소(evaluate_failed, 근거 1개 수준 4·5 → 3, 아래 2번 event_not_fired 변환)만 `rewrite_summary`가 summary를 1회 다시 쓴다. 같은 LLM(`MODEL_EVALUATOR`, 같은 temperature), system은 평가 공통 프롬프트, user는 `[요소]`·`[요약 재작성]`·`[최종 차원]`(이 요소의 차원별 id·이름·수준·기록 없음 표시 문장·rationale)뿐이다. 세션 기록과 다른 요소 결과는 넣지 않는다(후광 방지).
   - 출력 `{"summary": ...}`가 파싱 실패·빈 값·금지어면 다시 요청하지 않고 고정 문장 `REWRITE_FALLBACK`("일부 차원 판단이 검증 단계에서 바뀌어 요약을 다시 쓰지 못했습니다. 차원별 판단을 확인해 주세요.")을 쓴다. 전송 오류·타임아웃은 다른 평가 호출과 같이 잡지 않는다(저장 없이 큐 재시도).
   - 확신도 clamp만 일어난 요소, 차원이 바뀌지 않은 요소는 추가 호출이 없다. 모든 차원이 evaluate_failed면 지금처럼 `FAILED_SUMMARY`(호출 없음). 차원이 안 바뀌었는데 모델 summary만 무효인 경우도 지금처럼 `FAILED_SUMMARY`.
   - 재작성 호출은 `usage.llm_calls`에 든다(`element_retries`에는 들지 않음). 새 usage 키는 만들지 않았다.
   - 멱등: 재작성된 summary도 save_evaluation 본문에 들어가므로 재실행은 저장된 평가를 그대로 쓴다(LLM 재호출 없음).
2. **핵심 카드 미발생 → event_not_fired 결정적 변환** (`evaluate.py` `not_fired`)
   - 차원의 `core_cards`가 하나도 `observations`에 없고 수준이 있으며 `rationale`에 "보조 장면"이 없으면 거부(재요청)하지 않고 `level: null`, `no_record_reason: event_not_fired`, `confidence: null`, rationale 끝에 `NOT_FIRED_MARK`(" (핵심 카드 미발생·보조 장면 표시 없음으로 이벤트 미발생 처리)")를 붙인다. `evidence_refs`는 고쳐 쓰지 않고 그대로 둔다.
   - "보조 장면" 표시가 있으면 지금처럼 확신도 low 상한만 적용한다.
3. **프롬프트** (`scenarios/missions/debate/prompts/evaluator/common.md`, 카탈로그 해시 `common` 변경)
   - 역할과 원칙: "`summary`·`rationale`은 관찰된 행동을 서술한다. 미흡·부족·우수·낮은/높은 수준 같은 판정 형용사는 쓰지 않는다(수준은 숫자 칸이 보여 준다)." 금지어 목록(`guard_patterns.yaml`)에는 넣지 않았다.
   - 확신도: "핵심 장면이 없으면(핵심 카드 미발생) 일어나지 않은 행동의 부재로 낮은 수준을 주지 말고, 보조 장면에서 실제로 관찰된 행동이 있을 때만 `rationale`에 "보조 장면"을 표시해 판단한다. 그 표시 없이 수준을 내면 워커가 `event_not_fired`로 바꾼다."
   - 새 절 "요약 재작성": 재작성 호출의 입력·출력 형식과 규칙(1~2줄, 최종 차원 행과 어긋나지 않음, 수준 없는 차원은 기록 없음·판단 보류라고 밝힘, 차원 행에 없는 판단·다른 요소 언급 금지, 어조·금지 표현 규칙 유지). 별도 프롬프트 파일을 만들지 않은 이유: `prompt_versions` 키가 계약(`{common, 5요소}`)으로 고정이라 새 파일 해시를 남길 자리가 없다. 공통 프롬프트 안에 두면 해시에 포함된다.
4. `FakeEvaluatorLLM`(`LLM_FAKE=1`)이 `[요약 재작성]` 호출에 고정 summary를 낸다. 결정적 모드에서 카드가 발동하지 않은 차원은 이제 수준 3이 아니라 event_not_fired가 된다(고정 rationale에 "보조 장면"이 없으므로). `all_five`는 카드가 모두 발동해 영향 없음.

## 테스트

- `test_summary_rewritten_once_only_for_changed_element`: 차원이 바뀐 요소만 재작성 1회, 입력에 세션 기록·다른 요소 요약 없음·사유는 표시 문장, 바뀌지 않은 요소는 0회.
- `test_summary_rewrite_failure_uses_fixed_sentence`(파싱 실패·빈 값·금지어): 1회만 호출하고 고정 문장.
- `test_core_card_not_fired_without_support_mark_becomes_event_not_fired`: 재요청 없이 변환, rationale 끝 표시.
- `test_core_card_not_fired_caps_low_and_one_persuasion_card_caps_medium`(갱신): "보조 장면" 표시가 있으면 수준 유지·low.
- `test_rerun_reuses_saved_rewritten_summary_without_llm`(test_graph): 저장 직후 장애 → 재실행 시 LLM 재호출 없음, 저장된 재작성 summary 그대로.
- 기존 테스트 중 evaluate_failed·수준 상한 경로의 호출 수 기대를 +1(요약 재작성)로 고쳤다.
- `make test`·`make lint` 통과(report-worker 42 passed).

## 문서 반영 필요(오케스트레이터)

- `docs/common/rubric.md` 2.4 상한 목록 "핵심 카드가 미발생해 보조 장면만으로 판단하면 최대 `low`" 뒤: "`rationale`에 "보조 장면" 표시 없이 수준을 내면 워커가 거부하지 않고 `event_not_fired`(confidence null)로 바꾸고 rationale 끝에 변환을 표시한다."
- `docs/common/rubric.md` 7.3 워커 검증에 항목 추가: 위 event_not_fired 변환, 그리고 "검증으로 차원 행(evaluate_failed·수준 상한 3·event_not_fired)이 바뀐 요소는 최종 차원 행만 입력으로 summary를 1회 다시 쓰고, 실패(형식·금지어)하면 고정 문장으로 둔다. 확신도 clamp만 있으면 다시 쓰지 않는다." 마지막 항목의 "수준은 위 두 상한으로만 깎는다"는 event_not_fired 변환을 함께 적도록 고친다.
- `docs/common/rubric.md` 7.2 `summary` 행: "워커 검증으로 차원이 바뀌면 최종 차원 행으로 다시 쓴 서술(또는 고정 문장)". 서술 어조(판정 형용사 금지)도 7.1 `rationale`·7.2 `summary`에 한 줄.
- `docs/common/contracts.md` 검증 경계·EvaluationSave 설명에 같은 두 규칙(형식 변경 없음). reports.usage `llm_calls`에 요약 재작성 호출이 든다는 점.
- `docs/worker-infra/design.md` evaluate 단계: 요소별 호출 5회 + 차원이 바뀐 요소마다 요약 재작성 최대 1회.

## 리뷰 수정 (Codex 차단 1건)

- `FakeEvaluatorLLM`이 user 전체에서 `[요약 재작성]`을 찾아, 지원자 메시지에 그 문자열이 있으면 요소 평가 호출을 재작성 호출로 오인했다(19차원 전부 evaluate_failed). 이제 user의 두 번째 블록(`[요소] x` 다음 블록) 머리말만 본다. 요소 평가는 `[요소 척도]`, 재작성은 `[요약 재작성]`로 시작하고 세션 기록은 그 뒤 블록이라 섞이지 않는다.
- 실제 LLM 경로(`OpenAILLM`, `evaluate.py`)에는 문자열로 호출 종류를 가리는 곳이 없다.
- 재현 테스트 `test_llm_fake_not_confused_by_rewrite_header_in_candidate_message`: 수정 전 실패, 수정 후 통과.
