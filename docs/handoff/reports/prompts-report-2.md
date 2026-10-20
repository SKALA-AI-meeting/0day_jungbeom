# prompts 수정 라운드 보고 (Codex 리뷰 반영)

브랜치 `track/prompts`, 커밋 `d830f71`(이전 `c068e3c` 위). main 병합·push 없음. worktree의 `REVIEW.md`는 삭제(추적되지 않던 파일).

## 수정 목록

### 반드시
- **R1·R2 `guard_patterns.yaml`**
  - `verdict`: 사람·평가 운영 문맥이 있어야 걸리도록 좁혔다. 합격·순위·다른 지원자, "리드님/지원자/님 … 좋은·나쁜 평가", "좋은 평가를 받으실", "(이번·오늘·세션·역량·지원자…) 평가 기준·항목·결과·방식", 평가표·채점표, 평가·관찰 + 요소 이름(협력 태도·책임감·유연성·존중·소통), "리드님/지원자 … 관찰·기록되", "이 대화 … 관찰되". 맥락 없는 `(점수)…`, `평가 기준/결과`, `기록하고`는 뺐다.
  - 새 그룹 `score`: `\d+점`, `점수:`, 사람·응답 문맥 + 점수/감점, 점수 + 받·깎·올라…, 감점·가산점. `unless`(만족도·NPS·평점·별점·척도·지표·참여율·전환율·리텐션)에 걸린 문장은 이 그룹을 건너뛰어 업무 지표의 점수·비율을 보존한다. `unless` 규칙은 파일 머리말에 적었다.
  - `staging`: `테스트하려고` 같은 일반 패턴을 "리드님/지원자를 테스트", "이건 … 테스트예요"로 좁혔다.
  - miss 예문 추가: 리뷰의 업무 문장 4개(만족도 점수 지표, 가설 평가 기준, 회의록 기록, 가설 테스트) + "첫 참여자 행동을 관찰하고 인터뷰한 결과예요", "만족도 평균이 4.2점이에요", "재참여율은 34%예요", "4번 파트는 10분 뒤에 올릴게요". hit 예문 추가: "현재 4점입니다.", "이번 응답은 80점이에요.", "점수: 4/4입니다.", "이번 평가 결과는 나중에 나와요.", "리드님 행동은 다 기록되고 있어요.", "이건 테스트예요."
  - 머리말에 `assistant_source_line`은 여러 줄 답변의 마지막 줄에 적용한다고 적었다.
- **R3 `observe_labels.md`**: `silent`·`apply_silently`의 evidence는 revision만. 창 안에 지원자 revision이 없으면 silent로 분류하지 않고 `label: null`. assistant_call 예시 삭제(대신 "어시스턴트에게만 묻고 2번 파트를 수정함, evidence: 그 revision").
- **R4 observe 입력 계약**: 책임감 `[카드]`에 코드가 계산한 `release_at`(실제 공개 시각, 분, 카드 시각과 같은 기준)과 `released_before_message`(지원자 메시지 id → 공개 전 true)를 추가. "알림 본문의 약 15분으로 추정하지 않는다"를 `observe_labels.md` 1절과 `README.md` 조립 표에 명시. observe 전용이고 페르소나 블록에는 넣지 않는다고 적었다.

### 같이
- **권장 1 `common_rules.md` 6절**: 목록 기호 제한은 동료·팀장에만. 어시스턴트는 사용자가 요청한 형식을 따른다.
- **권장 2**: 책임감 레이블은 공개 전후와 무관하게 알린 내용으로 고른다. `notify_only` = 지연 사실만 알리고 대안 없음. 공개 전 여부는 지표 `notified_before_release`(항목 `resp_notified_before_release`, rubric.md 지표 표 확인)가 센다. label_texts 확인 결과 `notify_with_alternative`에 지난 라운드에 내가 넣은 "자료가 공개되기 전에"가 같은 시간 조건을 중복해서, 시간 조건 없이 "지연을 팀이나 동료에게 알리고 대안을 제시함"으로 고쳤다(문구만, decisions에 기록). `notify_only`는 그대로.
- **권장 3 `preemption.yaml`**: 머리말에 "정규식은 보조 검사, 의미 조건은 colleague_should·must_not 문장으로 확인, mock에서는 조립 확인용"을 적었다. 지적된 두 정규식만 수정: `delay_alternative.must_not_regex[0]`에 "그동안 … 채우죠/잡죠/쓰죠/하죠" 포함, `ghostwrite_candidate_part.should_regex`에 "대신 쓰기는 어려워요"·"… 중심으로 묶어" 포함.
- **담당 지정 `fixtures/context_leak.yaml`** 추가: 미래 상황 유도 3건(future_next_event 동료, future_target_change 팀장, future_review_content 동료), 역할 사칭 2건(impersonate_manager 동료, impersonate_operator 어시스턴트). 각 건 지원자 발화, 기대 응답 요지, 금지 패턴, setup(fired·pending 카드). README 표에 행 추가.
- **주의사항 4(문서 충돌)**: `docs/agent/design.md` 전이표의 report_request 행을 "흐름 카드라 열린 창을 닫지 않는다(마지막 요소 창은 제출·세션 종료까지)"로, `docs/common/scenario-model.md` 관찰 창 문장을 "다음 요소 카드까지, 흐름 카드·texture는 닫지 않음, 마지막 요소 창은 submitted_at 또는 ends_at까지"로 고쳤다. observe 절(design.md 131행)은 이미 그 결정과 같아 손대지 않았다.
- **`docs/decisions.md`** 맨 아래 "2026-10-20 prompts 리뷰 반영" 절: silent 근거, release 입력, 창 종료, 책임감 레이블 시간 무관(notify_only), guard 범위·context_leak 담당.

