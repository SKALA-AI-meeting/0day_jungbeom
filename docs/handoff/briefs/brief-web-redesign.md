# 브리프: web-redesign 트랙 (P1)

역할: 재설계된 UI를 **mock으로 먼저** 만든다. worktree `../Day-0_zaeho.worktrees/web-redesign`(현재 폴더), 브랜치 `track/web-redesign`. 기준 커밋 eeda2a1(main), 계약 커밋 eeda2a1(`docs/common/contracts.md` 고정), catalog_version 없음(mock은 픽스처만 읽는다).

## 공통 규칙
- 커밋은 자기 브랜치에만. main 병합·push 금지. 커밋 메시지는 한국어 한 문장 + 본문에 실행한 테스트 명령.
- `infra/.env`·`.env.local` 키 값 출력·복사 금지. 실제 스택: **사용 안 함**(api·MCP·DB 기동 금지, 전부 `NEXT_PUBLIC_MOCK=1`).
- 소유권 밖 파일은 수정하지 않는다. 계약(`docs/common/contracts.md`)이나 공용 픽스처(`tests/fixtures/contracts/`)가 바뀌어야 하면 보고서에 "변경 요청"(영향 경로·요청/응답 예시)으로 적고 mock 쪽에서 가능한 범위로 계속한다. `docs/common/*`·`docs/decisions.md`·`docs/plan.md`·`docs/handoff.md`는 오케스트레이터만 고친다.
- TDD, happy path 중심(`docs/dev-process.md`). 완료 기준 한 줄당 vitest 하나 안팎, 그 이상 늘리지 않는다.
- 다른 트랙(scenario-redesign)이 같은 시각에 `services/`·`scenarios/`·`tests/fixtures/`·`infra/`를 고치고 있다. 그 폴더는 읽기만 한다.

## 읽을 것 (순서대로)
1. `AGENTS.md`, `PRD.md`(특히 7장 지원자 흐름·관리자 화면·리포트)
2. `docs/common/contracts.md`(정본. 관리자·지원자 REST, WS 프레임, State 스냅샷, Report, 전체 기록), `docs/common/scenario-model.md`(120분·카드 7장 시각), `docs/common/rubric.md`(항목 id·사유 문장·근거 타입), `docs/common/data-model.md`
3. `docs/frontend/design-direction.md` → `docs/frontend/design-system.md` → `docs/frontend/design.md`(화면 규칙·경로·mock 데이터 형태·**완료 기준**)
4. `docs/plan.md`(web-redesign 행, 파일 소유권, 병렬 규칙), `docs/dev-process.md`, `docs/decisions.md`의 2026-10-20 "인성 5요소·문서 주고받기 재설계"·"개발 전 리뷰 3종 반영" 절
5. 리뷰 반영 지시서 `docs/handoff/reviews/review-redesign-triage.md`, 지원자 관점 `review-candidate-view.md`, 담당자 관점 `review-admin-view.md`(화면에 직접 닿는 요구가 많다), `review-plan.md` 3·4절
6. `docs/handoff/reports/fixtures-align-report.md`(픽스처 id 규칙·contracts 어긋남 메모), `tests/fixtures/README.md`와 `tests/fixtures/contracts/*.json` 73개(화면이 그릴 데이터의 정본 예시)
7. 기존 코드: `apps/web/` 전체(옛 설계의 관리자·오피스 화면, `mocks/README.md`·`index.ts`·`types.ts`·`ws-replay.ts`, `components/ui/`, `lib/api.ts`·`lib/ws.ts`), 앞선 보고서 `docs/handoff/reports/web-admin-report*.md`·`web-office-report*.md`·`foundation-report*.md`의 web 관련 "다른 트랙에 알릴 것"
8. 디자인 스킬: `apps/web/.agents/skills/<이름>/SKILL.md`(git 무시, worktree에 복사돼 있다. 없으면 `cd apps/web && npx -y skills@latest add emilkowalski/skills --yes`). 화면 구성 `emil-design-eng`, 라이브러리 확인 `pick-ui-library`, 모션 `animate`, 마무리 `review-animations`·`break-ui`.

## 허용 파일 (docs/plan.md 소유권 web-redesign 행)
`apps/web/app/`, `apps/web/components/`(ui 포함), `apps/web/app/globals.css`, `apps/web/lib/api.ts`·`lib/ws.ts`, `apps/web/mocks/` 전부, `apps/web/public/`, web 테스트, `apps/web/package.json`·`pnpm-lock.yaml`(사전 허용), `apps/web/.prettierignore`(`.agents` 추가 허용). 재설계 기간 동안 web-admin·web-office·foundation의 web 소유권을 이 트랙이 받는다.
사전 승인된 공용 변경: 위 package/lock·prettierignore뿐. 루트 `Makefile`·`infra/`·`tests/`·`docs/common/`은 요청만.

