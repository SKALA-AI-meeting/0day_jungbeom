# MCP 설계

둘 다 Python FastMCP, Streamable HTTP. 도구 목록·입출력·오류 형식·허용 목록은 `common/contracts.md`가 정본이다.

## business-mcp (`services/business-mcp/`)

- api 내부 앱(`http://api:8001/internal/*`)을 httpx로 호출한다. DB 접근 없음. 권한·상태 판단은 하지 않고 api의 403·409를 코드로 전달한다(`forbidden`, `conflict`).
- 각 도구는 Pydantic 입력 모델, docstring 설명, `{ok, data}` 반환. api 4xx→코드 매핑(404 not_found, 403 forbidden, 409 conflict, 422 invalid_input), 5xx·연결 실패→`upstream_unavailable`(retryable, 1회 재시도). 타임아웃 10초.
- `post_message`의 `meta`(토큰·지연·모델)는 내부 메시지 API의 meta로 그대로 전달한다.
- 도구 목록(2026-10-20 재설계, 정본은 contracts.md):

| 도구 | 입력 | 내부 API | 종류 |
|---|---|---|---|
| get_board | {session_id} | GET /board. 할 일이 0개여도 섹션 담당 5행과 확정 스냅샷을 돌려준다 | 조회 |
| get_shared_documents | {session_id} | GET /docs/shared. 지원자 문서는 보낸 버전만, 동료 문서는 전부. 공유 안 된 지원자 문서·버전은 결과에 없다 | 조회 |
| post_message | {session_id, channel ∈ team∣dm∣manager_dm∣notice, sender ∈ colleague∣manager∣system, content, event_id?, run_id, seq, meta?} | POST /messages | 변경 |
| send_document | {session_id, doc_id∣part_no, content, channel, event_id, seq, run_id} | POST /docs/send. 동료 문서를 만들거나 revision+1 하고 버전 vN을 고정한 뒤 채널에 문서 카드 메시지 1건(event_id·seq 포함)을 올린다. seq는 파트별 고정(파트 번호×10). 응답 {doc_id, version, message_id} | 변경 |
| set_division | {session_id, parts, decided_by, run_id} | PUT /division. 섹션 담당 draft 5개를 쓰고 같은 검사를 통과하면 스냅샷을 만든다. 할 일 행은 읽거나 쓰지 않는다. division_min 위반은 `invalid_input` | 변경 |
| update_task | {session_id, task_id, status, run_id} | PUT /tasks/{task_id}. 동료는 보드에 있는 자기 실행 담당 할 일의 **상태만** 바꾼다(제목·섹션·order·due_min 없음). 할 일이 없으면 그래프가 부르지 않는다 | 변경 |
| release_document | {session_id, doc_id} | POST /releases/{doc_id} | 변경 |
| record_observation | {session_id, card_id, element, window_start, window_end, metrics, label, aux, evidence: [{type, id}], facts?, run_id} | POST /observations | 변경 |
| update_observation | {session_id, card_id, window_start, metrics, run_id} | PATCH /observations. 같은 (card_id, window_start) 행의 지정한 지표만 갱신(세션 종료 시 collab_help `promise_kept` 확정용) | 변경 |

- 삭제된 도구: 공유 문서 조회·파트 쓰기 도구. 동료는 자기 문서를 send_document로만 쓰고, 지원자 문서는 get_shared_documents로만 읽는다.
- 허용 목록(그래프가 주입): 동료 respond = search_documents, get_document, get_board, get_shared_documents. 팀장 respond_manager = search_documents, get_board, get_shared_documents. 결정적 노드(코드 호출) = post_message, send_document, set_division, update_task, release_document, record_observation, update_observation.
- 멱등 키는 그대로 전달하고 판단은 api에 맡긴다: `post_message`는 (run_id, seq), `send_document`는 문서 (doc_id, run_id)·메시지 (run_id, seq)(같은 키면 버전이 늘지 않고 기존 결과), `update_task`는 (task_id, field, run_id), `set_division`은 내용 동일성, `record_observation`은 (card_id, window_start)(run_id는 추적용), `update_observation`은 같은 키에 같은 run_id면 기존 값.

## rag-mcp (`services/rag-mcp/`)

- 시드 시 `scenarios/missions/<id>/documents/*.md`를 400자 청크로 나눠 BGE-M3(1024차원)로 임베딩해 `doc_chunks`에 저장. 키는 (catalog_version, doc_id, chunk_no)이고 catalog_version은 api와 같은 함수(`scenarios/version.py` 하나, 미션 폴더 전체(catalog.yaml·cards.yaml·documents·prompts 포함)의 내용 해시)로 계산한다. `reindex_documents`는 현재 버전을 색인하고 이전 버전 청크는 남겨 진행 중 채용 건이 자기 버전으로 검색하게 한다. 에이전트에는 노출하지 않는다.
- `search_documents`: 내부 `GET /internal/sessions/{id}/documents`로 `catalog_version`과 공개 목록을 받아 같은 버전·공개된 doc_id로 필터한 뒤 코사인 유사도 상위 k. 해당 버전 청크가 없으면 `upstream_unavailable`(재색인 필요). 결과에 doc_id·title·chunk·score.
- 모델 로드는 시작 시 1회. 컨테이너 메모리 3GB.

## 완료 기준
- MCP Inspector에서 도구 목록·설명 확인
- 연결 테스트: 그래프→MCP→api 저장→WS 노출 1건, 미공개 문서 차단, 권한 밖 변경 403→forbidden, api 중단 시 upstream_unavailable, 잘못된 입력 invalid_input
- 같은 run_id·seq 재호출이 중복 메시지를 만들지 않음. 같은 (doc_id, run_id)의 send_document 재호출이 버전을 늘리지 않고, 같은 run에서 파트 2개를 보내면 seq가 달라 메시지 2건이 생김
- get_shared_documents가 공유 안 된 지원자 문서를 돌려주지 않음, update_task에 status 외 필드는 invalid_input, update_observation이 지정한 지표만 바꿈
- 팀장 허용 목록에서 search_documents가 공개된 문서만 돌려줌
