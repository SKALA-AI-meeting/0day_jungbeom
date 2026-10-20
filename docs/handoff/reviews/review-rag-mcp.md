# rag-mcp W2 리뷰

대상: `track/rag-mcp`의 `git diff main..HEAD`, HEAD `b9b110f`. 개발자 보고서를 먼저 읽고 계약·설계·구현·테스트를 대조했다. **판정: 문서 전문의 버전 고정 문제 1건 해결 후 병합.** 소스 수정·Git 변경·외부 호출은 하지 않았다.

검증: 기존 가상환경에서 `python -m pytest -q -p no:cacheprovider`는 **2 passed, 1 deselected, 7 errors**였다. 7건은 모두 `services/rag-mcp/tests/conftest.py:50`에서 샌드박스의 PostgreSQL 소켓 연결 차단(`PermissionError`)으로 발생했으며 제품 실패로 판정하지 않았다. 기존 오류 매핑·연결 실패 재시도·503 복구 테스트 3개는 DB 없는 MockTransport 실행으로 별도 통과했다. 잘못된 `top_k=0`의 `invalid_input` 응답과 아래 버전 문제도 인메모리 MCP 클라이언트로 확인했다. rag-mcp의 ruff check·format check 및 `git diff --check main..HEAD`는 통과했다. 실제 BGE-M3·Docker·전체 저장소 검사는 이번 리뷰에서 재실행하지 않았으므로 보고서의 성공 결과와 구분한다.

## 1) 반드시 고칠 것 — 병합 차단

- **[P1] 전문 조회도 세션의 catalog_version에 고정해야 한다 — `services/rag-mcp/rag_mcp/tools.py:84`.** API가 준 버전은 사용하지 않고 현재 파일을 읽으므로, 같은 채용 건의 나중 지원자는 앞선 지원자와 다른 회사 문서를 받는다(`PRD.md:145`, `PRD.md:221`, `docs/common/scenario-model.md:25` 위반). 임시 scenarios 복사본에서 V1을 기록한 뒤 metrics 본문을 V2로 바꾸고 API는 V1을 반환하게 했을 때, `get_document`가 V2 전용 문구를 반환하는 것을 재현했다. 문서 삭제 시에는 보존된 V1 색인이 있어도 `not_found`가 된다. 버전별 원문 또는 채용 건에 복사된 원문을 반환하고, 해당 버전을 제공할 수 없으면 최신 본문 대신 `upstream_unavailable`로 실패해야 한다. 기존 재색인 테스트에 구버전 전문 조회 검증 1건을 포함하면 충분하다. **개발 브리프가 현재 파일 읽기를 지정했던 점은 확인했다. 개발자의 브리프 일탈이 아니라 상위 PRD의 동일 조건 원칙과 충돌하는 브리프 보완 사항이며, API/계약 변경이 필요한 해결책은 오케스트레이터가 결정해야 한다.**

## 2) 고치면 좋은 것

- **API mock 픽스처를 DB에서 분리 — `services/rag-mcp/tests/conftest.py:89`.** 오류 매핑·재시도 테스트는 DB를 사용하지 않는데도 `api(database_url)` 때문에 PostgreSQL 없이는 실행되지 않는다. DB를 쓰는 테스트만 DB 설정을 주입하도록 정리하면 기존 테스트 수를 늘리지 않고 검증이 쉬워진다.
- **잘못된 입력의 계약 응답 1건을 테스트로 유지 — `services/rag-mcp/tests/test_tools.py:23`, `services/rag-mcp/rag_mcp/server.py:23`.** 직접 확인한 `top_k=0`은 정상적으로 `invalid_input`을 반환했지만 회귀 테스트는 없다. `docs/mcp/design.md:20`의 명시된 완료 기준에 해당하므로 대표 입력 1건만 추가할 가치가 있다.
- **3GB 제한에서 실제 로드·색인·검색을 확인 — `services/rag-mcp/rag_mcp/embedder.py:40`, `infra/docker-compose.yml:76`.** 호스트 live 테스트와 이미지 빌드 성공만으로 컨테이너 메모리 제한 및 초기 다운로드를 포함한 healthcheck 시간 충족은 확인되지 않는다. 새 테스트 묶음을 만들기보다 M1 연결 확인 때 실제 제한 아래 한 번 측정하면 된다. 현재 근거로 OOM이나 기동 실패를 단정하지 않는다.

## 3) 보고서의 남은 문제·변경 요청별 의견

