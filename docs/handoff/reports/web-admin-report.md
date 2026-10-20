# web-admin 트랙 보고 (W2)

브랜치 `track/web-admin`, 커밋 1개. main 병합·push 없음.

## 완료 기준 실행 결과
| 기준 | 명령 | 결과 |
|---|---|---|
| 화면당 렌더 테스트(로그인·가입, 목록+생성, 지원자 목록·초대, 리포트) + mock 흐름 | `cd apps/web && pnpm test` | 6 파일 8 테스트 통과 |
| 린트 | `cd apps/web && pnpm lint` | eslint·prettier 통과 (`tsc --noEmit`도 통과) |
| 루트 | `make lint`, `make test` | 통과 (api 폴더 없는 서비스는 건너뜀) |
| 가입→생성(요소 0·5개 거부)→초대(링크 복사)→목록 7종·합계→draft→조정(메모 필수, already_reviewed·memo_required)→검토 완료→reviewed 이력 | `mocks/admin.test.ts`(mockRequest 흐름) | 통과 |

## `NEXT_PUBLIC_MOCK=1 pnpm dev`로 확인한 화면
- /admin/signup → 가입 후 /admin/positions 이동
- /admin/positions (목록), /admin/positions/pos-1 (지원자 9명, 상태 배지 9종, 합계·요소 칩, 기본/담당자 점수 출처)
- /admin/sessions/s-ready/report: draft 배지·헤더 문구·산출물·평가표, 값 변경 시 메모 필수 오류와 담당자 점수 미리보기, 메모 입력 후 검토 완료 → "확정 중…" → 폴링으로 final, 검토 이력 표시
- 확인 못 함(테스트로만 검증): /admin/login, /admin/positions/new 화면 직접 조작, 링크 복사 버튼 클릭, 초대 취소 확인 창

## 수정 파일
- `apps/web/app/admin/` (layout, login, signup, positions, positions/new, positions/[id], sessions/[id]/report)
- `apps/web/components/admin/` (types, client, format, review, score, auth-form, shell, position-list, position-form, candidates, report-view, 테스트 4개)
- `apps/web/mocks/admin.ts`, `mocks/admin.test.ts`, `mocks/fixtures/admin/{catalog,positions,candidates,report}.json`

## 구현 메모
- 토큰은 localStorage(`dayzero.admin.token`). 없으면 /admin/login으로 보냄.
- 리포트 단계 판정: `stage=final` → 검토 완료, `stage=draft`이고 `rubric.review`가 있으면 확정 중(폴링 2초), 아니면 검토 대기. 서버의 GET 합성 규칙(admin.py `merge_rubric`)을 그대로 따름.
- 채용 건 이름은 GET /admin/positions 목록에서 id로 찾음(단건 조회 API 없음).
- mock은 서버 오류 코드(memo_required, invalid_item, duplicate_item, already_reviewed 우선순위, invalid_elements, conflict)를 흉내 냄. 확정 중 GET 2회 뒤 final.
- 요소별 칩의 분모는 4로 고정(요소당 항목 4개).

## 남은 문제
- 렌더 테스트는 jsdom·testing-library 없이 `renderToStaticMarkup`으로 함(package.json 변경 불가). 클릭·폴링 동작은 브라우저 수동 확인으로 대체.
- 계약에 열려 있는 필드는 선택으로 처리: 항목의 `no_record_reason`·`response_minutes`, 섹션의 `aux_facts`(문자열 또는 `{text}`)·`out_of_window_messages[{t_min, channel?, quote}]`·`card_t_min`, `ai_usage.evidence[].category`.
- `lib/api.ts`가 `Idempotency-Key` 옵션을 아직 갖고 있으나 쓰지 않음.

## 변경 요청
- (worker/오케스트레이터) 리포트 JSON에서 AI 활용의 위임·맥락·검증 구분 필드명이 계약에 없음. 화면은 `ai_usage.evidence[].category ∈ delegate|context|verify`를 기대하고 없으면 "기타"로 묶음. 이름이 다르면 contracts.md에 확정 필요.
- (worker) 항목별 기록 없음 사유와 응답 시간 분 값의 위치 확정: 화면은 `items[].no_record_reason`(없으면 섹션의 `no_record_reason`), `items[].response_minutes`를 읽음.
- (foundation, 낮음) `lib/api.ts`의 `idempotencyKey` 옵션 제거.

## 다른 트랙에 알릴 것
- worker: 위 두 필드 이름과 `aux_facts`·`out_of_window_messages` 모양을 맞춰 주세요. 화면은 모양이 달라도 깨지지 않게 방어하지만 값은 안 보입니다.
- web-office/web-polish: `next dev`가 `apps/web/AGENTS.md`를 자동 생성함(커밋하지 않음).
- web-polish: 관리자 화면은 `components/ui`의 Badge·Button·Card·Input·Select·Textarea·ConfirmDialog·StatusBadge·EmptyState만 사용.
