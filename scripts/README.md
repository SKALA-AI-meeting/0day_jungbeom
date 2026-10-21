# scripts

| 파일 | 역할 | 담당 |
|---|---|---|
| `worktree.sh` | 트랙별 worktree 생성·제거(`sh scripts/worktree.sh --remove <이름>`) | 오케스트레이터 |
| `seed.py` | ① 미션 자료 원문을 현재 `catalog_version`으로 `materials` 테이블에 시드(이전 버전 유지) ② 관리자 가입·채용 건 생성(`/admin/positions`, 요소 선택 없음, `--minutes 60∣15`) ③ rag-mcp `reindex_materials`로 같은 버전 청크 색인. `make seed`(= `uv run --project services/api python scripts/seed.py`). `--skip-position`·`--skip-reindex`로 단계를 건너뛴다 | be-foundation |
| `make_session.py` | 단계 시드 세션 즉시 생성(`--start-at entry∣keyword∣problem∣solution∣proposal∣ended`, `--minutes 15∣60`, `--stage`, `--llm fake∣live`). `make stage STAGE=<단계> [MIN=15] [LLM=fake∣live]`. 시드 재생은 card_due를 거치지 않아 직후 `session_cards.locked_option_id`·`card_progress`가 비어 있고, problem 시드의 기준안은 첫 card_due 처리 때 잠긴다. solution·proposal·ended 시드는 card_due를 거치지 않아 ended 리포트·디브리핑에 문제 단계 카드 장면이 없다 | stage-kit |
| `stage_advance.py` | 세션 시간 당기기. `make stage-advance SID=<id> TO=deadline∣idle∣card:<id>∣<초>` | stage-kit |
| `save_eval_fixture.py` | 실 스택에서 끝난 세션의 SessionRecord(assessment-mcp `get_session_record`)를 `tests/eval/fixtures/sessions/<session_id>.json`으로 저장 | e2e |

서비스 이름: api(8000·내부 8001), debate-mcp(9101), rag-mcp(9102), assessment-mcp(9103), report-worker, web(3000). 자료 원문은 api가 `materials` 테이블에서 읽고 rag-mcp는 `material_chunks`만 쓴다(`docs/architecture/data-model.md`).
