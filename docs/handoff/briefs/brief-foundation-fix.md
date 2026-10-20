# foundation 수정 라운드 (Codex 리뷰 반영)

리뷰 원문: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/review-foundation-raw.txt (섹션 1~4). 아래는 오케스트레이터 결정이다. 같은 브랜치에 커밋하고, 끝나면 보고서를 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report-2.md 에 저장한다(완료 기준 3·5·6 재실행 결과, 수정 목록). 마지막 응답은 경로 한 줄.

## 반드시 고칠 것 (리뷰 1절)
1. 종료 run 실패 처리: `complete()`에서 end run의 `RunResult.ok`를 확인한다. 결정: ok=False여도 세션은 completed로 진행하고 리포트를 발행한다(지원자 작업물을 잃지 않기 위해). 대신 agent_runs를 failed로 남기고 로그를 찍는다. 멱등 테스트에 이 경로 한 줄 추가.
2. 동시 제출 직렬화: `complete()` 전체(상태 재검증 → end run → reuse → completed 커밋 → 발행)를 세션 Lock 안에서 수행한다. Lock 안에서 상태를 다시 읽어 in_progress가 아니면 아무것도 하지 않는다. `run_agent`가 Lock을 다시 잡아 교착되지 않도록 "이미 잡은 Lock 안에서 실행"하는 경로를 둔다(예: run_agent에 lock 보유 여부 인자, 또는 Lock 없이 실행하는 내부 함수). 다른 트랙이 쓸 호출 규칙을 docstring에 적는다.
3. `start()`에서 `invites.expires_at` 만료 검사(consent와 같은 410 코드).
4. CORS: 공개 앱에 CORSMiddleware. 허용 origin은 설정 `WEB_ORIGIN`(기본 http://localhost:3000, 쉼표 구분 복수 허용), 메서드 전부, 헤더 Authorization·Content-Type·Idempotency-Key. `infra/.env.example`에 추가. 내부 앱(8001)에는 넣지 않는다.
5. 큐 발행: 채널 `on_return_raises=True`, 발행 반환값 확인. 라우팅 실패면 예외 → enqueued_at 미기록. FakePublisher 테스트로 실패 경로 한 줄.

## 같이 고칠 것 (리뷰 2절, 오케스트레이터 결정)
6. `scripts/seed.py`: MCP 응답의 `{ok:false, error}`도 실패로 처리.
7. web mocks 소유권 분리: `mocks/index.ts`는 `mocks/admin.ts`(web-admin 소유)·`mocks/office.ts`(web-office 소유)의 ROUTES를 합치기만 한다. 두 파일은 빈 ROUTES로 만들어 둔다. fixture도 `mocks/fixtures/admin/`, `mocks/fixtures/office/`로 나누고 기존 2개(report, state)는 각각 admin·office에 둔다.
8. 세션 시작 시 `document_states` 파트 행(revision 0, 빈 본문)을 SessionService.start()가 만든다. 파트 수는 시나리오 parts에서. tasks 행은 분업 확정 때 api-candidate가 만든다(지금 안 함). 조립·전이 테스트의 기대값만 갱신.
9. `tests/fixtures/contracts/state.json`·`mocks/fixtures/.../state.json`의 "..." 시각을 실제 ISO 시각으로. report.json은 그대로(화면 트랙이 채움).
10. `config.py`: `SCENARIOS_DIR`가 기본값(/scenarios)이고 없을 때만 저장소 `scenarios/`로 대체한다. 사용자가 지정한 경로가 없으면 오류.

## 문서 동기화 (이번만 foundation이 수정 허용)
- `docs/common/contracts.md`: WS 프레임 봉투 `{"type", "payload"}` 예시 1개와 `session.replaced` 뒤 close code 4000; 큐 본문 `attempt`는 1부터(총 3회); 시작 시 만료 검사; CORS 한 줄.
- `docs/common/data-model.md`: SessionService 목록에 `cancel` 추가; 세션 실패 시 디브리핑은 "중단 안내만"으로 PRD 7.4·contracts와 맞춤; 시작 시 파트 행 생성.
- `docs/common/scenario-model.md`: 시점은 0.01분 단위 반올림; interview_expected_time은 실제 책임감 카드 시각(미선택이면 "시작 시 공유됨").
- `docs/agent/design.md`: AgentRunner `RunResult.usage` 추가, 종료 run 실패 시 처리(1번), run_agent Lock 규칙(2번).
- `docs/plan.md` 파일 소유권: foundation 행에 `services/api/tests/conftest.py` 추가; web-admin 행에 `mocks/admin.ts`·`mocks/fixtures/admin/`, web-office 행에 `mocks/office.ts`·`mocks/fixtures/office/`; api-candidate 행에 `app/services/reuse.py`(estimate_reuse)와 context의 reuse 훅 연결.
- `docs/decisions.md`: 2026-10-20 "foundation 리뷰" 절에 위 결정(1·2·7·8·10, 소유권 예외 3건 수용: catalog.yaml 인용, ruff.toml md 제외, web README, 확인 후 큐 유실 복구는 MVP 제외) 기록.
- `scenarios/catalog.yaml` 67행 근처 주석 "L×5/12"를 "책임감 카드 시각"으로 고친다(값 변경 없음).

## 하지 않을 것
확인 후 큐 유실 복구, 실제 runner 연결, reuse 구현, 임베딩 의존성, web build args. 키 값 출력 금지.
