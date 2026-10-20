# MCP 설계

둘 다 Python FastMCP, Streamable HTTP. 도구 목록·입출력·오류 형식·허용 목록은 `common/contracts.md`가 정본이다.

## business-mcp (`services/business-mcp/`)

- api 내부 앱(`http://api:8001/internal/*`)을 httpx로 호출한다. DB 접근 없음. 권한·상태 판단은 하지 않고 api의 403·409를 코드로 전달한다(`forbidden`, `conflict`).
- 각 도구는 Pydantic 입력 모델, docstring 설명, `{ok, data}` 반환. api 4xx→코드 매핑(404 not_found, 403 forbidden, 409 conflict, 422 invalid_input), 5xx·연결 실패→`upstream_unavailable`(retryable, 1회 재시도). 타임아웃 10초.
- `post_message`, `write_document_part`, `record_observation`은 run_id·seq를 그대로 전달해 멱등을 api에 맡긴다.

## rag-mcp (`services/rag-mcp/`)

- 시드 시 `scenarios/documents/*.md`를 400자 청크로 나눠 BGE-M3(1024차원)로 임베딩해 `doc_chunks`에 저장. 키는 (catalog_version, doc_id, chunk_no)이고 catalog_version은 api와 같은 카탈로그 파일 해시다. `reindex_documents`는 현재 버전을 색인하고 이전 버전 청크는 남겨 진행 중 채용 건이 자기 버전으로 검색하게 한다. 에이전트에는 노출하지 않는다.
- `search_documents`: 내부 `GET /internal/sessions/{id}/documents`로 `catalog_version`과 공개 목록을 받아 같은 버전·공개된 doc_id로 필터한 뒤 코사인 유사도 상위 k. 해당 버전 청크가 없으면 `upstream_unavailable`(재색인 필요). 결과에 doc_id·title·chunk·score.
- 모델 로드는 시작 시 1회. 컨테이너 메모리 3GB.

## 완료 기준
- MCP Inspector에서 도구 목록·설명 확인
- 연결 테스트: 그래프→MCP→api 저장→WS 노출 1건, 미공개 문서 차단, 권한 밖 변경 403→forbidden, api 중단 시 upstream_unavailable, 잘못된 입력 invalid_input
- 같은 run_id·seq 재호출이 중복 메시지를 만들지 않음
