# 재설계 문서 점검 결과 (2026-10-20, 탐색 에이전트)

`docs/prd-change-proposals.md`의 "인성 5요소·미션 단위 재설계" 절과 어긋나는 기존 문서 위치. 반영 트랙이 이 목록을 체크리스트로 쓴다. **점검 뒤에 협업 모델이 "문서 주고받기"로 바뀌었다**(`docs/frontend/design-direction.md`). 아래에서 "전체 편집·낙관적 잠금·섹션 작성자"라고 쓴 항목은 모두 "문서 주고받기·버전·최종본"으로 읽는다. 호칭 "리드"는 "주담당"으로 바꾼다.

## PRD.md
- 12, 14: 핵심 가치의 "실수" 연출 예 → 도움 요청·반대 의견·지연·방향 변경·보고 압박. 1장에 초점 문장("같이 일하기 좋은 사람인가") 추가.
- 85~86: 5.1 동료 "실수 연출" 삭제, 반대 의견·초안 공유 추가. 팀장 역할에 보고 압박·과제 질문 응답 추가.
- 132, 349: MVP 이후 후보에서 공정성·정직성 삭제.
- 139: 5.4 예시 시각(지연 01:00).
- 145: 5.5 원칙 "미션과 선택 요소로 조립". 반대 의견 내용은 고정, 말투만 생성.
- 152: 6장 도입을 미션 단위로.
- 160, 163: 6.1 협업 방식(문서 주고받기, 중간 점검 v1·리뷰 v2), 동료 가치 "근거를 들어 한 번 다른 의견, 주담당이 정하면 따름", 선점 금지 재정의.
- 171, 181: 6.2 division_min 유지, 주담당 호칭.
- 191~192: 6.3 인터뷰 요약 시각(01:00 알림·01:10 공개), 운영 정책 역할은 "배경 제약".
- 230: 7.1 채용 건 생성에 미션(MVP 고정 1개).
- 252, 254: 7.3 안내 문구(동료 파트 읽기 전용 삭제, 문서 주고받기 설명), 제출 → 보고 요청 → 종료.
- 257~269: 7.4 예외 흐름에 조기 제출 시 보고 요청 추가.
- 297~298, 310, 315, 321: F-13/F-14(문서·보드 규칙), F-21(분업=계획성 카드), F-26(보고 요청은 11L/12 또는 제출 시), F-30(카드별 기록).
- 329, 340, 352~353: 9장 산출물(최종본 섹션별 출처, 주고받은 문서 목록), 책임감 예시 항목, 10장 "요소당 카드 1개"·"혼자 편집"·제외 항목 수정.
- 360, 365: 11장 가설·발생률 정의.
- 386: 12장 "실수" 삭제, "실력 비점수화" 차별화.
- 433~434, 15장 표: 보고 압박의 불쾌감, 반대 의견 공정성(내용 고정), 디브리핑 설명.
- 441: 16장 열린 질문 갱신.
- 540~543, 550: A.3 observe 카드 단위 창, 노드(반대 의견·보고 대기·제출 시 보고 요청), A.4 확장 후보 재정의.

## AGENTS.md
- 23: "같은 채용 건·같은 미션의 지원자는 같은 시나리오".
- 24: 고정 제약에 "실력(오류 발견·산출물 품질)은 점수에 넣지 않는다" 추가.

## docs/common
- architecture.md 21, 35, 48, 62: mission_id, 카드 단위 창·related_card, 대본 이름, `scenarios/missions/<id>/`.
- harness.md 7, 9, 11, 14: Context(반대 의견 입력·정직 사실 입력), Agent Loop(재분업 기준 카드 이름), Recovery(문서 보내기 실패 폴백).
- testing.md 18, 22, 31, 34, 36, 37, 41, 47: 요소 id, 대본 이름, respect 단언 삭제, 레이블 7세트, 초안 시각, 새 선점 유도 픽스처, 추가 테스트(조기 제출 시 정직 카드, 카드 단위 창, 문서 보내기·열기·가져오기).
- rubric.md, scenario-model.md, contracts.md, data-model.md: 요소→카드, 창 정의, mission_id, documents·shares·opens·final_document, observations 키 (session, card_id, window_start), rubric_adjustments.card_id.

## docs/agent/design.md
- 21~22 멱등 키 card_id. 39, 67 midpoint_draft 승격. 51 violation_pointed_out 삭제. 63~64 분업 확정 규칙. 68~70 review(반대 의견·대체 대상), fix_part 삭제, request_report(정직 창·제출 시). 76 respect 삭제. 85 related_card=card id. 93 같이 파트. 97 division_min 근거. 107 선점 금지. 115 초안 시각. 121 카드 이름. 131~133 창 정의·창 밖 메시지 허용. 145~148 완료 기준.

## docs/api/design.md
- 60 문서 모델(documents·버전·보내기·열기·최종본). 64 완료 기준 elements 1~5·mission_id.

## docs/frontend/design.md
- 19 요소 5개·"이렇게 봅니다". 32~35 오피스 레이아웃 전체를 design-direction.md로 교체. 43~45 합계 표기, 산출물 출처, 카드 소섹션. 55 완료 기준 0개·6개 거부.

## docs/worker-infra/design.md
- 12~13 카드 소섹션, 정직 사실(공유 이력·최종본 구성·보드 상태) 계산 위치.

## docs/mcp/design.md
- 10 문서 도구(send_document·버전), 관찰 키 card_id.

## docs/plan.md
- 11, 16, 20, 23, 37, 53, 77, 80: 트랙 범위·소유권(`scenarios/missions/<id>/`)·W3 순서(UI 먼저)·MVP 제외·확장 후보.

## docs/decisions.md
- 7, 8, 19, 34, 40, 45, 49, 54, 66, 76, 82: 대체 결정 절을 추가(예전 행은 지우지 않고 "2026-10-20 재설계로 대체" 표시).

## scenarios (개발 단계에서 반영)
- prompts/colleague.md 11, 14, 30, 49~56, 85~89. manager.md 31, 39~42. guard_patterns.yaml 31~32, 39, 100. fixtures/preemption.yaml, context_leak.yaml.
- e2e/*.yaml 전부. documents/policy.md는 유지.
- catalog.yaml 전체 구조(미션 폴더·요소→cards[]).

## 코드·픽스처 (개발 단계에서 반영)
- infra/db/schema.sql 23, 28, 111, 114, 143, 168, 205.
- apps/web/mocks/fixtures/admin/catalog.json, services/report-worker/tests/fixtures/report_sample.json, tests/fixtures/contracts/*.
- services/api/app/services/scenario.py, web 테스트 3개.

## docs/share, docs/review, docs/handoff
- share/architecture.html 350, 353, 401~407, 420, 423, 546. share/plan-report.html 136, 228, 291, 321~324, 336, 341~346, 357~361, 367, 393~394, 492, 498. review/design-review.html은 "이후 변경" 주석만. handoff.md 25, 88.

## 점검이 드러낸 공백과 결정
제안서 7절(설계 결정)과 8절(기획 결정), design-direction.md "결정" 절에 전부 정리됨: 제출 → 보고 → 종료, 슬롯 공식, division_min 유지, 파트 의존 관계, 반대 의견 내용 고정, 선점 금지 재정의, 기여 판정(문서 주인), 창 밖 근거 범위, 관찰 키, 이름 정리, 주담당 호칭.
