# rag-mcp

미션 회사 문서(`scenarios/missions/<id>/documents/*.md`) 검색·조회·색인 MCP 서버. Streamable HTTP `:9102/mcp`, 헬스 `/health`.
계약: `docs/common/contracts.md`, 설계: `docs/mcp/design.md`.

## 도구

| 도구 | 하는 일 |
|---|---|
| search_documents | 내부 `GET /internal/sessions/{id}/documents`의 catalog_version·공개 목록으로 거른 청크를 코사인 유사도 상위 top_k로. 해당 버전 색인이 없으면 `upstream_unavailable` |
| get_document | 공개된 문서 전문. 세션 catalog_version의 청크를 chunk_no 순으로 이어 붙여 복원(채용 건 고정). 공개 전 `not_released`, 해당 버전 색인이 없으면 `upstream_unavailable` |
| list_documents | 문서 목록과 공개 여부 |
| reindex_documents | `{mission_id?}`(기본 planning). 미션 폴더 해시(catalog_version)로 400자 청크 색인. 같은 버전은 덮어쓰고 다른 버전 청크는 유지. `{indexed(색인된 청크 수), model, dim, catalog_version}` |

api 오류 매핑·재시도는 business-mcp와 같다(`rag_mcp/client.py` 표).

## 실행

```
uv run python -m rag_mcp          # 시작 시 BGE-M3를 1회 로드(첫 실행은 약 2.3GB 다운로드, HF_HOME 캐시)
uv run pytest                     # Fake 임베딩 + 임시 DB(rag_test_*). make infra-up의 postgres 필요
uv run pytest -m live             # 실제 BGE-M3(CPU)
```

환경: `DATABASE_URL`, `API_INTERNAL_URL`, `INTERNAL_TOKEN`, `SCENARIOS_DIR`(기본 /scenarios, 없으면 저장소 scenarios/), `EMBEDDING_MODEL`(기본 BAAI/bge-m3), `HF_HOME`(컨테이너 기본 /models).
