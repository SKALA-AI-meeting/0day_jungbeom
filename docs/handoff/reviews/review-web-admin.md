# web-admin W2 리뷰

대상: `track/web-admin`, `git diff main...HEAD`, HEAD `f2f4c38`. 개발자 보고서를 먼저 읽고 PRD·설계·계약·실제 관리자 라우터와 대조했다. 판정: **수정 후 재리뷰 필요**.

직접 실행: `cd apps/web && pnpm test`(6파일·8테스트 통과), `pnpm lint`(통과), `pnpm exec tsc --noEmit --incremental false`(통과), `git diff --check main...HEAD`(통과). mock 라우터는 메모리에서 TypeScript를 변환해 추가 재현했다. 브라우저 조작·실서버 통합·루트 make 명령은 이번 리뷰에서 실행하지 않았다. 소스·Git 상태 변경 명령·gh·외부 게시 없이 이 보고서만 작성했다.

## 1) 반드시 고칠 것(병합 차단)

1. **[P1] 재초대에서 이전 응시를 연결할 수 없음** — `apps/web/components/admin/client.ts:83`: 초대 입력이 `{alias, email}`뿐이며 화면에도 이전 세션을 선택하거나 재초대하는 경로가 없어 PRD F-02의 P0 완료 조건을 충족하지 못한다.
   - `apps/web/components/admin/candidates.tsx:41`은 이미 연결된 fixture의 “재응시” 표시만 한다. 실패한 지원자를 다시 초대해도 `previous_session_id`가 전송되지 않아 별개 응시로 저장된다. 기존 응시를 지정하는 동선과 요청·mock 저장까지 연결해야 한다. 기준: `PRD.md:280`, `docs/common/contracts.md:39`.

2. **[P2] 채용 건 생성 화면에 타임라인·지원자 안내 문안이 없음** — `apps/web/components/admin/position-form.tsx:84`: 요소와 평가표만 출력하고 `catalog.timeline`, `session_minutes`, `candidate_notice_template`를 사용하지 않아 `/admin/catalog`가 요구하는 생성 화면 미리보기가 빠졌다.
   - 선택 요소에 따른 시각과 안내 문안을 보여 줘야 한다. 목업의 시각도 함께 맞춰야 한다. `apps/web/mocks/fixtures/admin/catalog.json:95`의 분업 0.1·마감 보고 0.9는 실제 카탈로그의 0.0833·0.9167과 다르고, `:99`의 배치 설명은 리뷰에 붙는 카드를 제외한다는 서버 조건을 누락했다. 기준: `docs/common/contracts.md:33`, `services/api/app/routers/admin.py:57`, `scenarios/catalog.yaml:69`.

3. **[P2] 확정 중 GET이 한 번 실패하면 폴링이 영구 중단됨** — `apps/web/components/admin/client.ts:122`: 조회 실패 시 기존 리포트를 `null`로 지워 `apps/web/app/admin/sessions/[id]/report/page.tsx:22`의 `approving`이 false가 되고 타이머가 해제된다.
   - 재현 흐름: 검토 POST 성공 → approving 리포트 수신 → 다음 GET 일시 실패. 이후 서버가 reviewed가 되어도 화면은 오류만 남고 재조회하지 않는다. POST 직후 첫 GET이 실패해도 같은 문제가 생긴다. 마지막 성공 데이터를 유지하거나 제출 성공 상태를 바탕으로 GET을 재개하고, 수동 재조회 경로도 제공해야 한다. 생성·초대 POST 자동 재시도와는 별개다.

4. **[P2] 계약에 있는 카드 발생 시각을 읽지 않음** — `apps/web/components/admin/report-view.tsx:224`: `section.card_t_min`만 표시하고 계약의 `evidence[].context.card_at_t_min`을 읽지 않아 정상 계약 응답에서도 발생 시각이 사라진다.
   - 현재 fixture는 두 위치를 모두 넣어 문제를 가린다. 섹션의 추가 필드가 없는 응답에서도 근거의 context 값을 이용해 표시해야 한다. 새 섹션 필드를 필수로 정하려면 오케스트레이터의 계약 확정이 먼저다. 기준: `docs/common/contracts.md:69`, `docs/frontend/design.md:45`.

5. **[P2] 완료된 mock 세션이 조회만으로 approving으로 되돌아감** — `apps/web/mocks/admin.ts:205`: `applyReview()`가 후보 행을 approving으로 바꾼 뒤 `row.status === "reviewed"`를 검사하므로 초기 reviewed 여부를 잃는다.
   - 직접 재현: 초기 `s-reviewed` 목록은 reviewed → 첫 report GET은 `{stage:"draft", reviewed_at:null}`, 목록도 approving → 두 번째 GET에서 final. 완료된 리포트를 열자마자 검토 이력이 보여야 하며 GET으로 완료 상태가 후퇴하면 안 된다. 변경 전 상태를 보존해 초기화해야 한다.

