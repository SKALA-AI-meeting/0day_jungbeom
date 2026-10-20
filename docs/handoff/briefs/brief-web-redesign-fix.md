# 브리프: web-redesign 수정 라운드 1 (UI/UX 페르소나 리뷰 반영)

리뷰 원문: `docs/handoff/reviews/review-uiux-view.md`(worktree에 있음, 스크린샷 `uiux-shots/`). 같은 브랜치에서 이어서 작업하고 커밋한다. 리뷰 파일은 `git add`해서 함께 커밋한다(스크린샷 폴더는 올리지 않는다, `.gitignore`에 `docs/handoff/reviews/uiux-shots/` 추가 허용). 계약 변경은 main에 반영됐다(아래 "계약 변경"), worktree에는 아직 없으니 이 브리프의 설명대로 적용한다.

## 계약 변경(오케스트레이터 결정, main d6f9ca1·27e5f1d)
- `POST .../share {channel, note?}`: 문서 카드 메시지 본문은 지원자가 쓴 `note`뿐, 없으면 빈 문자열. 시스템이 "1번 v1 보냅니다"를 만들지 않는다(B7).
- State `session.alias` 추가(R18). mock 픽스처 `state*.json`의 session에 alias를 넣고 킥오프 파싱(`aliasOf`)은 alias가 없을 때의 폴백으로만.
- Report 카드 소섹션 `window {start_min, end_min}`(관찰 창). label 항목은 met·unmet과 무관하게 판정 창의 지원자 메시지를 evidence에 싣고 없으면 no_record(B6). mock `report.json`에 window를 넣고(카드 시각 기준 scenario-model 창) 화면은 `connection_gaps`와 겹치면 카드 머리에 "이 구간 연결 끊김 mm:ss~mm:ss" 칩, label 항목 근거가 비면 "판정 창 N~M분에 지원자 메시지 없음".
- 지원자 목록 묶음: 확정 중(approving)은 "완료" 묶음(data-model 수정됨, 설계 판단 6 뒤집음).
- final 메모는 리포트 전체 메모(design.md 수정됨, R31은 문구만).
- import `version: null` = 보내지 않은 내 문서 현재 저장본(보고서 변경 요청 4).

## 반드시 고칠 것 (리뷰 차단 B1~B8)
- B1 접속 교체(4000)는 전체 오버레이 + 입력 잠금 + "이 창에서 다시 열기", 끊김은 상단 배너 + 보내기 대기 표시.
- B2 자료 탭은 공개 전 문서에 시각을 쓰지 않는다("공유 예정"만). 시각은 킥오프·알림 메시지가 말한다. 공개 뒤 "공개됨".
- B3 동의 화면에 관찰 요소 이름(`elements_names`), "기록은 90일 보관 뒤 삭제", "어시스턴트를 쓰는지 여부는 점수에 들어가지 않습니다".
- B4 남은 시간은 "1분 42초"처럼 단위, 10분 전부터 상단 마감 배너, 새 줄이 오면 맨 아래에 있을 때 끝까지 스크롤, 2분 전 토스트 확인.
- B5 dev 데이터 토글은 화면 오른쪽 아래 작은 접힘 칩으로(무엇도 덮지 않게).
- B6 위 계약대로.
- B7 보내기 팝오버에 "한마디(선택)" 입력, 본문은 그것만. mock 대본의 동료 보내기 메시지도 카드 + 짧은 한마디 형태로.
- B8은 scenario 몫(문구)이라 web은 서버 문장을 그대로 두되 `persona_note`에 "values:"가 있으면 그대로 보이게만 둔다(수정 금지).

## 이번 라운드에 같이 고칠 권장 항목
R1, R2(설계 판단 4 뒤집음: 대화 채널의 "보냈어요" 줄 제거, 전체 기록에만), R4, R5, R6, R7, R8, R9, R10, R11, R12, R14, R15, R16, R17, R20, R21, R22, R23, R24, R25, R26, R28, R29, R31(문구).
polish로 넘길 것(보고서에 적기만): R3, R20의 기록 화면 머리 고정 외 세부. scenario로 넘긴 것(web은 그대로): R13(422 문구), R18 alias 값, R19(프롬프트 조건), R27(픽스처 candidate_count), B8, R30(사용자 결정).

## 완료
기존 완료 기준 유지(`pnpm test`·`pnpm lint`·build, review-animations·break-ui 재확인 간단히). 보고서 `docs/handoff/reports/web-redesign-report.md`에 "## 수정 라운드 1" 절을 추가: 항목별 처리(고침/polish로/scenario로), 바뀐 설계 판단, 새 진입 경로 변경점. 마지막 응답은 경로 한 줄. 주석 규칙(역할·알아야 할 로직·예외 의도) 유지.
