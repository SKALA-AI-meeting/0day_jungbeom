# rag-mcp 트랙 (W2) 완료 보고

브랜치 `track/rag-mcp`, 커밋 `b9b110f` (push·병합 안 함).

## 완료 기준별 명령·결과

| 완료 기준 | 명령 | 결과 |
|---|---|---|
| 도구 목록·설명 | fastmcp `Client(mcp).list_tools()` 스크립트(아래 출력), `test_tools_listed_with_descriptions` | 도구 4개, 모두 설명과 인자 설명 있음 |
| 검색 응답 | `test_search_returns_matching_chunk_first` | Fake 임베딩으로 재색인 뒤 metrics 첫 청크와 같은 쿼리 → 1위 metrics, score > 0.99, 결과 키 {doc_id,title,chunk,score}, 내부 GET /internal/sessions/s1/documents에 X-Internal-Token 전달 |
| 미공개 문서 차단 | `test_unreleased_documents_blocked` | 미공개 interview_summary 청크와 똑같은 쿼리도 결과는 공개 문서(metrics)만. get_document(interview_summary) → `not_released`, 공개 문서는 전문, list_documents에 released=false |
| 색인 없는 버전 | `test_search_without_index_for_version_is_upstream_unavailable` | `upstream_unavailable`, retryable=true |
| 재색인 | `test_reindex_idempotent_and_keeps_previous_version` | 같은 버전 2회 결과·행 수 동일. 임시 scenarios 복사본의 문서를 바꾸면 새 버전 청크가 추가되고 이전 버전 청크 수는 그대로 |
| 오류 매핑·재시도 | `test_error_codes_mapped`, `test_connection_failure_retried_once_then_upstream_unavailable`, `test_5xx_retry_recovers` | 401·403→forbidden, 404→not_found, 410→conflict, 4xx 재시도 없음. 연결 실패 2회 호출 후 upstream_unavailable. 503 다음 200이면 성공 (423→not_released 매핑은 business-mcp 표 그대로) |
| 단위 테스트 | `cd services/rag-mcp && uv run pytest -q` | 9 passed, 1 deselected (2.1s) |
| 실제 모델 | `uv run pytest -q -m live` | 1 passed (72s, 첫 실행이라 BGE-M3 다운로드 포함). 1024차원, 정규화됨, 관련 문장 유사도가 더 높음 |
| 루트 검사 | `make test`, `make lint` | 둘 다 통과 (api 5, business-mcp 11, rag-mcp 9, worker 1, web 1) |
| Docker | `docker build -t dayzero-rag-mcp:track services/rag-mcp` | 성공, 75초. 이미지 3.4GB, 안에 torch 2.14.1+cpu, sentence-transformers 6.1.0, CUDA 없음 |
| 테스트 DB 정리 | `psql ... "select datname from pg_database where datname like 'rag_test_%'"` | 0행. 공용 DB의 doc_chunks도 0행(건드리지 않음) |

도구 목록 출력:
```
- search_documents: 이 세션에 공개된 회사 문서에서 질문과 가까운 문단을 찾는다.
  args: {"query": "찾을 내용(자연어 질문이나 키워드)", "session_id": "세션 ID. ...", "top_k": "돌려줄 청크 수(기본 3)"}
- get_document: 공개된 회사 문서 하나의 전문을 읽는다. 결과는 {doc_id, title, content}.
  args: {"doc_id": "문서 ID(예: metrics, policy)", "session_id": "..."}
- list_documents: 이 세션의 회사 문서 목록과 공개 여부를 조회한다. 결과는 [{doc_id, title, released}].
  args: {"session_id": "..."}
- reindex_documents: 현재 카탈로그 버전으로 고정 회사 문서를 400자 청크로 나눠 다시 색인한다(관리용).
  args: {}
```

