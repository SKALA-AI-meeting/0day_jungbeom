# scripts

| 파일 | 역할 | 담당 |
|---|---|---|
| `worktree.sh` | 트랙별 worktree 생성·제거(`sh scripts/worktree.sh --remove <이름>`) | 오케스트레이터 |
| `seed.py` | ① 미션 자료 원문을 현재 `catalog_version`으로 `materials` 테이블에 시드(이전 버전 유지) ② 관리자 가입·채용 건 생성(`/admin/positions`, 요소 선택 없음, `--minutes 60∣15`) ③ rag-mcp `reindex_materials`로 같은 버전 청크 색인. `make seed`(= `uv run --project services/api python scripts/seed.py`). `--skip-position`·`--skip-reindex`로 단계를 건너뛴다 | be-foundation |
| `make_session.py` | `--minutes 15`로 테스트 세션 즉시 생성(내부 테스트 API) | e2e |

서비스 이름: api(8000·내부 8001), debate-mcp(9101), rag-mcp(9102), assessment-mcp(9103), report-worker, web(3000). 자료 원문은 api가 `materials` 테이블에서 읽고 rag-mcp는 `material_chunks`만 쓴다(`docs/common/data-model.md`).
