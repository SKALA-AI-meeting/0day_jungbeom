# S4.5 api-blank 보고

브랜치 `track/api-blank`(기준 116fd0d). 제출 때 빈 칸과 빈칸 경고 확인 여부를 저장하고 사실 지표·기록 요약에 노출한다.

## 변경

- `infra/db/schema.sql`·`Proposal` 모델: `submit_blank_sections text[]`, `blank_warning_shown boolean`(둘 다 null 허용). 기존 DB는 재생성.
- `POST /sessions/{id}/proposal/submit` 본문 `{blank_warning_shown?: bool}`(본문 없음도 허용). `session.submit`이 제출본에서 공백뿐인 칸 id를 템플릿 순서로 계산해 저장하고, 자동 제출이면 `blank_warning_shown`은 null. 빈 칸이 있어도 제출은 막지 않는다. `session.submit`·`proposal.submit`에 `template` 인자를 더해 호출부 3곳(라우터, 스케줄러, 테스트 세션)을 맞췄다.
- 내부 facts: `blank_sections_at_submit`(list, 미제출이면 []), `blank_warning_acknowledged`(bool∣null).
- 관리자 record `proposal_submit` summary: `제출` / `제출 · 빈 칸 N개(경고 확인 후 제출)` / 경고 없이 빈 칸이면 `제출 · 빈 칸 N개` / 자동 제출이면 `자동 제출`(빈 칸 있으면 ` · 빈 칸 N개`). 기존 "기획안 제출" 문구는 "제출"로 바뀌었다.
- 계약: `tests/contract_shape.py` FACTS에 두 키, 픽스처 `internal_facts`·`report`·`session_record`(facts에 `[]`/`false`)와 `admin_record`(summary "제출") — `tests/fixtures/contracts/`와 `apps/web/mocks/fixtures/` 사본 바이트 동일.
- 평가 프롬프트 `scenarios/missions/debate/prompts/evaluator/common.md` 편향 방지에 한 줄: 빈 칸 지표는 맥락 참고, 단독으로 수준을 정하지 않고 안의 질 판단에 쓰지 않는다(공통 프롬프트 해시가 바뀐다).

## 확인만 한 것

- 평가 에이전트 입력: assessment-mcp `get_session_record`가 `/facts`를 그대로 `facts`로 넣고, report-worker `evaluate`가 세션 기록 전체를 `[세션 기록]`에 넣으므로 새 facts가 자동 전달된다. 코드 수정 없음.
- 리포트 facts: report-worker가 api facts를 그대로 `report.facts`에 담으므로 데이터는 자동 노출된다. 단 화면 `apps/web/components/admin/report-view.tsx`의 사실 지표 표는 키를 하나씩 골라 행을 만들므로 새 두 지표는 **화면에 표시되지 않는다**. web 트랙 소관이라 손대지 않았다(필요하면 "제출 때 빈 칸"·"빈칸 경고 확인 후 제출" 행 추가).

## 테스트

`services/api/tests/test_c06_submit.py`: 빈 칸 계산·저장(공백뿐 칸 포함, 경고 true), 자동 제출(빈 칸 계산, 경고 null), facts 두 키, record summary "제출 · 빈 칸 2개(경고 확인 후 제출)". `make test`(api 154 passed 등 전부 통과)·`make lint` 통과.

## 추가 범위(main 7287f90 계약 반영)

main을 브랜치에 merge했다. main의 9cd7b9b가 track/debate(116fd0d)와 트리가 같은 squash라 add/add 충돌이 나서 `-X ours`로 합쳤다. 합친 뒤 `git diff 7287f90 HEAD`가 이 트랙 첫 커밋의 diff와 바이트 단위로 같은 것을 확인했다(main 문서 변경은 그대로 들어왔다).

