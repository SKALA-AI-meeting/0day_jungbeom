# stage-e2e 보고 (S3)

기준: origin/track/debate ba7b11b 위 track/stage-e2e. 결과: **`make e2e-stages` 7개 spec 9개 테스트 통과**(LLM_FAKE=1 스택, 연속 3회 통과, 약 45초). `make test-e2e`·`make lint`도 통과.

## spec별 결과

`tests/e2e/records/stages/summary.md`에 표로 있다. entry·keyword·problem·solution(합의 채움·`silent`·`solo_confirm`)·proposal·debrief·admin-report 모두 정상 1개 + 계약이 요구하는 것만 확인한다. 시드는 내부 테스트 API(`POST /internal/test/sessions`), 시간은 `advance`(`card:<id>`·`deadline`·`idle`)로 당긴다.

## 기록

- 스크린샷(커밋): `tests/e2e/records/stages/<단계>/NN-이름.png`(핵심 시점), 요약 `tests/e2e/records/stages/summary.md`
- 영상(webm)·trace·HTML 리포트(git 무시): `tests/e2e/records/stages/.artifacts/<테스트>/`, `tests/e2e/records/stages/html-report/` — `cd apps/web && pnpm exec playwright show-report ../../tests/e2e/records/stages/html-report`

## 만든 것

`apps/web/playwright.config.ts`(video·trace on, 1280x800, workers 1), `apps/web/e2e/stages/*.spec.ts` + `helpers.ts`(시드·advance·내부 조회·스크린샷), `apps/web/package.json`의 `@playwright/test` 1.63.0(+lockfile), Makefile `e2e-stages`·`e2e-stack-up`·`e2e-stack-seed`·`e2e-stack-down`, `infra/docker-compose.e2e.yml`(별도 프로젝트용 override), `.gitignore`(영상·trace·리포트).

## 스택 기동 방법 (다른 스택 건드리지 않음)

1. `infra/.env.e2e`(git 무시)를 `infra/.env.example`에서 복사해 `JWT_SECRET`·`INTERNAL_TOKEN`·`ASSESSMENT_MCP_TOKEN`을 임의 값으로, `LLM_FAKE=1`·`ENABLE_TEST_API=1`·`AGENT_RUNNER=session`·`WEB_ORIGIN=http://localhost:3100`·`NEXT_PUBLIC_*`=8100으로 둔다(OPENAI 키는 비움).
2. `make e2e-stack-up` — `docker compose -p dayzero-debate`, web 3100·api 8100·내부 8101(127.0.0.1)·rabbitmq UI 15674·postgres 5442·rag 9112. 모델 캐시는 기존 `infra_hfcache` 볼륨을 재사용한다.
3. `make e2e-stack-seed`(자료 원문·재색인) → `make e2e-stages [STAGE=<spec 이름>]`. 첫 실행 전 `cd apps/web && pnpm exec playwright install chromium`.
4. 끝나면 `make e2e-stack-down`. `dayzero-submission-*`·`infra-*` 컨테이너는 만지지 않았다.

## 발견 버그

`docs/handoff/reports/stage-e2e-bugs.md`: 하 1건(관리자 리포트를 draft 생성 전에 열면 "report not found", 자동 재시도 없음). 나머지는 테스트 주의점이다.

## 한계

- `LLM=live`는 돌리지 않았다. 문장 단언(예: 기준안 고정 입장 문장, 합의 흐름)은 결정적 LLM 모드 기준이라 실제 모델에서는 달라질 수 있다.
- 영상·trace가 spec 단위 폴더(`.artifacts/<테스트 이름>/`)에 있고 단계 폴더로 복사하지는 않는다.
