# prompts 수정 라운드 (Codex 리뷰 반영)
리뷰 전문: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/review-prompts.md. 아래는 오케스트레이터 결정. 같은 브랜치에 커밋. 끝나면 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/prompts-report-2.md 에 수정 목록·검증 명령·결과를 저장(worktree의 REVIEW.md는 지운다). 마지막 응답은 경로 한 줄.

## 반드시
- R1·R2 guard_patterns.yaml: 판정 패턴을 "지원자/리드/응답에 대한 평가"나 "현재 평가 운영"을 드러내는 문맥으로 좁힌다. 리뷰의 업무 문장 4개(만족도 점수 지표, 가설 평가 기준, 회의록 기록, 가설 테스트)는 miss 예문으로 추가. 숫자 점수("4점입니다", "80점이에요", "점수: 4/4")는 hit 예문으로 추가하고 패턴에 포함. 업무 지표의 점수·비율은 보존. 검증 스크립트로 hit/miss 전부 재확인.
- R3 observe_labels.md: 설계 계약 유지. `silent`의 evidence는 revision만. 창 안에 revision이 없으면 silent로 분류할 수 없고 `label: null`(unclassified). assistant_call 예시는 삭제.
- R4 observe 입력 계약: `[카드]` 블록에 코드가 계산해 넣는 사실을 추가한다: `release_at`(실제 공개 시각, 분), `released_before_message`(각 지원자 메시지마다 공개 전/후 bool). observe_labels.md와 README.md의 입력 정의에 반영하고 "알림 본문의 15분으로 추정하지 않는다"고 명시. agent-session에 알릴 것에 추가.

## 같이
- 권장 1: common_rules.md의 목록 기호 제한은 메신저 페르소나(동료·팀장)에만 적용, 어시스턴트는 사용자가 요청한 형식을 따른다.
- 권장 2: `notify_only`는 "지연 사실만 알리고 대안 없음"(공개 전후 무관)으로 유지. 공개 전 여부는 metric `resp_notified_before_release`가 센다(rubric.md 확인). observe_labels.md 책임감 절을 그에 맞게 수정. label_texts는 의미와 맞는지 확인만.
- 권장 3: preemption.yaml 머리말에 "정규식은 보조 검사이며 의미 조건은 기대 행동 문장으로 확인"을 명시하고, 지적된 두 정규식만 고친다.
- 담당 지정: `fixtures/context_leak.yaml` 추가 — 미래 상황 유도 질문 3건, 역할 사칭 질문 2건(지원자 발화 + 기대 응답 요지 + 금지 패턴). harness.md Context 행의 픽스처 담당은 prompts.
- 주의사항 4(문서 충돌): 오케스트레이터 결정 = 마지막 요소 창은 제출(세션 종료)까지. 이번만 `docs/agent/design.md` 전이표·observe 절과 `docs/common/scenario-model.md`의 해당 문장을 그 결정으로 맞춰 고친다(두 문서 외 수정 금지). `docs/decisions.md` 맨 아래에 "2026-10-20 prompts 리뷰 반영" 절로 R3·R4·창 종료·notify_only 결정을 적는다.

## 하지 않을 것
카탈로그 구조·조건 변경, 코드 작성.
