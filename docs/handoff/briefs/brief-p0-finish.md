# 브리프: P0 마무리 (Claude Opus 인수, 2026-10-21)

역할: 오케스트레이터 인수. 저장소 `/Users/zaehorang/Projects/Day-0_zaeho`, 브랜치 `track/redesign-docs`(main보다 앞서 있음, 커밋 d5e1c7a까지). 이 브리프의 일을 끝내고 멈춘다. P1 개발은 사용자가 시작하라고 할 때 `docs/handoff.md`의 "P1 기동 절차"대로 띄운다.

## 상태
- 문서(PRD·docs/*)는 전부 커밋됐다. `docs/common/contracts.md`가 이름 정본이며 더 바꾸지 않는다.
- **작업 트리에 미커밋 변경**: `tests/fixtures/contracts/` 아래 수정 5개·추가 68개(총 73개). 이전 에이전트가 contracts.md 기준으로 정합화를 **끝냈고** JSON 파싱은 통과했으나 커밋하지 않았다. 그 에이전트의 판단: classification.kind 값은 agent/design.md 기준, 카드 이름은 임의, no_evidence 라벨, mcp_tools.json 참조, collab_disagree card_at_t_min 90.5, 흐름 카드의 events[].element는 null. 손대지 않은 것: `tests/fixtures/README.md`(갱신 필요), `apps/web/mocks/fixtures/*`. 깨지는 것으로 보고된 테스트: `services/api/tests/test_candidate.py`(STATE_FIXTURE 키·persona, 옛 4요소). 이 브리프의 이름이 바뀌었다(brief-p0-finish-codex.md → brief-p0-finish.md): 핸드오프의 참조도 같이 고친다. 저장소 루트의 `REVIEW.md`·`REVIEW-PLAN.md`는 리뷰 원문 사본(이미 `docs/handoff/reviews/review-redesign.md`·`review-plan.md`에 보관)이라 지운다.

## 할 일
1. `tests/fixtures/contracts/`를 `docs/common/contracts.md` 최종본과 **검수**한다(재작성 아님, 어긋난 곳만 고친다). `tests/fixtures/README.md`를 새 파일 목록에 맞게 갱신한다. 기준: 관리자 API 응답, Report JSON(summary 세 수 met·unmet·no_record, items[].basis, evidence[].record_ref·flag, ai_usage.events[], notes[], review.reviewer_name), 지원자 state·my-documents·final·tasks(assignee null 시작, both), WS 프레임(document.shared, division.confirmed, session.reporting {deadline_at}, session.ended), 내부 API(docs/shared, docs/send with event_id·seq, document_revisions, observations PATCH, honesty_facts, task_events, board), MCP 도구 입출력(send_document, get_shared_documents, update_observation), debrief(final_view_until, survey.questions)·debrief/survey, record 배열. 값은 `docs/common/scenario-model.md`의 120분·5요소(카드 7장: planning_division 10, collab_help 30, planning_checkin 45, responsibility_delay 60(공개 70), adaptability_change 75, collab_disagree 90, honesty_report 110)와 `rubric.md` 항목 id를 쓴다. 옛 구조(요소 4개·respect·document_states·history·category·ratio·section_no·scored·calls)는 남기지 않는다.
2. `python3 -I -c 'import json,glob; [json.load(open(f)) for f in glob.glob("tests/fixtures/contracts/**/*.json", recursive=True)]'` 통과.
3. `docs/handoff/reports/fixtures-align-report.md` 작성: 만든·바꾼·지운 파일, contracts와 어긋나 판단한 곳, 이 픽스처를 쓰는 기존 테스트 중 깨지는 파일 목록(`grep -rn "fixtures/contracts" services apps tests`). 테스트 코드는 고치지 않는다(scenario-redesign 몫).
4. 커밋(한국어 한 문장, 의도 중심) → `git checkout main && git merge --squash track/redesign-docs` → 커밋 메시지 "인성 5요소·문서 주고받기 재설계를 기획·설계·계획 문서와 공용 픽스처에 반영하고 개발 전 리뷰 4종을 반영함" → `git branch -D track/redesign-docs`. 문서·픽스처만 바뀌었으므로 `make test`는 기존 테스트가 픽스처 변경으로 깨질 수 있다. **깨지는 것이 픽스처 때문이면 병합을 막지 않고** 보고서의 목록과 일치하는지만 확인한다. `make lint`는 통과해야 한다.
5. `docs/handoff.md` "현재 상태"의 "(병합 후 기입)"에 병합 커밋 해시를 적고, 같은 절의 "Codex가 인수" 문단과 진행 표 P0 행을 "Claude Opus가 마무리·병합 완료"로 고친 뒤 main에 커밋한다. push는 사용자에게 묻는다.
6. 멈춘다. 마지막 응답은 병합 커밋 해시와 깨지는 테스트 수 한 줄.

## 규칙
- AGENTS.md, `docs/dev-process.md`, `docs/handoff.md`의 Herdr 운영 규칙·체크리스트를 따른다. 키 값은 어디에도 출력하지 않는다. `docs/common/*`은 수정하지 않는다(어긋남을 발견하면 보고서에 적는다).
