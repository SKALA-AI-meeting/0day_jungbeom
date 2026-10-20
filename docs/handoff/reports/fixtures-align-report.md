# 공용 픽스처 정합화 보고 (P0 마무리, 2026-10-21)

기준: `docs/common/contracts.md` 최종본, `scenario-model.md`(120분·카드 7장), `rubric.md`(항목 id·근거 타입). 이전 에이전트가 만든 작업 트리 변경(수정 5·추가 68)을 검수했고, 어긋난 곳만 고쳤다.

## 파일

- 수정(기존 5): `mcp_ok.json`, `message.json`, `report.json`, `state.json`, `ws_events.json`
- 추가(68): `tests/fixtures/README.md`의 표에 있는 나머지 전부(관리자·지원자·WS·내부 REST·MCP·큐)
- 삭제: 없음(픽스처). 저장소 루트 `REVIEW.md`·`REVIEW-PLAN.md`는 `docs/handoff/reviews/`에 원문이 있어 지움
- `tests/fixtures/README.md`: 새 파일 목록과 id 규칙으로 다시 씀

## 검수에서 고친 곳 (이전 에이전트 결과가 contracts와 어긋남)

| 파일 | 어긋남 | 고친 값 |
|---|---|---|
| `report.json` | `summary[].observed` | `summary[].line` |
| `report.json` | 근거의 `scored: true/false` (옛 구조) | 삭제. 점수 무관 근거(doc_view)는 `flag: "aux_fact"` |
| `report.json` | document·doc_view 근거에 `record_ref` 값이 있음 | `null`(기록 목록에 없는 타입) |
| `report.json` | `ai_usage.calls[] {request, response, cited_docs, applied_parts}` | `ai_usage.events[] {call_id, t_min, request_quote, response_quote, cited_doc_ids, applied_part}`. applied_part는 `internal_assistant_reuse.json`의 applied=true 파트(ac-2 → 2, ac-1 → null) |
| `report.json` | 최상위 `notes` 없음 | `notes: []` |
| `report.json` | collab_disagree 근거 `context.card_at_t_min` 90 ≠ 카드 `card_at_t_min` 90.5 | 카드 값과 같게(전 근거 공통 규칙) |
| `admin_candidates.json` | 중첩 `score {met, unmet, no_record, source, by_element}`, `display_group` 없음 | 평탄화 `met·unmet·no_record·score_source·by_element`(리포트 없으면 null), `display_group`(needs_review·problem·waiting) |
| `admin_record.json` | `{entries: [...]}`, type에 event·document·doc_view, `ref` 없음 | 배열 `[{t_min, type, channel?, by, summary, ref}]`, type은 계약의 7개만(notice 채널 메시지는 `notice`). 동료 보내기(ksh-4-1)·ac-2·sh-2 행 추가로 리포트 `record_ref`가 모두 기록에 있음 |
| `admin_report_notes.json` | `notes[].memo` | `notes[].text` |
| `debrief.json`, `debrief_failed.json` | `final_view_until` 없음, `survey.questions` 없음 | 정상: 종료+7일, 2문항(natural·fair). 실패: `final_view_until: null`, `questions: []` |
| `observation_patch.json` | `{metrics, run_id}` | `{card_id, window_start, metrics_patch, run_id}` |
| `mcp_tools.json` `update_observation` | 입력에 `window_start` 없음, `metrics` | `window_start`, `metrics_patch` |
| `internal_division_put.json`, `mcp_tools.json` `set_division` | 요청 decided_by=colleague_default인데 응답은 candidate | 요청을 candidate(채팅으로 정한 분업을 동료 set_division이 채움)로 맞춤, run_id r-11 |

이전 에이전트 판단 중 유지한 것: classification.kind는 `docs/agent/design.md`(question∣instruction∣redivide∣progress_query∣doc_feedback∣report∣other), 카드 이름은 임의, 관찰 없는 창은 `no_evidence` 라벨, `mcp_tools.json`의 출력은 같은 폴더 파일 참조, collab_disagree `card_at_t_min` 90.5(같은 이벤트의 첫 메시지 시각), 흐름 카드의 `events[].element`는 null.

## contracts.md에서 발견한 어긋남 (수정하지 않음, 오케스트레이터 판단 필요)

1. Report 예시 `summary[1]`에 `"judged":0`이 있다. 같은 문단과 워커 산출 표는 `{element, name, line, met, unmet, no_record}`라 오타로 보인다. 픽스처는 `unmet`을 쓴다.
2. Report 예시의 `rubric...evidence[]`는 `{type, id, t_min, record_ref}`만 있고 섹션 근거는 `context` 등을 더 가진다. 픽스처는 두 곳 모두 섹션 근거와 같은 전체 형태를 쓴다(필드 추가라 계약 위반은 아님).
3. State 예시는 `division`이 확정인데 `tasks[1].assignee`가 null이다. 픽스처 `state.json`(47.5분)은 확정 뒤라 5행이 모두 차 있다. "assignee null 시작"은 `internal_task_events.json`의 assignee `old_value: null`로 드러난다. 시작 직후 State 픽스처가 필요하면 scenario-redesign이 추가한다.
4. `GET /admin/positions`의 `candidate_count`가 세션 수인지 사람 수인지 정해져 있지 않다. 픽스처는 2(사람 2명, 세션 3개)다.

## 이 픽스처를 쓰는 기존 테스트

`grep -rn "fixtures/contracts" services apps tests` 결과와 실행 결과(`make test`의 서비스별 pytest, 2026-10-21):

| 파일 | 쓰는 픽스처 | 결과 |
|---|---|---|
| `services/api/tests/test_candidate.py` (`test_candidate_endpoints`) | `state.json` (STATE_FIXTURE 키·persona) | **실패**: 코드가 옛 State 키를 낸다(옛 4요소·공유 문서) |
| `services/business-mcp/tests/test_tools.py` | `mcp_ok.json` | 통과 |
| `tests/conftest.py` (`load_contract`) | 전체 | 사용하는 테스트 없음 |
| `apps/web` | 자체 `apps/web/mocks/fixtures/` (이 폴더를 읽지 않음) | 영향 없음 |

깨지는 테스트 1개(api 1 failed, 81 passed). 테스트 코드는 고치지 않았다(scenario-redesign 몫). 다른 서비스: business-mcp 11, rag-mcp 10, report-worker 17 통과.

## lint

`uv run ruff check .`·`ruff format --check .`·web `eslint .` 통과. `make lint`의 web `prettier --check .`은 git이 무시하는 로컬 폴더 `apps/web/.agents/skills/`(2026-10-20 설치된 스킬 문서 23개)에서 실패한다. 추적 파일만 보면(`--ignore-path .gitignore` 추가) 통과한다. 이번 변경과 무관하며 해당 폴더는 지우지 않았다. `apps/web/.prettierignore`에 `.agents`를 넣을지는 사용자 결정.
