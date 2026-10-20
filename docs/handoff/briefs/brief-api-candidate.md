# 브리프: api-candidate 트랙 (W1)
역할: api-candidate 개발. 브랜치 track/api-candidate.
## 공통 규칙
- worktree는 현재 폴더, 커밋은 자기 브랜치에만. main 병합·push 금지.
- 읽을 것: AGENTS.md, docs/plan.md(자기 트랙 행·파일 소유권·병렬 작업 규칙), docs/dev-process.md, docs/common/contracts.md, docs/decisions.md 맨 아래 "foundation 리뷰 반영" 절.
- foundation 결과를 먼저 본다: 보고서 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report.md 와 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report-2.md 의 "다른 트랙에 알릴 것" 절(자기 트랙 항목).
- 소유권 밖 파일(foundation 소유 파일, contracts.md, 다른 트랙 폴더)은 수정하지 않는다. 바꿔야 하면 보고서에 "변경 요청"으로 적고 가능한 범위에서 계속 진행한다.
- TDD, happy path 중심. 완료 기준 한 줄당 테스트 하나. LLM 호출 없음(mock). DB는 공용 postgres(`make infra-up`은 main 저장소에서 이미 떠 있음, localhost:5432). api 테스트는 실행마다 임시 DB를 만드는 conftest를 그대로 쓴다. 통합 스택은 한 번에 하나이므로 `make up`·`app.run` 상시 기동 금지(필요하면 잠깐 띄우고 내린다).
- `infra/.env` 키 값은 출력·복사 금지.
- 커밋 메시지는 한국어 한 문장, 본문에 실행한 테스트 명령.
- 끝나면 완료 기준 각 줄을 직접 실행해 명령·결과, 수정 파일 목록, 남은 문제, 변경 요청, 다른 트랙에 알릴 것을 Markdown으로 저장한다. 마지막 응답은 그 파일 경로 한 줄만.
## 추가로 읽을 것
docs/common/data-model.md, docs/api/design.md(SessionService, 스케줄러 5초 루프 표, 제출 처리·estimate_reuse, 문서 저장, 완료 기준 api-candidate 줄), docs/common/scenario-model.md, docs/agent/design.md의 run_agent Lock 규칙, services/api/app/{main,auth,hub,queue,run}.py, app/services/*, app/agent/runner.py, tests/conftest.py, tests/fixtures/contracts/{state,ws_events,message}.json.
## 범위
`app/routers/candidate.py`(/s/{token} 진입·동의·대기·시작, /sessions/{id}/state·document PUT·submit·회사 문서 조회(doc_views 기록)·디브리핑 read token), `app/routers/ws.py`(/ws/sessions/{id}: 인증, message.send→accept_candidate_message→run_agent 백그라운드(lock_held=False), ack, 증분, 재연결 후 /state, session.replaced), `app/scheduler.py`(`async def run(ctx)`; events·runs·retry·releases·timeouts·outbox·ending 7종, run.py가 같은 루프에서 띄움), `app/services/reuse.py`(estimate_reuse 순수 함수, api/design.md 알고리즘)와 context의 reuse 훅 연결(decisions.md로 api-candidate 소유로 이관됨), tasks 행 생성(분업 확정 시). complete()는 세션 Lock을 잡으므로 Lock 밖에서 부른다.
## 완료 기준 (plan.md·api/design.md)
지원자 엔드포인트·WS(ack, 증분, 재연결 후 /state), 6분 테스트 세션(L=6)에서 이벤트가 ±10초 내 fired→done(FakeAgentRunner), 만료 시 큐 발행(FakePublisher), 재시작 후 fired 이벤트 재실행, 미발행 세션 재발행, estimate_reuse 예시 2개(verbatim 1.0, edited 0.5), submitted_at 이후 PUT 409 session_ending. `cd services/api && uv run pytest`, 루트 `make test`·`make lint` 통과.
## 보고서 경로
/private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/api-candidate-report.md
