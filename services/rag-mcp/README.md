# rag-mcp

키워드별 참고 자료(`scenarios/missions/<id>/keywords.yaml`의 `materials`, 본문 `materials/<keyword>/*.md`) 검색·조회·색인 MCP 서버. Streamable HTTP `:9102/mcp`, 헬스 `/health`. 도구는 모두 `async def`.
계약: `docs/contracts/mcp.md` "rag-mcp", 설계: `docs/services/mcp.md`.

## 도구

| 도구 | 하는 일 |
|---|---|
| search_materials | 내부 `GET /internal/sessions/{id}/materials`의 잠금·확정 키워드·catalog_version으로 거른 `material_chunks`를 코사인 유사도 상위 top_k로. 키워드 확정 전이면 `not_released`, 해당 버전 색인이 없으면 `upstream_unavailable` |
| get_material | 열린 자료 전문. 내부 `GET /internal/sessions/{id}/materials/{material_id}`(채용 건 catalog_version의 `materials` 원문)를 그대로 전달. 열리지 않은 자료는 `not_released` |
| reindex_materials | `{mission_id?}`(기본 debate). 미션 폴더 해시(catalog_version)로 400자 청크를 키워드 키와 함께 색인. 같은 버전은 덮어쓰고 다른 버전 청크는 유지. `{indexed, model, dim, catalog_version}`. 에이전트에 노출하지 않음 |

원문 `materials` 행은 `scripts/seed.py`가 같은 catalog_version으로 시드한다. api 오류 매핑·재시도는 `rag_mcp/client.py` 표.

## 실행

```
uv run python -m rag_mcp          # 시작 시 BGE-M3를 1회 로드(첫 실행은 약 2.3GB 다운로드, HF_HOME 캐시)
uv run pytest                     # Fake 임베딩 + 임시 DB(rag_test_*). make infra-up의 postgres 필요(없으면 DB 테스트 건너뜀)
uv run pytest -m live             # 실제 BGE-M3(CPU)
```

환경: `DATABASE_URL`, `API_INTERNAL_URL`, `INTERNAL_TOKEN`, `SCENARIOS_DIR`(기본 /scenarios, 없으면 저장소 scenarios/), `EMBEDDING_MODEL`(기본 BAAI/bge-m3), `HF_HOME`(컨테이너 기본 /models), 테스트용 `TEST_DATABASE_URL`.
