# e2e

`run.py`가 `scenarios/e2e/*.yaml` 대본으로 실제 서비스를 상대해 세션을 끝까지 진행하고 `records/<일시>-<대본>/`에 기록을 남긴다. 형식과 단언은 `docs/common/testing.md`, step 키는 `scenarios/e2e/README.md`.

| 파일 | 역할 |
|---|---|
| `run.py` | 러너(CLI). 세션 조립 → 동의·시작 → WS·REST로 step 진행 → 제출·보고·종료 대기 → report_ready → 관리자 draft·검토(2a)·final·전체 기록 → 내부 API·DB 수집 → 단언 → 기록 |
| `client.py` | REST(공개·내부)·WS 클라이언트. 오간 것은 전부 transcript(토큰 값은 가림) |
| `asserts.py` | 단언 1~9. 함수 이름의 번호가 testing.md 번호 |
| `records.py` | 기록 폴더(transcript.jsonl·observations·report_draft/final·record·summary.md) |
| `faults.py` | 장애 주입 ASGI 층(api 내부 앱 앞). 실 스택에서는 프록시, 테스트에서는 미들웨어 |
| `stack.py` | 앱 프로세스 기동·재시작(`--manage-stack`)과 장애 주입 6종 |
| `auth.py` | 단언 8 인증 경계(`records/<일시>-auth/auth.md`) |
| `conftest.py`, `test_runner.py` | mock 단위 테스트: api 테스트 스택(격리 DB·실제 MCP 하위 프로세스·FakeLLM) 위에서 러너를 그대로 돌린다. 시계는 DB 시각 이동, 워커는 프로세스 안 SimWorker |

## 실행

```
make test-e2e                                       # mock 단위 테스트(인프라 postgres 필요). tests/eval 포함
uv run --project services/api python tests/e2e/run.py --script all_five   # 떠 있는 스택에 대본 하나
uv run --project services/api python tests/e2e/run.py --manage-stack --script restart   # 러너가 api·mcp·worker 기동
make e2e-concurrent   # 단언 7
make e2e-auth         # 단언 8
make e2e-faults       # 단언 6(러너가 앱을 띄움, rabbitmq 정지·재기동 포함)
make eval-live        # 근거 정확성 live 1회 → records/eval-live-<일시>.md
```

환경: `infra/.env.local` → `infra/.env`(환경변수가 우선). `E2E_PUBLIC_URL`(기본 localhost:8000), `E2E_INTERNAL_URL`(기본 localhost:8001), `INTERNAL_TOKEN`, `E2E_DATABASE_URL`(없으면 `DATABASE_URL`, 사용량·seq 측정용 읽기 전용 조회). api는 `ENABLE_TEST_API=1`·`AGENT_RUNNER=session`·`ASSISTANT_RUNNER=graph`로 떠 있어야 한다.

패키지 이름: 이 폴더는 `e2e`로 import한다(`tests/`를 경로에 넣음). 최상위 `tests`는 mock이 픽스처를 가져오는 api 테스트 패키지다.
