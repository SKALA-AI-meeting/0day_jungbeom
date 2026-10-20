# 리뷰 브리프: web-polish 트랙 (P2)
역할: 읽기 전용 리뷰어. 소스 수정·git 변경·외부 게시 금지. 결과는 `/Users/zaehorang/Projects/Day-0_zaeho.worktrees/web-polish/REVIEW.md`(git에 안 올림)에 Markdown, 마지막 응답은 경로 한 줄.
출력: 1) 반드시 고칠 것 2) 고치면 좋은 것(web-integrate로 넘길 것 구분) 3) 보고서 쟁점 의견 4) web-integrate 주의사항. 파일:줄·한 줄 근거, 한국어.
기준: `docs/handoff/briefs/brief-web-polish.md`(허용 파일: ui 내부 props 불변, globals.css, public/brand, 그리고 conversation·office-view·my-docs·board의 레이아웃·표시만. 상태 로직·API·reducer·saver 변경 금지 — 로고 적용을 위한 link-screens·auth-form·shell·layout·debrief-screen의 한 줄 수정은 오케스트레이터 승인), `docs/frontend/design-system.md` 모션·토큰, 보고서 `docs/handoff/reports/web-polish-report.md`(먼저 읽기). 확인: props 변경 없음, reducer/saver/flow/client diff 없음, 기존 테스트 11개 통과, review-animations·break-ui 표가 실제 코드와 맞는지, 1280 폭에서 편집·제출·팝오버 동선, 분할 보기가 DocViewer·최종본 동시 편집 상태를 깨지 않는지, 접근성(reduced-motion·포커스) 보존.
대상: `git diff main...HEAD`. 실행: `cd apps/web && pnpm test && pnpm lint && NEXT_PUBLIC_MOCK=1 npx next build`.
