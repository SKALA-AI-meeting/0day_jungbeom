# gm-fix 보고

기준: track/debate e4b91f8. 리뷰 `gm-uiux-review.md`의 B4~B7, N1·N3·N4·N5·N11·N12·N13.

| 항목 | 수정 | 방식 |
|---|---|---|
| B4 | `use-session.ts`, `proposal-editor.tsx` | 저장 시각을 epoch ms로 두고 `savedLabel`로 "방금/n분 전 저장됨" 표기(20초마다 갱신). 테스트 `proposal-editor.test.ts` 추가 |
| B5 | `mocks/fixtures/debrief.json`, `debrief-screen.tsx`, `mocks/debate.ts` | "각자의" 삭제, 첫 문장(R1 고정)과 이어지는 설명을 문장 단위 문단으로 분리 |
| B6 | `debate-view.tsx` PhaseBar | 지난 단계 아이콘 뒤에 "· 합의/시간 초과" 글자 추가 |
| B7 | `fixtures/sample-report.json`, `mocks/fixtures/{report,evaluation_save,internal_evaluations,admin_review_request}.json`, `report-view.tsx`, `report-view.test.tsx` | 메모를 "09:06 발언 앞뒤에서…"로, "(앵커 N)" 삭제, 화면에서도 `cleanRationale`로 걸러냄 |
| N1 | `chat.tsx` | 묶음 머리에서 시각 제거 |
| N3 | `debate-view.tsx`, `ui/tabs.tsx` | 패널을 Tabs 안으로 넣고 `keepMounted`로 aria 연결 복구, 빈 tabpanel 제거 |
| N4 | `chat.tsx`, `decision-panel.tsx`, `proposal-editor.tsx` | 입력에 `focus-visible:ring-2 ring-accent/40` 추가 |
| N5 | `chat.tsx` | 스크롤러에 `role="log" aria-live="polite"` |
| N11 | `record-view.tsx` | `bg-canvas/95` -> `bg-canvas` |
| N12 | `report-view.tsx` | `print-break`를 details 전체에서 summary와 판단 이유 dl로 옮김 |
| N13 | `report-view.tsx` | "지원자 지원자A · 표시 이름 김지원" |

## 실행
apps/web에서 `pnpm install --frozen-lockfile`, `pnpm test`(14 파일 통과), `pnpm lint`(eslint+prettier 통과), `pnpm build` 통과. 지원자 컴포넌트·mock의 유형 id grep은 디브리핑 외 0건(admin 표시 이름·테스트 정규식 제외).

## 남은 문제
- `lg` 미만 PC 안내(N2)는 범위 밖이라 제거하고 단일 레이아웃(min-w-[1024px])으로 되돌림.
- 인쇄 빈칸(N12)과 화면 변경은 브라우저 재캡처로 확인하지 않음(재캡처는 범위 밖).
- 계약 예시 픽스처(`docs/common` 쪽)의 debrief "각자의"·앵커 표기는 원본에서 별도로 고쳐야 함(apps/web 사본만 수정).
