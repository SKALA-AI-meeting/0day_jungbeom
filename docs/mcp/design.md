# MCP 설계

둘 다 Python FastMCP, Streamable HTTP. 도구 목록·입출력·오류 형식은 `common/contracts.md`가 정본이다.

## business-mcp (`services/business-mcp/`)

- api `/internal/*`을 httpx로 호출한다. DB 접근 없음.
- 각 도구는 Pydantic 입력 모델, docstring 설명, `{ok, data}` 반환. api 4xx는 코드로 매핑(404→not_found, 403→forbidden, 422→invalid_input), 5xx·연결 실패→`upstream_unavailable`(retryable). 타임아웃 10초.
- `update_task`, `write_document_part`는 호출 전 `get_session`의 division으로 동료 담당인지 확인한다.

## rag-mcp (`services/rag-mcp/`)

- 시드 시 `scenarios/documents/*.md`를 400자 청크로 나눠 BGE-M3(1024차원)로 임베딩해 `doc_chunks`에 저장. `index_documents`가 같은 일을 한다.
- `search_documents`는 session_id로 api `/internal/sessions/{id}`… 대신 `document_releases`를 직접 읽지 않는다. api `GET /sessions/{id}/documents` 내부 호출로 공개 목록을 받아 필터한다(DB 읽기도 api 경유, 벡터 테이블만 직접).
- 코사인 유사도 상위 k. 결과에 doc_id·title·chunk·score.
- 모델 로드는 프로세스 시작 시 1회. 컨테이너 메모리 2GB 이상.

## 완료 기준
- MCP Inspector에서 도구 목록·설명 확인
- 없는 세션, 권한 밖 변경, 공개 전 문서에 대한 오류 코드 테스트
- api 중단 시 `upstream_unavailable` 반환