- **`indexed`가 청크 수인 점: 유지 가능, 의미를 계약에 명시할 것 — `services/rag-mcp/rag_mcp/tools.py:126`, `docs/common/contracts.md:179`.** 계약은 `n`의 단위를 정의하지 않았고 현재 README·docstring·테스트는 청크 수로 일치한다. 이것만으로 병합 차단할 근거는 없다. 오케스트레이터가 계약에 “색인된 청크 수”를 적으면 충분하며 별도 문서 수 필드는 MVP에 불필요하다.
- **현재 파일을 읽는 전문 조회: 수용 불가 — `services/rag-mcp/rag_mcp/tools.py:84`.** 위 차단 항목과 같으며, 검색에서 구버전을 보존하는 것만으로 전문 조회의 버전 혼합을 막을 수 없다.
- **3.4GB 이미지·첫 모델 다운로드: 크기 자체는 수용 가능 — `services/rag-mcp/Dockerfile:9`, `services/rag-mcp/rag_mcp/server.py:35`.** CPU torch 의존성과 모델 로드 후 healthy가 되는 구조는 목적에 맞는다. 추가 경량화보다 실제 3GB 메모리·초기 기동 시간 확인을 우선한다.
- **실제 API 연결 미실행: 현 단계에서 수용 — `docs/plan.md:65`, `services/rag-mcp/tests/conftest.py:99`.** 트랙은 mock으로 개발하고 M1 끝에 연결 테스트한다는 규칙과 맞으며, 그래프→rag→API→WS 종단 완료로 보고해서는 안 된다.
- **변경 요청 1, 캐시 볼륨 `/models` 정렬: 반영 필요 — `services/rag-mcp/Dockerfile:7`, `infra/docker-compose.yml:72`.** 현재 모델은 `/models`에 받는데 영속 볼륨은 다른 경로에 있어 컨테이너 재생성 시 캐시를 잃는다. 개발 브리프가 `/models`와 compose 변경 요청을 명시했으므로 트랙의 범위 위반은 아니다. 오케스트레이터가 배포 전 볼륨을 함께 맞춰야 한다. 단순 stop/start와 컨테이너 재생성은 구분해야 한다.
- **변경 요청 2, `.env.example`의 HF_HOME 주석: 선택 사항 유지 — `services/rag-mcp/Dockerfile:7`.** 이미지 기본값이 있으므로 실행 필수값은 아니다. 주석을 추가한다면 compose 볼륨과 일치해야 한다는 설명이면 충분하다.
- **변경 요청 3, 골격 이미지 재빌드·seed: 타당 — `Makefile:6`, `scripts/seed.py:115`.** `infra-up`에는 `--build`가 없으므로 병합 후 main에서 기존 단일 스택의 rag-mcp를 명시적으로 재빌드·재생성하고, API가 준비된 뒤 seed해야 한다. 새 통합 스택을 추가로 띄울 필요는 없다.

## 4) 다른 트랙 주의사항 및 확인 결과

- **api-admin/foundation: 같은 버전 입력을 유지 — `services/rag-mcp/rag_mcp/documents.py:42`, `services/api/app/services/scenario.py:66`, `scenarios/version.py:10`.** 양쪽 모두 같은 `version.py` 함수에 scenarios 경로를 전달하며 catalog·문서·프롬프트 파일을 해시에 포함한다. `docs/mcp/design.md:14`의 짧은 해시 설명에는 prompts가 빠져 있으나 실제 공용 함수와 scenario-model 계약은 일치한다. 서로 다른 scenarios 내용으로 실행하면 함수가 같아도 버전은 달라진다.
- **agent-min/assistant: 도구 허용 목록과 오류 봉투를 적용 — `docs/common/contracts.md:185`, `services/rag-mcp/rag_mcp/tools.py:47`.** `reindex_documents`는 관리용으로만 호출하고 모델에는 노출하지 않는다. `session_id`는 그래프가 주입하며, 색인 없는 버전의 `upstream_unavailable`은 폴백 대상으로 처리한다. API 4xx 매핑·10초 타임아웃·실패 후 1회 재시도는 business-mcp와 일치한다(`services/rag-mcp/rag_mcp/client.py:82`).
- **공개 필터·재색인 구현은 적절 — `services/rag-mcp/rag_mcp/tools.py:44`, `services/rag-mcp/rag_mcp/tools.py:82`, `services/rag-mcp/rag_mcp/store.py:34`.** 검색은 버전·공개 ID로 SQL 필터하고 전문 조회는 공개 확인 후 파일에 접근한다. 재색인은 트랜잭션 안에서 해당 버전만 교체해 이전 버전을 보존한다. 청크는 strip한 본문을 400자 단위로 자르며(`documents.py:37`), Fake와 실제 BGE-M3 live 테스트도 분리돼 있다(`tests/conftest.py:39`, `tests/test_live.py:7`). 테스트 범위나 구현에 눈에 띄는 MVP 과잉은 없다.
- **오케스트레이터: main의 handoff 변경을 보존한 채 rebase — `docs/handoff.md:11`, `docs/handoff.md:52`.** 지정된 `main..HEAD` 비교에는 handoff 운영 규칙·상태가 되돌아가는 diff가 보이지만, `b9b110f` 자체는 `services/rag-mcp/` 14개 파일만 변경했다. main에만 추가된 후속 커밋 3개 때문에 생긴 비교 차이이므로 무단 문서 수정으로 판정하지 않는다. 개발 브리프가 rag-mcp 전체와 pyproject·lock 변경을 허용한 것도 확인했다. 병합 전 main 위 rebase와 `make test`·`make lint`를 완료해야 한다(`docs/plan.md:43`).