- 칸 표시용 `outcome`: `common.slot_outcome`이 확정 값에서 계산하고, 열로 저장하지 않는다. timeout이면 `timeout`. AI 채우기(`filled_by` ≠ candidate)는 `consensus`. 지원자 확정은 `support` 스냅샷에서 확정 안의 지지자가 3명 이상이면 `consensus`, 아니면 `candidate_decision`(option_id null이면 항상 `candidate_decision`). `slot_public`을 거쳐 `/state` slots·확정 응답 slot·내부 `/slots`·fill 응답에, `slot_event`를 거쳐 WS `slot.confirmed`에 들어간다. 확정 전 칸은 null이다. `/state`에는 `support`를 계속 내리지 않는다.
- 리포트 slots: report-worker `report.py`가 세션 기록 slots의 `outcome`을 그대로 옮긴다(최소 수정 1줄). assessment-mcp는 내부 `/slots`를 그대로 넘기므로 SessionRecord slots에도 `outcome`이 생긴다(코드 수정 없음). 평가 입력에도 보이게 되는데, 이미 받는 `support`에서 계산한 값이라 정보가 새로 늘지는 않는다.
- 제출 저장값은 첫 커밋 구현이 이미 새 규칙과 맞았다. 수동·자동 모두 빈 칸 목록을 계산하고(없으면 `[]`), 수동 제출에서 생략하면 false, 자동 제출이면 null, 제출 전에는 둘 다 null, 멱등 재호출로 바뀌지 않는다. 이 동작을 고정하는 테스트를 더했다.
- 계약 형태: `OUTCOME` enum을 SLOT_PUBLIC·SLOT_FULL(SessionRecord slots 포함)·`slot.confirmed`·리포트 slots에 더했다. confirmed 칸은 outcome이 필수다. 픽스처 11개에 넣은 값은 픽스처 자신의 support로 계산했다. 키워드는 지지자가 candidate·p2 두 명이라 `candidate_decision`이고, 그래서 contracts.md 예시의 키워드 `"outcome":"consensus"`(지지자 3명 예시)와 다르다. web 사본도 바이트 동일하게 맞췄다.
- 평가 프롬프트 줄을 main rubric의 새 문구(성실성·품질 대리 지표 금지, `idea_credit` 공란만 `hon_credit_record`, 경고값은 근거 단위 아님)에 맞춰 다시 썼다.

추가 테스트: 확정 전 outcome null과 지원자 혼자 확정 → `candidate_decision`(확정 응답·WS·내부 slots·state, state에 support 없음), 지지자 3명 확정 → `consensus`, fill → `consensus`, timeout → `timeout`, 수동 제출 생략 → `[]`/false에 제출 전 null·재호출 불변. `make test`(api 156 passed)·`make lint` 통과.

## 기록 요약 outcome

- 관리자 record의 칸 확정 줄 끝 토큰을 resolution 대신 outcome(`consensus`∣`candidate_decision`∣`timeout`)으로 바꿨다(`reports.record`가 `slot_outcome`을 쓴다). admin_record 픽스처 두 사본의 키워드 줄은 지지자 2명이라 `(candidate_decision)`으로 맞췄고, 두 사본은 바이트 동일하다.
- 테스트: `test_c01` 지원자 혼자 확정 → "keyword: 물 (candidate_decision)". api 156 passed, `make lint` 통과.
- 단독 make test에서 web report-view 1건 실패, web-ux 병합 뒤 해소: `apps/web/components/admin/format.ts`의 정규식이 아직 `consensus|timeout`만 받는다. track/web-ux 25a9f22가 세 토큰을 처리하므로 통합 때 web-ux를 먼저 병합하면 맞는다. 이 트랙은 web 파일을 건드리지 않았다.

## Codex 리뷰 반영(main b51db8c merge 뒤)

- 차단: 제출 줄 요약을 계약대로 항상 쓴다. 수동 true는 "제출 · 빈 칸 N개(경고 확인 후 제출)", 수동 false는 "제출 · 빈 칸 N개(경고 없이 제출)", 자동은 "자동 제출 · 빈 칸 N개"이고 N=0이어도 쓴다. 앞 절에 적은 "제출"·"자동 제출" 단독 형식은 이것으로 대체됐다. admin_record 픽스처 두 사본은 "제출 · 빈 칸 0개(경고 없이 제출)"이고 바이트 동일하다.
- 권장1(test_c01): 확정 안 지지자 2명, 다른 안에만 3명, option_id null은 모두 `candidate_decision`. 확정 응답과 WS `slot.confirmed`에 `support` 키가 없음을 단언한다.
- 권장2(test_c06): 빈 칸 없는 자동 제출은 `[]`/null이고, 그 뒤 수동 submit(true)을 재호출해도 바뀌지 않는다. 요약은 "자동 제출 · 빈 칸 0개". 기존 자동·수동 테스트에도 요약 단언을 더했다.
- web: 이 요약 문구를 가정하는 web 코드·테스트는 없다(record-view는 type 라벨만 쓴다). 단독 make test의 web 실패는 여전히 report-view 1건(키워드 outcome)뿐이고 web-ux 병합 뒤 해소된다.
- api 158 passed, `make lint` 통과.