## 범위
`docs/frontend/design.md` 전체를 mock으로 구현한다. 옛 화면(요소 4개·공유 문서 편집·리드 호칭)은 새 설계로 바꾼다(남기지 않는다).
- 지원자 `/s/[token]`: 링크 입장(만료·완료·취소 안내) → 안내·동의(점수 설명 세 줄, 외부 도구 한 줄, 문의 창구) → 대기(레이아웃 그림, 팀 소개) → 가상 오피스(레일 / 대화↔열린 문서 / 오른쪽 탭 4개: 내 문서·보드·자료·어시스턴트, "?" 안내) → 제출 확인 창 → 보고 대기(reporting, 5분 카운트, 채널 잠금 없음) → 디브리핑(최종본 열람 기한, 설문 2문항, 문의 창구). 재연결 후 상태 복원, reporting 상태 재입장.
- 문서 주고받기: 내 문서 보내기(버전↑, DocCard 메시지) → 동료 문서 받기 → DocViewer 열기(opens 기록) → 문서에 매인 답글(참조 칩) → 최종본에 가져오기(출처 칩, 편집 원문 보존) → 제출.
- 보드: 담당 없음 5장 시작 → 담당(나·도현·둘 다) 채우면 `division.confirmed`+SystemLine, 끌어 놓기(칸·순서), 상세 패널 "언제까지" 프리셋·의존 배지, 확정 뒤 재배정.
- SystemLine 종류 전부, 개인 알림(보낸 사람·"나에게만"·"공개됨"), 편집 중 새 메시지 Toast, 어시스턴트 응답 복사, 접속 끊김 줄, 2분 전 경고.
- 관리자: `/admin/positions/new`(미션 1개 표시, 요소 5개 카드 기본 전체 선택·체크 해제, 뺐을 때 차이 한 줄, 0개·6개 거부, 샘플 리포트 링크), `/admin/positions/[id]`(상태 묶음·필터·세 수 점수 met/unmet/no_record·실패 행동 안내·삭제 예정일·재초대·다시 생성·취소), `/admin/sessions/[id]/report`(요약표, 최종본 출처 칩과 편집 원문 나란히, 주고받은 문서 목록, 접힌 카드 소섹션, 기록 기반/AI 분류 기반 칩, 사유 문장, 정직 주석, 시간순 AI 활용, 검토 완료 확인 창·검토자 이름, final 메모 추가, 인쇄 미리보기 전부 펼침), `/admin/sessions/[id]/record`(전체 기록 타임라인, 리포트 "기록에서 보기"가 해당 줄 하이라이트), `/admin/sample-report`(픽스처 정적 렌더). 로그인·가입·목록은 새 디자인 토큰으로 맞춘다.
- mock 데이터: `apps/web/mocks/fixtures/`를 `tests/fixtures/contracts/`의 **같은 id·같은 형태**로 다시 만든다(복사 뒤 화면에 필요한 WS 재생 스크립트만 추가). 두 폴더의 형태가 어긋나면 계약 쪽이 맞고, 계약 자체가 모자라면 변경 요청.
- 호칭은 "주담당". "리드"·"평가"·"점수"가 지원자 화면에 보이지 않는다(동의 화면의 점수 설명 제외). 서비스 이름 Day Zero 변주 자유.

## 완료 기준 (`docs/frontend/design.md` "완료 기준 (web-redesign)" 전부)
관리자 2줄, 리포트 1줄, 지원자 1줄, 문서 흐름 1줄, 보드 1줄, 알림·SystemLine 1줄, `review-animations`·`break-ui` 통과. 각 줄을 `NEXT_PUBLIC_MOCK=1 pnpm dev`(3000)에서 직접 확인하고 vitest(줄당 1개 안팎)로 고정한다. `pnpm lint`, `pnpm test`, 루트 `make lint`(web 부분)·`make test`(web 부분) 통과. 확인이 끝나면 dev 서버는 끈다(`lsof -ti:3000 -sTCP:LISTEN | xargs kill`).

## 관문 (이 트랙만)
구현 완료 보고 → 오케스트레이터가 UI/UX 전문가 페르소나 리뷰(실제 mock 화면·스크린샷)를 돌림 → 지적 반영 → 같은 탭 오른쪽 Codex 코드 리뷰(`REVIEW.md`) → 반영 → 사용자가 mock으로 직접 확인 → 피드백 반영 → 병합. 리뷰를 쉽게 하도록 보고서에 **화면별 진입 경로와 mock 조작 순서**(어느 토큰·어느 버튼으로 어떤 상태가 나오는지)를 적는다.

## 보고
`docs/handoff/reports/web-redesign-report.md`에: 기준 커밋, 완료 기준 각 줄의 명령·결과·검증 방식(전부 mock), 수정 파일 목록, 화면별 진입 경로·mock 조작 순서, 남은 문제, 변경 요청(계약·픽스처), 다른 트랙에 알릴 것(web-integrate가 실 API에 붙일 때 바꿀 지점, web-polish에 넘길 ui·globals.css·brand 목록), 후속 인수자에게 넘길 것. 마지막 응답은 경로 한 줄.