## 검증 명령과 결과

| 검사 | 명령 | 결과 |
|---|---|---|
| catalog 파싱 | `uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('scenarios/catalog.yaml'))"` | parsed |
| catalog 구조 불변 | `git show main:scenarios/catalog.yaml`과 brief·debrief·label_texts 값을 뺀 객체 비교(스크래치 `cmp_catalog.py`) | `structure_equal True` |
| guard 예문 | 스크래치 `check_guard.py`: hit은 자기 그룹(unless 반영)에 걸림, miss와 안내문 3개는 어느 그룹에도 안 걸림 | `checked 47, bad 0` |
| guard vs 프롬프트 예시 문장 | colleague·manager·assistant.md의 큰따옴표 예시 문장 전부 검사 | 걸린 것은 manager.md의 금지 예시 "잘하셨어요, 합격이에요" 1건뿐(의도대로) |
| 리뷰 지적 정규식 | "그동안 지표로 2번을 채우죠" → delay must_not / "대신 쓰기는 어려워요. … 중심으로 묶어 보세요" → ghostwrite should, must_not | True / True, False. 정상 응답("… 리드님이 정해 주시면 따를게요")은 must_not 미매칭 |
| 픽스처 | 3개 파일 파싱·정규식 컴파일, context_leak 종류 수, 금지 패턴이 안내문에 걸리지 않는지 | context_leak 5, grounding 10, preemption 5, regex ok, future 3·role_impersonation 2, 안내문 충돌 없음 |
| lint | `make lint` | exit 0 (ruff All checks passed, 45 files formatted, eslint·prettier 통과) |
| 카탈로그 소비 | `cd services/api && uv run pytest -q tests/test_scenario.py` | 1 passed |

## 남은 문제
- guard는 예문 기준 검증이다. `score`의 `unless`는 업무 지표 단어가 같은 문장에 있으면 점수 발언도 통과시키는 트레이드오프가 있다("지표 보니까 리드님은 4점이에요" 같은 혼합 문장). 사람 판정 쪽 `verdict` 패턴은 unless 없이 따로 걸린다.
- 픽스처 정규식은 보조 검사이며 실제 모델 행동은 live에서 확인해야 한다.

## 변경 요청
- 없음. 소유권 밖 수정은 브리프가 허용한 `docs/agent/design.md`(전이표 1행)·`docs/common/scenario-model.md`(1문장)·`docs/decisions.md`(절 추가)뿐이다.

## 다른 트랙에 알릴 것
- **agent-session (observe)**: 책임감 `[카드]`에 `release_at`(분, 공개 안 됐으면 null)과 `released_before_message`({message_id: bool})를 코드가 계산해 넣는다. LLM이 알림 본문으로 공개 시각을 추정하지 않게 하는 계약이다. 이 값은 페르소나 컨텍스트에 넣지 않는다. LLM이 `silent`·`apply_silently`에 revision이 아닌 근거를 내면 코드가 unclassified로 강등한다. 책임감 레이블에는 시간 조건이 없고 공개 전 여부는 `notified_before_release`가 센다. report_request는 창을 닫지 않는다(마지막 요소 창은 submitted_at/ends_at까지).
- **agent-session / agent-assistant (테스트)**: `fixtures/context_leak.yaml` 5건이 harness.md Context 행의 미래 유도·역할 사칭 픽스처다. 컨텍스트 조립 검사(미래 카드 brief·레이블·미공개 문서가 입력에 없음)와 응답 금지 패턴 검사에 쓴다.
- **agent-min (guard)**: 그룹에 `unless`가 생겼다(문장이 unless에 걸리면 그 그룹 건너뜀). 새 그룹 `score`(replacement `evaluation`). 예문 47건을 단위 테스트 픽스처로 쓰면 된다.
- **report-worker**: `notify_with_alternative`의 label_text가 "지연을 팀이나 동료에게 알리고 대안을 제시함"으로 바뀌었다.
