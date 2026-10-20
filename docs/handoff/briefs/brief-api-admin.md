# 브리프: api-admin 트랙 (W1)
역할: api-admin 개발. 브랜치 track/api-admin.
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
docs/common/data-model.md, docs/api/design.md(인증·SessionService·문서 저장·완료 기준 api-admin 줄), docs/common/rubric.md(리뷰 조정 본문), docs/common/scenario-model.md, services/api/app/{main,auth,config}.py, app/services/*, tests/conftest.py.
## 범위
`app/routers/admin.py`, `app/routers/internal.py`와 그 테스트. contracts.md의 /admin/* 전부(가입·로그인, 카탈로그 조회·평가표 미리보기, 채용 건 생성·조회, 초대 발행·취소, 지원자 목록(display_status·score.by_element), 세션 취소, 리포트 조회·리뷰(`{adjustments, memo}`, memo_required·already_reviewed), 산출물·조정 병합)과 /internal/* 전부(세션 컨텍스트·문서 목록, 메시지 저장, 문서 파트 쓰기, 관찰 기록, 분류 PUT, 리포트 draft/final 저장·content_hash, 어시스턴트 호출 기록 등 계약에 있는 것). 라우터 파일에 `router = APIRouter()`만 두면 main.py가 자동 포함한다(admin은 8000, internal은 8001).
## 완료 기준 (plan.md·api/design.md)
계약 예시대로 응답, 기업 간 격리(다른 회사 채용 건 404), elements 검증(400 invalid_elements), 권한 밖 변경 403, 승인 전 final 저장 409, memo_required·already_reviewed, 내부 저장 멱등(run_id·seq / run_id / element·window_start). `cd services/api && uv run pytest`, 루트 `make test`·`make lint` 통과.
## 보고서 경로
/private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/api-admin-report.md