6. **[P2] 완료 후 동일 리뷰 재전달의 mock 응답이 계약과 다름** — `apps/web/mocks/admin.ts:232`: 동일 본문이면 현재 단계와 관계없이 `{status:"approving"}`을 반환한다.
   - 직접 재현: s-ready에 조정 제출 → GET 2회로 final 확인 → 동일 POST 재전달 결과가 approving. 계약과 실제 API는 이때 reviewed를 반환한다. 현재 상태를 돌려줘야 한다. 기준: `docs/common/contracts.md:42`, `services/api/app/routers/admin.py`의 `review()`.

7. **[P2] 새 mock 테스트가 명시된 파일 소유권 밖에 있음** — `apps/web/mocks/admin.test.ts:1`: 소유권표에서 `mocks/`는 foundation 소유이고 web-admin 예외는 `admin.ts`·`fixtures/admin/`뿐이라 이 새 파일의 경로는 허용 범위 밖이다.
   - 테스트 자체는 필요한 정상 흐름 검증이다. `components/admin/` 안으로 옮기거나 오케스트레이터가 테스트 경로 예외를 명시해야 한다. 보고서에는 해당 승인 근거가 없다. `components/ui` 내부·props, package.json, lib/api.ts, 공용 계약 문서 변경은 없었다. 기준: `docs/plan.md:49`, `docs/plan.md:57`, `docs/plan.md:63`.

## 2) 고치면 좋은 것

- `apps/web/components/admin/report-view.tsx:234`: 관찰 문장 옆 조정 메모가 `section.observed`가 있는 분기에서만 보여 관찰 없음 항목을 담당자가 정정하면 메모는 평가표 아래에만 남는다. 관찰 없음 안내 옆에도 보여 주면 정정 취지를 바로 읽을 수 있다(`docs/common/rubric.md`의 메모 병기 원칙).
- `apps/web/components/admin/report-view.test.tsx:35`: 테스트 범위는 happy path와 필수 실패에 집중돼 과잉은 없다. 다만 정적 렌더·순수 함수·mock 호출 테스트는 페이지의 클릭·폴링 연결을 검증하지 않으므로 “전 흐름 통과”로 확대 해석하면 안 된다. 위 오류 재현은 기존 테스트 흐름에 필요한 단언을 보강하고, 의존성 추가 없이 가능한 수동 확인 결과도 남기는 정도면 충분하다.

## 3) 보고서의 결정·남은 문제·변경 요청에 대한 의견

보고서에는 “내가 정한 것” 제목이 없어 “구현 메모”의 결정을 해당 항목으로 검토했다.

