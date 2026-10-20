# 브리프: rag-mcp 트랙 (W2)
역할: rag-mcp 개발. worktree는 현재 폴더, 브랜치 track/rag-mcp. 커밋은 자기 브랜치에만, main 병합·push 금지.
## 공통 규칙
- 읽을 것: AGENTS.md, docs/plan.md(자기 트랙 행·파일 소유권·병렬 규칙), docs/dev-process.md, docs/common/contracts.md(rag-mcp 도구 4개, 공통 응답 형식, 내부 GET /internal/sessions/{id}/documents), docs/mcp/design.md(rag-mcp 절·완료 기준), docs/common/harness.md, docs/decisions.md 맨 아래 절, infra/db/schema.sql의 doc_chunks, scenarios/version.py, scenarios/documents/*.md, services/rag-mcp/ 현재 골격, 그리고 이미 병합된 services/business-mcp/(client.py의 오류 매핑·재시도 구조를 그대로 따라 한다. 401→forbidden, 410→conflict, 423→not_released, 5xx·연결 실패→upstream_unavailable 1회 재시도, 타임아웃 10초).
- 소유권: `services/rag-mcp/` 전체(pyproject·lock 포함, 임베딩 의존성 추가 허용). 그 밖(compose, api, contracts.md)은 수정하지 않고 "변경 요청"으로 보고.
- TDD, happy path 중심, LLM 없음. **임베딩 모델은 테스트에서 Fake**(1024차원 결정적 벡터)로 두고, 실제 BGE-M3(sentence-transformers, CPU)는 Embedder 인터페이스 뒤에 두어 시작 시 1회 지연 로드. 실제 모델 테스트는 `@pytest.mark.live`. DB는 공용 postgres(localhost:5432, pgvector 설치됨, `make infra-up`은 main에서 이미 떠 있음). 테스트는 임시 DB 또는 임시 catalog_version 값을 써서 다른 worktree와 겹치지 않게 하고 끝나면 지운다.
- 통합 스택 하나 원칙: `make up`·api 상시 기동 금지. 내부 API는 아직 없다고 보고 httpx MockTransport로 mock.
- `infra/.env` 키 값 출력·복사 금지. 커밋 메시지는 한국어 한 문장 + 본문에 테스트 명령.
## 범위
도구 4개: search_documents(내부 GET /documents로 catalog_version·공개 목록을 받아 같은 버전·공개 doc_id만 필터, 코사인 상위 top_k, 결과 {doc_id,title,chunk,score}; 해당 버전 청크 없으면 upstream_unavailable), get_document(공개 전 not_released, 본문은 scenarios/documents에서), list_documents, reindex_documents(현재 catalog_version으로 documents/*.md를 400자 청크로 색인, 다른 버전 청크는 유지, {indexed, model, dim, catalog_version}). SCENARIOS_DIR은 api config와 같은 규칙(기본 /scenarios, 없으면 저장소 scenarios/). 문서 title은 각 md의 첫 제목 줄.
## 완료 기준 (docs/mcp/design.md)
도구 목록·설명 확인(fastmcp 클라이언트로 명령·출력 기록), 검색 응답(Fake 임베딩으로 쿼리와 같은 청크가 1위), 미공개 문서 차단(search에서 제외·get_document not_released), 재색인(같은 버전 재실행 멱등, 버전 바뀌면 추가되고 이전 청크 유지), 오류 매핑·재시도. `uv run pytest`, 루트 `make test`·`make lint` 통과. Dockerfile이 실제 모델 의존성을 포함해 빌드되는지 `docker build` 한 번(시간 걸리면 보고에 소요 시간 기록). HF 모델 캐시 경로는 env `HF_HOME`(기본 /models)로 두고 compose 볼륨은 변경 요청으로 올린다.
## 보고
완료 기준 각 줄의 명령·결과, 수정 파일, 남은 문제, 변경 요청, 다른 트랙에 알릴 것을 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/rag-mcp-report.md 에 저장. 마지막 응답은 경로 한 줄.
