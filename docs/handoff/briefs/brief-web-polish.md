# 브리프: web-polish 트랙 (P2, web-integrate보다 먼저 시작)

역할: web-redesign 결과를 다듬는다(모션·반응형·브랜드·작은 UX 마무리). worktree `../Day-0_zaeho.worktrees/web-polish`(현재 폴더), 브랜치 `track/web-polish`. 기준 커밋 main 2019069(web-redesign 병합). 계약 커밋 37bed0b(contracts.md). 실제 스택: 사용 안 함(`NEXT_PUBLIC_MOCK=1`만).

## 공통 규칙
- 커밋은 자기 브랜치에만. 키 값 출력 금지. TDD happy path(기존 vitest 11개가 깨지지 않게, 새 테스트는 완료 기준에 해당하는 것만).
- `docs/common/*`·`docs/plan.md`·`docs/handoff.md` 수정 금지. 계약 변경 필요하면 보고서에 변경 요청.
- **같은 시각에 scenario-redesign이 `services/`·`scenarios/`·`tests/fixtures/`를 고치고 있다. 그 폴더는 읽기만.** web-integrate는 이 트랙이 병합된 뒤 시작하므로 `apps/web` 안에서 겹칠 다른 pane은 없다.
- 주석은 역할·알아야 할 로직·예외 의도 수준(AGENTS.md).

## 읽을 것
AGENTS.md, docs/plan.md(web-polish 행·소유권), docs/frontend/design-system.md(토큰·컴포넌트·모션 절), design-direction.md ④ 레이아웃, design.md(화면 규칙), `docs/handoff/reports/web-redesign-report.md`의 "web-polish(넘길 목록)"·"다른 트랙에 알릴 것"·수정 라운드 표(R3 등 polish로 넘긴 항목), `docs/handoff/reviews/review-uiux-view.md` 2절 권장(polish로 분류된 것), 디자인 스킬 `apps/web/.agents/skills/{animate,review-animations,break-ui,emil-design-eng}/SKILL.md`(없으면 `npx -y skills@latest add emilkowalski/skills --yes`).

## 허용 파일
`apps/web/components/ui/` 내부(**props 변경 금지**), `apps/web/app/globals.css`, `apps/web/public/brand/`, 그리고 이번 트랙에 한해 레이아웃·표시만 바꾸는 범위로 `components/office/conversation.tsx`(같은 시각 문서 카드 묶기 R3), `components/office/office-view.tsx`(열 폭·≥1440 분할 보기·1280 폭), `components/office/my-docs.tsx`(최종본 바닥 저장 실패 지속 표시, `version: null` 출처 문구 "현재 저장본"), `components/office/board.tsx`(드롭 scale 0.98→1, 넓은 보드). 이 네 파일에서 **상태 로직·API 호출·reducer·saver는 손대지 않는다**(web-integrate 몫).

## 범위
1. 모션: `animate` 기준으로 문서 열기/닫기·카드 이동·메시지 도착·팝오버·토스트를 점검하고 `review-animations` 통과. 보존: doc-viewer 160/120ms, board 150ms, reduced-motion, 인쇄 규칙.
2. 반응형: 1280 폭에서 편집·제출·팝오버 동선이 되는지(레일 접기 또는 패널 폭 조정), ≥1440에서 받은 문서를 보며 내 문서를 고치는 분할 보기.
3. 브랜드: `public/brand/`에 간단한 워드마크(SVG, "Day Zero" 글자 기반)와 파비콘. 로그인·입장·대기·관리자 셸에 적용.
4. 작은 UX: R3 카드 묶음(같은 분·같은 사람의 문서 카드를 한 메시지 블록에 2열), 최종본 저장 실패 지속 표시, "현재 저장본" 문구, 빈 완료 칸 접기.
5. `break-ui`: 긴 별칭·빈 목록·긴 메시지·긴 문서·요소 5개 카드 겹침·`?data=worst` 재점검.

## 완료 기준 (docs/plan.md web-polish 행)
`review-animations`·`break-ui` 통과(스킬 기준 표를 보고서에), 1280·1440·1920 세 폭 스크린샷 각 3장(오피스·리포트·생성)을 `docs/handoff/reports/web-polish-shots/`(git 무시)에, `pnpm test`·`pnpm lint`·`NEXT_PUBLIC_MOCK=1 npx next build` 통과. 끝나면 dev 서버 종료.

## 보고
`docs/handoff/reports/web-polish-report.md`: 기준 커밋, 항목별 처리, 바뀐 파일, review-animations·break-ui 표, 남은 문제, web-integrate에 알릴 것(이 트랙이 손댄 office 파일의 어느 줄이 레이아웃용인지). 마지막 응답은 경로 한 줄.