| 쟁점 | 의견·근거 |
|---|---|
| 토큰 localStorage 보관 | 수용. `apps/web/components/admin/client.ts:10`은 Bearer 호출과 로그인 전 화면 차단에 연결된다. 이번 범위에서 별도 인증 체계 확장은 필요 없다. |
| draft + rubric.review로 approving 판정 | 수용. `apps/web/components/admin/review.ts:13`은 실제 API의 제출 후 합성 규칙과 일치한다. 다만 폴링 실패 복구는 필수 수정 3번 대상이다. |
| 채용 건 이름을 목록 API에서 조회 | 수용. `apps/web/app/admin/positions/[id]/page.tsx:21`은 단건 API 없는 현 계약에서 합리적이며 API 추가 요청은 불필요하다. |
| 오류 코드·우선순위를 mock에서 재현 | 방향 수용. `apps/web/mocks/admin.ts:224`는 already_reviewed를 본문 검증보다 우선한다. 다만 완료 상태 초기화·멱등 응답은 필수 수정 5·6번 대상이고, 테스트의 서로 다른 정상 본문 검사만으로 잘못된 본문의 오류 우선순위까지 검증됐다고 할 수는 없다. |
| 요소당 항목 수 4 고정 | 수용. `apps/web/components/admin/score.tsx:25`의 `4 - judged`는 PRD·카탈로그의 요소당 4항목 제약과 맞는다. 실제 칩의 분모는 고정 4가 아니라 judged이며 보고서의 “분모 4 고정” 설명은 “기록 없음 수를 4에서 계산”으로 정정하는 편이 정확하다. |
| 정적 렌더 테스트·수동 확인 대체 | 조건부 수용. 패키지 소유권을 지켰고 테스트 과잉은 없다. `apps/web/components/admin/candidates.test.tsx:34`는 복사 버튼의 존재만 확인하므로 링크 복사 성공을 검증한 것으로 볼 수 없다. 보고서가 직접 조작하지 못한 로그인·생성·복사·취소 동선은 M1 연결 확인에서 실제로 실행해야 한다. |
| no_record_reason·response_minutes 선택 필드 | 계약 구체화 요청에 동의. `apps/web/components/admin/types.ts:76`의 선택 선언은 구형 데이터 렌더에는 도움이 되지만 기록 없음 사유·실제 응답 분 표시의 완료를 보장하지 않는다. 항목별 위치·null 의미를 worker와 확정해야 하며 섹션 사유로 모든 항목을 대체할 수 있다고 가정하면 안 된다. |
| aux_facts·out_of_window_messages 모양 | 계약 구체화 요청에 동의. `apps/web/components/admin/types.ts:99`의 string 또는 `{text}`와 `:112`의 배열 구조는 아직 공용 계약에 구체적으로 정해지지 않았다. `report-view.tsx:278`은 임의 객체의 내용을 복원하지 못하므로 “모양이 달라도 방어됨”은 완전한 호환 보장이 아니다. 양측 공통 fixture를 확정해야 한다. |
| card_t_min 선택 필드 | 현 상태 수용 불가. `apps/web/components/admin/report-view.tsx:224`는 계약에 있는 context 시각도 활용하지 않는다. 필수 수정 4번처럼 기존 필드를 먼저 지원해야 한다. |
| AI 활용 category 도입 요청 | 오케스트레이터가 확정할 필요가 있다. `apps/web/components/admin/report-view.tsx:306`은 category가 없으면 전부 “기타”로 보여 주므로 계약상 예시만으로는 위임·맥락·검증 구분이 완성되지 않는다. category 열거값을 worker와 합의해 계약·fixture에 반영하고, 프론트의 임의 필드명을 worker가 따라야 한다고 단정하지 말아야 한다. |
| 미사용 idempotencyKey 제거 요청 | 낮은 우선순위 요청에 동의. `apps/web/components/admin/client.ts:68` 이하 실제 호출은 이 옵션을 사용하지 않아 현재 CORS·멱등 계약을 위반하지 않는다. `apps/web/lib/api.ts:31` 정리는 foundation 소유로 남기는 것이 맞다. |

`adjusted`로 null 조정과 무조정을 구별하는 표시(`report-view.tsx:166`), review·history와 담당자 합계, `by_element`, display_status 코드 7종 및 만료·취소 배지는 실제 관리자 API와 일치한다. 조정 메모 필수·memo_required·already_reviewed 안내, 최종 입력 잠금도 구현돼 있다. 합격·등급·순위 판정 UI는 없고 헤더의 합격·불합격 비판정 안내는 설계가 지정한 문구다. 상태·관찰·점수 표현을 위한 불필요한 라이브러리나 MVP 밖 기능 확장은 발견하지 못했다.

## 4) 다른 트랙 주의사항

- **worker·오케스트레이터** — `apps/web/components/admin/types.ts:76`, `:99`, `:115`: 기록 없음 사유·응답 분·보조 사실·창 밖 메시지·AI 분류 필드의 공통 JSON 예시를 확정해야 한다. 현재 main의 worker는 heartbeat 단계라 실제 리포트 생산자와 화면의 호환 완료를 주장할 수 없다. 공용 계약 수정은 오케스트레이터가 조율한다.
- **api-admin·worker** — `apps/web/components/admin/review.ts:13`: 화면은 GET 합성 응답의 rubric.review 존재를 제출 완료 신호로, stage=final을 최종 완료 신호로 사용한다. 제출 후 reviewer_total·review를 채우고 final의 reviewed_at·history를 유지하는 현재 API 규칙을 보존해야 한다.
- **foundation·오케스트레이터** — `apps/web/mocks/admin.test.ts:1`: 테스트 경로 소유권 정리가 필요하다. 미사용 `lib/api.ts` 옵션 제거는 별도 저우선순위 작업이며 web-admin이 직접 고칠 이유는 없다.
- **web-polish** — `apps/web/components/admin/report-view.tsx:5`: 기존 UI props만 소비하며 UI 내부 수정은 없다. 긴 산출물·메모·근거 인용, 좁은 화면은 polish 확인 대상으로 넘길 수 있지만 기능 누락·폴링 복구는 web-admin에서 먼저 해결해야 한다.
- **web-office·e2e-runner** — `apps/web/mocks/admin.ts:289`: 새 초대는 `mock-invite-N` 링크만 만들며 office mock과 세션 상태를 공유하지 않는다. 이번 관리자 mock 검증을 지원자 입장부터 reviewed까지의 통합 완료로 해석하지 말아야 한다.
