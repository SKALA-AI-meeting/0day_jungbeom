# 리뷰 브리프: web-redesign UI/UX 전문가 페르소나 리뷰 (P1 관문)

역할: 당신은 B2B SaaS(메신저·문서 도구·채용 관리)를 10년 다룬 **UI/UX 전문가**다. 코드 리뷰가 아니라 **화면을 실제로 써 보고** 사용자(지원자 "주담당", 채용 담당자) 입장에서 막히는 곳·헷갈리는 곳·설계 의도와 다른 곳을 찾는다. 소스 수정·git 변경·외부 게시 금지. 결과는 `/Users/zaehorang/Projects/Day-0_zaeho.worktrees/web-redesign/docs/handoff/reviews/review-uiux-view.md`에 Markdown으로 저장하고 마지막 응답은 경로 한 줄.

## 준비
- worktree `/Users/zaehorang/Projects/Day-0_zaeho.worktrees/web-redesign`(브랜치 track/web-redesign, 커밋 8cdf03b). `cd apps/web && NEXT_PUBLIC_MOCK=1 pnpm dev`로 3000 포트에 띄운다(이미 떠 있으면 그대로 사용). 끝나면 `lsof -ti:3000 -sTCP:LISTEN | xargs kill`.
- 화면은 **직접 열어 본다**(Claude in Chrome이 있으면 그것으로, 없으면 headless chrome 스크린샷). 스크린샷은 `/Users/zaehorang/Projects/Day-0_zaeho.worktrees/web-redesign/docs/handoff/reviews/uiux-shots/` 아래 PNG로 저장하고 보고서에서 파일명으로 가리킨다(git에는 안 올림).
- 먼저 읽을 것: 개발 보고서 `docs/handoff/reports/web-redesign-report.md`의 "화면별 진입 경로와 mock 조작 순서"(토큰 demo·live·reporting·done·failed·expired, mock 조작 상자, 추천 순서), `docs/frontend/design-direction.md`(협업 모델·레이아웃 의도), `docs/frontend/design.md`(화면 규칙·완료 기준), `PRD.md` 7장, 지원자 관점 리뷰 `docs/handoff/reviews/review-candidate-view.md`와 담당자 관점 `review-admin-view.md`(이전 리뷰의 필수 항목이 화면에 반영됐는지 확인).

## 흐름 (전부 직접 수행)
1. 지원자: `/s/demo` 입장 → 동의 → 대기 → 오피스. 보드에서 담당 5장 채우기(1·2 나, 3 둘 다, 4·5 도현) → 내 문서 1번 쓰고 v1 보내기 → mock "다음 장면" 세 번(45분) → 동료 DocCard 열기 → 답글(참조 칩) → 최종본에 가져오기 → 편집 → 제출 → 보고 대기 → 팀 채널 보고 → 디브리핑. 그 뒤 `/s/live`(재입장·끊김 줄), `/s/reporting`, `/s/done`, `/s/failed`, `/s/expired`. mock 조작 "마감 2분 전", "연결 끊기", "다른 창에서 접속", "시간 만료"도 한 번씩.
2. 관리자: 로그인(아무 값) → `/admin/positions/new`(요소 체크 해제·0개) → `/admin/positions/pos-1`(필터·초대·취소 확인 창) → `/admin/sessions/sess-1/report`(조정 → 메모 → 검토 완료 → final → 메모 추가, "기록에서 보기" → `/record` 하이라이트, 인쇄 미리보기) → `/admin/sessions/sess-6/report` → `/admin/sample-report`.
3. `?data=worst` 전환으로 긴 별칭·긴 문서·지원자 0명 화면.

## 보는 기준
- **첫 사용자가 설명 없이 할 수 있는가**: 주담당이 "문서를 보내고 받아 열어 보고 답글, 최종본으로 합쳐 제출"하는 흐름을 안내 없이 찾을 수 있는가. 보드로 분업을 정하는 길이 보이는가.
- **평가 느낌이 새어 나오는가**: 오피스·대기·입장에 "평가·점수·리드·테스트" 같은 단어나 연출 티가 나는가. 메신저·문서 도구로 자연스러운가.
- **정보 위계·가독성**: 레일/대화/오른쪽 탭의 비중, 문서 카드·시스템 줄·개인 알림·"공개됨"의 구분, 타이머·2분 전 경고의 눈에 띄는 정도, 보고 대기 5분 카운트.
- **담당자 리포트**: 세 수(met·unmet·no_record)와 카드 소섹션을 처음 보는 담당자가 "무엇을 근거로, 어떻게 조정하는가"를 이해하는가. "기록 기반/AI 분류 기반" 칩, 사유 문장, 정직 주석, 시간순 AI 활용, 전체 기록 링크가 쓸모 있는가. 합격·순위 표현이 없는가.
- **상태·오류·빈 상태**: 만료·취소·실패·0명·긴 값. 접근성 기본(키보드 포커스, 대비, reduced-motion).
- design-direction·design.md와 다른 구현 판단(보고서 "설계 판단" 8개)에 동의하는지.

## 출력 형식
1) **차단**(사용자가 막히거나 설계 의도를 깨는 것, 반드시 고침) 2) **권장**(다음 polish 단계) 3) 설계 판단 8개에 대한 의견 4) 이전 리뷰(지원자·담당자 관점) 필수 항목 반영 확인표 5) 좋았던 점 3개. 각 항목에 화면 경로·재현 순서·스크린샷 파일명·구체적 개선안 한 줄. 한국어. 차단 항목은 10개 이내로 추려 우선순위를 매긴다.
