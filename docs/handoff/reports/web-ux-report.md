# web-ux 보고 (S4.5, track/web-ux)

## 반영

| # | 내용 | 위치 |
|---|---|---|
| 1 | 결정 사항 입력칸·기획안 칸에 placeholder, 굵은 테두리(채팅 입력창과 구분), 비활성 이유 한 줄("내용을 적으면 정할 수 있어요"/"후보를 고르면 정할 수 있어요") | `decision-panel.tsx`, `proposal-editor.tsx` |
| 2 | 키워드 단계 결정 사항 패널에 목적·위치 안내 | `decision-panel.tsx` |
| 3 | 디브리핑: 제출 완료 확인과 설문을 위로, 평가와 기록 다음에 장면·요소·AI 동료, 내 발언·제출한 기획안은 접음 | `debrief-screen.tsx` |
| 4 | 확인 창 버튼 "네, 정할게요"(패널은 [이걸로 정하기] 유지). "확정" 단어는 wording 테스트가 막아 쓰지 않음 | `decision-panel.tsx`, e2e |
| 5 | 지원자 목록은 이미 상태 열(`display_status` 기반)이 있어 변경 없음. 채용 건 목록 상태 열은 이번 범위에서 뺐다(MVP 이후, 계약에 상태 필드 없음) | 해당 없음 |
| 6 | 칸 결과 "합의"/"지원자 결정"/"시간 초과": 관리자 리포트(타임라인·근거)는 `support`의 확정 안 지지자 3명 이상 판정(`slotResultText`). 지원자 화면도 동일(아래 outcome 전환) | `lib/resolution.ts`, `admin/format.ts` |
| 7 | 빈칸 경고 창 → 기존 확인 창 → submit 본문 `{blank_warning_shown: true}`(빈 칸 없으면 `{}`) | `proposal-editor.tsx`, `use-session.ts` |

## outcome 전환 (main 7287f90 계약)

- 칸 결과 표시는 `support` 계산 대신 api의 `outcome`(consensus|candidate_decision|timeout)만 본다(`lib/resolution.ts` `resolutionLabel`). 없으면 `resolution`으로 폴백(timeout은 시간 초과, 그 외 합의). 지원자 결정 패널·진행바·관리자 리포트(타임라인·근거)에 같은 함수를 쓴다.
- `outcome` 타입을 `Slot`·`slot.confirmed`·리포트 slots에 더했고 reducer가 WS 값을 반영한다. mock은 지원자가 정하면 `candidate_decision`, AI 채우기는 `consensus`, 시간 초과는 `timeout`을 낸다. 계약 픽스처 사본은 바꾸지 않았다(없으면 폴백).
- 이전 보고의 `filled_by` 갈음과 `slotResultText`는 제거했다. 관리자 기록 요약 문장(`... (consensus)`)은 요약 문자열이라 그대로 "합의"로 나온다(서버가 문장에 결과를 넣어 줘야 함).
- 판단 보류 문구(`evaluate_failed`)는 이미 rubric.md 5장 문구와 같아 변경 없음.

## 사실 지표·기록 요약

- 사실 지표 표에 "제출 때 빈 칸"(`blank_sections_at_submit`, 기획안 칸 이름)과 "빈칸 경고 확인 뒤 제출"(`blank_warning_acknowledged`, null은 "자동 제출") 행을 더했다.
- 기록 요약 문장 끝 토큰(`consensus|candidate_decision|timeout`, 예전 resolution 토큰 포함)을 같은 `resolutionLabel`로 바꿔 보인다. "제출 · 빈 칸 N개(...)" 문구는 그대로 보여 주고 웹이 가정하는 테스트·mock은 없었다.

## Codex 리뷰 반영

- outcome이 없으면 `resolution=timeout`만 "시간 초과"이고 그 밖은 결과 라벨을 붙이지 않는다(`resolutionLabel`이 null, 값만 표시).
- 제출 순서를 저장 완료(대기분 PUT, 409면 최신 초안으로 교체) → 최신 초안으로 빈 칸 검사 → 경고 창 → 제출 확인 창 → submit으로 바꿨다(`submitFlow`, `use-session`의 `prepareSubmit`). submit은 더 이상 저장하지 않는다(창이 떠 있는 동안 편집 불가).
- 흐름 테스트 4건(경고 거친 제출 본문, 빈 칸 없음, 돌아가서 쓰기·취소 시 submit 미호출, 최신 초안 재검사)과 solo_confirm e2e의 "지원자 결정" 단언(결정 사항·진행바)을 더했다. e2e는 실행하지 않았다.
- 제출 흐름이 도는 동안(저장·경고·확인·submit 요청) 기획안 입력을 잠그고 "제출 중…"을 보인다. submit이 끝나면(실패해도 훅이 안내 토스트를 띄운 뒤) 잠금이 풀린다. DOM 테스트 1건(`proposal-editor.dom.test.tsx`)으로 확인했다.

## 기타 판단

- 채용 건 목록은 계약에 상태 필드가 없어 상태 열을 못 만들었다(지원자 목록에는 이미 있음).
- `wording.test.ts`: 빈칸 경고 문구 "비워 둔 칸"(design.md 지정)을 "칸 금지" 검사에서 제외했다.
- e2e 스펙(keyword·solution 확인 버튼 "네, 정할게요", proposal 빈칸 경고 단계)을 맞췄고 실행은 하지 않았다.
- main 병합 시 main의 apps/web이 기준(116fd0d)과 같아 충돌은 모두 이 브랜치 쪽으로 풀었다.

## 테스트

`pnpm test` 50 통과(신규: `lib/resolution.test.ts` outcome·폴백, `report-view.test.tsx` 빈칸 지표·outcome 표시, `proposal-editor.test.ts` 빈 칸 목록·제출 본문), `pnpm lint`·`pnpm build`·`tsc --noEmit` 통과.