## 수정 파일 (모두 `services/rag-mcp/`)
- 새 파일: `rag_mcp/{config,client,embedder,documents,store,tools}.py`, `tests/{conftest,test_tools,test_live}.py`
- 수정: `rag_mcp/server.py`(시작 시 모델 1회 로드, invalid_input 미들웨어), `pyproject.toml`(sentence-transformers·torch 추가, linux는 pytorch CPU 인덱스, pytest 이벤트 루프 범위를 api처럼 session으로, live 마커 설명), `uv.lock`, `Dockerfile`(`ENV HF_HOME=/models`), `README.md`

## 설계 메모
- `client.py`는 business-mcp 구조를 그대로 따름(같은 오류 표, 타임아웃 10초, 5xx·연결 실패 1회 재시도).
- 임베딩은 `Embedder` 인터페이스 뒤에 있음. 서버 lifespan에서 BGE-M3를 한 번 로드하고, 로드가 끝나야 `/health`가 응답함. 테스트는 `set_embedder(FakeEmbedder())`로 바꿔 씀.
- 색인: 같은 버전은 트랜잭션으로 지우고 다시 넣음(멱등). 다른 버전 청크는 그대로 둠. 청크는 문서 본문을 앞에서부터 400자씩 자른 것이고, title은 각 md의 첫 `#` 줄.
- 테스트 DB: api conftest와 같은 방식. 실행마다 `rag_test_<랜덤>`을 만들어 schema.sql을 적용하고 끝나면 `DROP ... WITH (FORCE)`.
- DB 연결·쿼리 오류는 `upstream_unavailable`(retryable)로 돌려줌(테스트 없음, 완료 기준 밖).

## 남은 문제
- `reindex_documents`의 `indexed`는 **청크 수**로 정함. 계약의 "고정 문서 5개를 색인"을 문서 수로 읽을 수도 있음. 지금 문서는 각각 400자 안팎이라 청크 수가 문서 수와 거의 같음. 문서 수가 맞다면 알려 주면 바로 고침.
- `get_document` 본문은 현재 `scenarios/documents` 파일에서 읽음. 이전 catalog_version에 고정된 채용 건이 문서가 바뀐 뒤 조회하면 현재 본문을 받게 됨. 검색은 버전별 청크라 문제없음.
- 이미지 3.4GB(CPU torch 포함). 모델 가중치(약 2.3GB)는 이미지 밖 HF_HOME 볼륨에 받음. 그래서 첫 기동 때 다운로드 시간이 걸리고, healthcheck가 60회 × 10초 안에 끝나야 함.
- 실제 서버 + api 연결 확인은 하지 않음(통합 스택 하나 원칙). M1 끝 agent-min 연결 테스트에서 확인 필요.

## 변경 요청 (오케스트레이터)
1. `infra/docker-compose.yml` rag-mcp 볼륨: `hfcache:/root/.cache/huggingface` → `hfcache:/models`. 이미지가 `HF_HOME=/models`를 쓰므로, 바꾸지 않으면 재기동할 때마다 모델을 다시 받음.
2. (선택) `infra/.env.example`에 `HF_HOME=/models` 주석 한 줄. 이미지 기본값이라 필수는 아님.
3. 지금 떠 있는 `infra-rag-mcp-1`은 골격 이미지임. 병합 뒤 `make infra-up`을 `--build`로 다시 띄우고 `make seed`로 재색인해야 검색이 동작함(색인 없으면 search가 upstream_unavailable).

## 다른 트랙에 알릴 것
- agent-min·agent-assistant: 응답은 `{ok, data}`/`{ok:false, error}`. search 결과 `[{doc_id,title,chunk,score}]`(score는 코사인 유사도, 소수 4자리). `top_k`는 1~10, 기본 3. 해당 버전 색인이 없으면 `upstream_unavailable`.
- api-admin: rag-mcp는 내부 `GET /internal/sessions/{id}/documents` 응답 `{catalog_version, documents:[{doc_id,title,released}]}`에만 의존함. title은 이 응답의 값을 그대로 씀.
- foundation/seed: `make seed`의 reindex 결과 `indexed`는 청크 수임.
