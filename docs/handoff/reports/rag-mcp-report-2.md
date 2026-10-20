# rag-mcp 수정 라운드 보고 (Codex 리뷰 반영)

브랜치 `track/rag-mcp`, 커밋 `2c5fd26` (이전 `b9b110f` 위). push·병합 안 함. worktree의 `REVIEW.md`는 삭제함(추적되지 않던 파일).

## 수정 목록

| 항목 | 변경 | 파일 |
|---|---|---|
| P1 전문 버전 고정 | `get_document`가 더 이상 파일을 읽지 않음. 공개를 확인한 뒤 내부 GET /documents가 준 `catalog_version`의 `doc_chunks`를 chunk_no 순으로 이어 붙여 본문을 만듦(400자 슬라이스라 strip한 원문이 그대로 복원됨). 해당 버전 청크가 없으면 `upstream_unavailable`(retryable), DB 오류도 같음. title은 API 응답 값. API·계약 변경 없음 | `rag_mcp/tools.py`, `rag_mcp/store.py`(`document_chunks` 추가) |
| 쓰이지 않게 된 코드 정리 | `documents.read_document` 삭제(테스트는 `load_documents`로 원문을 얻음) | `rag_mcp/documents.py`, `tests/test_tools.py` |
| 재색인 테스트에 단언 1개 추가 | V1 색인 → 파일을 V2로 바꾸고 재색인 → API가 V1을 주면 `get_document`가 V1 본문을 돌려줌 | `tests/test_tools.py::test_reindex_idempotent_and_keeps_previous_version` |
| 공개 문서 전문 단언 | 기대값을 strip한 원문으로 바꿈(청크 복원 결과) | `tests/test_tools.py::test_unreleased_documents_blocked` |
| API mock과 DB 분리 | `api` 픽스처는 DB 없이 MockTransport와 기본 설정만 씀. `db` 픽스처가 `api.configure(settings)`로 임시 DB 설정을 넣음(mock 전송은 유지) | `tests/conftest.py` |
| invalid_input 테스트 | `search_documents(top_k=0)` → `invalid_input`, api 호출 없음 | `tests/test_tools.py::test_invalid_input_returned_as_error_result` |
| indexed 의미 명시 | docstring과 README에 "색인된 청크 수"라고 적음. get_document 설명에 버전 고정과 upstream_unavailable 추가 | `rag_mcp/tools.py`, `README.md` |

## 검증 명령·결과

| 명령 | 결과 |
|---|---|
| `cd services/rag-mcp && uv run pytest -q` | 10 passed, 1 deselected |
| `DATABASE_URL=postgresql://nobody@127.0.0.1:1/none uv run pytest -q -k "error_codes or connection_failure or 5xx or invalid_input or listed"` | 5 passed. 오류 매핑·재시도·잘못된 입력·도구 목록 테스트가 DB 없이 통과함 |
| `make test` (루트) | 통과 (api 5, business-mcp 11, rag-mcp 10, worker 1, web 1) |
| `make lint` (루트) | 통과 (ruff check·format, eslint·prettier) |
| `psql ... "select count(*) from pg_database where datname like 'rag_test_%'"` | 0. 임시 DB가 남지 않음 |

live 테스트와 docker build는 다시 돌리지 않음. 변경이 도구 로직과 테스트뿐이고, 의존성·Dockerfile·임베더는 그대로임.

## 하지 않은 것 (브리프대로)
- compose·env 수정. hfcache 볼륨을 `/models`로 맞추는 일은 병합 때 오케스트레이터가 함.
- 3GB 메모리 실측. M1 연결 확인 때 함.

## 다른 트랙에 알릴 것 (변경분)
- agent-min·agent-assistant: `get_document`도 해당 버전 색인이 없으면 `upstream_unavailable`을 돌려줌. 재색인(`make seed`) 전에는 검색과 전문 조회가 둘 다 이 오류를 냄. 폴백 대상으로 처리하면 됨.
- 오케스트레이터: 계약 `reindex_documents`의 `indexed`를 "색인된 청크 수"로 적어 주면 구현과 맞음.
