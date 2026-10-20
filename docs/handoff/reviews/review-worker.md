# worker 트랙 W2 리뷰

대상: `track/worker`, HEAD `d6b5a08`, `git diff main...HEAD`. 개발자 보고서를 먼저 읽고 PRD·설계·카탈로그·내부 API 및 지정된 web-admin 보고서/리뷰와 대조했다. 판정: **수정 및 트랙 간 계약 확정 후 재리뷰 필요**.

직접 검증:

- `services/report-worker`에서 `LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false UV_CACHE_DIR=/private/tmp/codex-review-worker-uv uv run --frozen pytest -q -rs`: **11 passed, 2 skipped**. Postgres와 RabbitMQ에 연결하지 못해 실제 체크포인터·DLQ 연결 테스트는 재확인하지 못했다. 개발자 보고서의 13 passed와 구분한다.
- `uv run --frozen ruff check services/report-worker`, `uv run --frozen ruff format --check services/report-worker`: 통과. `git diff --check main...HEAD`: 통과.
- 기존 FakeLLM·MockTransport를 이용한 메모리 재현: 승인 후에도 LLM 호출 1회, draft/final 본문 동일, `label_in + metric` AND와 `all`의 미충족 결과 0, LLM 실패 시 최초 포함 3회·재시도 2회·대기 1/3초·고정 폴백 확인.
- 워커의 실제 조립 함수를 호출해 필드 형태·미발생 오판·금지 표현 누락을 확인했다. `track/web-admin` 소스는 `git show`로 읽었으며, 해당 렌더 표현을 React 서버 렌더/JavaScript로 재현해 아래 오류를 확인했다. 브라우저·실제 관리자 화면 통합·루트 make·전체 compose는 실행하지 않았다.

첫 pytest 실행에서는 기존 환경 설정의 LangSmith 추적이 자동으로 전송을 시도했으나 DNS 실패로 끝났다. 이후 추적을 끄고 위 결과를 재확인했다. 소스 수정·Git 변경 명령·gh·명시적 외부 게시 작업은 하지 않았고, 리뷰 결과만 이 파일에 저장했다.

## 1) 반드시 고칠 것(병합 차단)

1. **[P1] 리포트의 맥락·보조 사실 형태가 관리자 화면에서 렌더 오류를 일으킴** — `services/report-worker/report_worker/report.py:139`, `services/report-worker/report_worker/report.py:236`: 워커는 `prev_persona_message`를 객체, `aux_facts`를 객체 맵으로 보내지만 web-admin은 각각 문자열과 배열로 소비한다.
   - `track/web-admin:apps/web/components/admin/report-view.tsx:64`는 `{id, sender, channel, t_min, content}` 객체를 React 자식으로 직접 넣어 `Objects are not valid as a React child`가 발생한다. 기존 워커 픽스처의 정상 협력 메시지 근거에서도 재현된다.
   - 같은 화면 `:273`은 객체의 `length`가 없어 보조 사실을 숨기고, 창 밖 메시지가 하나라도 있어 분기에 들어가면 `:278`의 `section.aux_facts?.map is not a function`으로 실패한다. 워커가 보내는 빈 `{}`도 이 오류를 일으킨다.
   - 공용 계약은 내부 형태를 확정하지 않았으므로 프론트의 임의 형태를 정답으로 강제할 문제는 아니다. 오케스트레이터가 공통 JSON을 확정하고 양측 생산·소비를 맞춘 뒤, 실제 워커 응답을 화면에 넣어 확인해야 한다. 기준: `docs/common/contracts.md:69`.

2. **[P2] LLM 사용량이 실제 `reports.usage`에 저장되지 않음** — `services/report-worker/report_worker/api.py:85`: 요청에 `usage`를 보내도 현재 API의 `ReportIn`은 content만 받아 사용량을 버린다.
   - `services/api/app/routers/internal.py:622`의 입력 모델과 `:636`의 Report insert 어디에도 usage 저장이 없다. `test_usage_recorded_with_draft`는 전송 본문만 확인하므로 DB 기록 완료의 증거가 아니다. 변경 요청 1을 api-admin·계약에 반영하고 실제 저장을 확인해야 한다. content만 해시하는 현재 원칙은 유지한다. 기준: `docs/worker-infra/design.md:31`, `docs/common/harness.md` Observability.

3. **[P2] 다른 카드 메시지만으로 미발생 카드를 발생으로 오인함** — `services/report-worker/report_worker/report.py:155`: 카드 시각 이후의 아무 `event_id`나 찾고 해당 카드인지 확인하지 않는다.
   - 재현: respect 카드 예정 90분, 관찰 행 없음, 90분의 review 흐름 카드 메시지만 있음 → respect 섹션이 `event_fired=true`, 사유 `no_activity`가 된다. review와 respect는 같은 시각의 별도 이벤트이므로 review 실행 뒤 respect 실행 전에 제출하는 경우를 구별할 수 없다.
   - 보고서의 변경 요청 2를 반영해 카드별 실제 이벤트 상태를 사용해야 한다. `:180`의 `card_at_t_min`도 현재는 예정 시각이므로 지연 전달 때 실제 카드 메시지 시각과 구별할 수 있도록 계약을 함께 확정해야 한다. 근거: `services/api/app/services/scenario.py`는 review·respect를 서로 다른 `card_id`로 펼친다. 기준: `docs/common/contracts.md:69`, `docs/agent/design.md:131`.

4. **[P2] 응답 분·AI 활용 구분이 양측 필드 불일치로 표시되지 않음** — `services/report-worker/report_worker/report.py:273`, `services/report-worker/report_worker/report.py:289`: 워커는 실제 분을 `items[].minutes`로 보내고 AI 근거에는 구분 필드를 전혀 넣지 않는다.
   - web-admin `report-view.tsx:154`는 `response_minutes`만 읽어 정상 응답의 실제 2분이 표시되지 않는다. `:306`은 `category`가 없으면 호출·재사용 근거를 모두 “기타”로 보내 위임·맥락·검증 구분이 비게 된다.
   - 필드명과 category 열거값은 아직 계약에 없으므로 양측 합의 대상으로 처리하되, “실제 분 표시”와 “위임·맥락·검증으로 나눔”이라는 기존 요구는 완료해야 한다. `response_minutes=null`의 무관련 메시지 상황도 숫자 0분과 혼동하지 않도록 표현을 확정한다. 기준: `docs/common/contracts.md:69`. 항목별 `no_record_reason`은 현재 양측 위치가 맞는다.

5. **[P2] 메시지 1,000건 이후의 실제 근거를 누락함** — `services/report-worker/report_worker/api.py:71`: 전체 세션 수집을 한 번의 `limit=1000` 조회로 끝낸다.
   - 실제 API는 `services/api/app/routers/internal.py:154`에서 오래된 순으로 정확히 limit만 반환한다. 세션 메시지 수를 1,000건으로 제한하는 계약은 없으므로 이후 메시지는 수집되지 않고, `report.py:225`의 세션 근거 검증에서 정상 근거까지 제거되며 어시스턴트 요청/응답도 빈 문자열이 될 수 있다.
   - 전체 조회를 보장하는 페이지 처리 또는 별도 조회 계약이 필요하다. `since_t_min`만으로 이어 읽을 경우 공개 분 값이 소수 둘째 자리로 반올림되므로 동일 시각·반올림 구간 누락까지 고려해야 한다. 정밀 커서가 필요하면 api-admin에 요청한다.

6. **[P2] 금지어 검사가 직접적인 순위·점수 표현을 통과시킴** — `services/report-worker/report_worker/report.py:25`: 현재 패턴은 `1위`, `만점`, `감점`, `가산점` 표현을 잡지 못한다.
   - 직접 재현: `clean_text("지원자는 1위다. AI 활용은 만점이다.")`가 원문을 그대로 반환한다. FakeLLM이 같은 문장을 주면 `ai_usage.summary`에도 남는 구조다. 고정 모델·프롬프트 지시만으로 금지어 후처리 완료를 주장할 수 없다.
   - 워커 목적에 맞는 금지 표현을 보강하고 기존 금지어 테스트에 대표 표현을 포함해야 한다. 페르소나 guard 전체를 재사용할 필요는 없으며, 업무의 “우선순위”와 근거 원문 인용은 보존한다. 기준: AGENTS.md 고정 제약, `docs/common/contracts.md:69`의 observed·note·summary 검사 범위.

7. **[P2] foundation 소유 의존성 파일을 변경한 예외 승인 근거가 없음** — `services/report-worker/pyproject.toml:13`, `services/report-worker/pyproject.toml:20`, `services/report-worker/uv.lock:1`: `docs/plan.md:50`은 모든 pyproject·lockfile을 foundation 소유로 명시한다.
   - worker 폴더 안이라는 사실만으로 소유권 준수가 되지는 않는다. 제공된 브리프·보고서에는 예외 승인 근거가 없고 보고서는 알림만 남겼다. psycopg binary·테스트용 pyyaml의 필요성은 타당하므로 오케스트레이터가 해당 예외를 승인·기록하거나 foundation이 반영해야 한다. 진입점 `__main__.py`는 foundation 병합 후 worker로 소유권이 넘어와 수정 가능하다. 기준: `docs/plan.md:63`.

## 2) 고치면 좋은 것

- `services/report-worker/tests/test_dlq.py:33`: 성공적인 테스트의 정리 코드는 있으며 큐·exchange 접두사도 고유하다. 다만 connect 도중 일부 토폴로지 생성 후 실패하면 skip하면서 close·삭제 경로를 지나지 않는다. 부분 초기화도 정리하도록 fixture 자원 범위를 감싸면 공용 인프라에 잔여물을 남길 가능성을 줄인다. Postgres fixture의 두 번째 연결 실패도 같은 관점으로 정리할 수 있다(`tests/test_graph.py:49`). 이번 환경에서는 연결 실패라 실제 잔여 큐·스키마 0건을 재확인하지 못했다.
- `services/report-worker/tests/test_graph.py:68`: 기존 happy path에 approve 이후 `llm.calls == 1` 단언도 두면 재개 시 LLM 재실행 금지를 직접 고정할 수 있다. 현재 구현은 재현에서 정상이며, 새 조합 테스트를 늘릴 필요는 없다.
- `services/report-worker/report_worker/config.py:43`: 기본 모델은 요구대로 gpt-4o-mini지만 임의 `OPENAI_MODEL`도 그대로 사용한다. 고정 모델 제약을 설정 단계에서 검증하면 운영 오설정을 바로 발견할 수 있다. 모델 대체 경로는 발견하지 못했다.

## 3) 보고서의 “남은 문제”·“변경 요청” 쟁점별 의견

| 쟁점 | 의견·근거 |
|---|---|
| 남은 문제 1 / 변경 요청 1: usage 저장 | 요청에 동의하며 완료 기준의 미완료 의존성이다. `api.py:85`의 전송만으로 해결되지 않는다. ReportIn 수용·DB 저장·재전달 때 최초 값 유지까지 api-admin이 연결해야 한다. usage를 content 해시에서 제외하는 제안은 맞다. |
| 남은 문제 2 / 변경 요청 2: 이벤트 대용 판단 | 현 대용 로직은 수용 불가이며 필수 수정 3번으로 재현했다. 카드별 status·시각을 제공하는 요청에 동의한다. `GET /internal/sessions/{id}`가 이미 이벤트를 DB에서 읽고 있으므로(`internal.py:119`) 해당 조회 응답 확장이 MVP에서 작은 선택이다. 구체 계약은 오케스트레이터가 결정한다. |
| 남은 문제 3 / 변경 요청 3: window_missed | observe와 형식 확정이 필요하다. `rubric.py:109`, `report.py:188`은 제안한 `{value:true,evidence_ids:[]}`와 bool 둘 다 읽는다. 다만 생산자가 보장하지 않으면 지연 전달 카드가 정상 채점된다. `docs/agent/design.md:131`의 전달 지연·창 조건을 observe가 판정하고 같은 형태로 저장한 예시를 공유해야 한다. 새 사유나 추정 규칙을 워커가 추가할 필요는 없다. |
| 남은 문제 4: null 지표 사유 | null 지표를 기록 없음으로 두고 response_minutes만 활동이 있으면 0으로 두는 값 계산은 rubric.md와 맞는다(`rubric.py:74`). 다만 정상 레이블인데 aux 지표가 null인 경우를 `no_activity`라고 부르면 활동이 있었다는 입력과 사유가 충돌한다. 문서에 이 경우의 사유가 확정돼 있지 않으므로 현 선택을 계약으로 굳히지 말고 observe의 null 의미와 함께 오케스트레이터가 결정해야 한다. |
| 남은 문제 5: 자체 금지어 정규식 | 페르소나 guard는 연출·평가 기준까지 막으므로 전체 재사용을 피한 판단은 수용한다. 하지만 자체 검사에서 순위·만점 등이 빠진 것은 별개 결함이다(필수 수정 6번). 검사 대상은 요구대로 observed·note·summary이며 원문 quote와 평가표 숫자를 지우지 않는다. |
| 남은 문제 6: adjusted 생략·추가 필드 | adjusted·reviewer·review·history를 API GET 합성에 맡기는 것은 맞다. 실제 `services/api/app/routers/admin.py`의 merge_rubric 경로를 보존한다. 항목 사유 추가는 필요하며, minutes 이름은 합의해야 한다. revision change_ratio·doc_view summary의 생산 자체는 적절하지만 web-admin은 현재 해당 값/문서명을 표시하지 않는다. |
| web-admin의 필드 요청: 항목 사유·응답 시간 | 항목 사유는 `report.py:267`과 화면의 읽기 위치가 일치한다. 분 값은 minutes 대 response_minutes로 불일치한다. 섹션 사유로 항목의 not_applicable까지 대신할 수 없으므로 항목 사유를 유지해야 한다. |
| web-admin의 필드 요청: aux_facts·창 밖 메시지·맥락 | 창 밖 메시지의 t_min·quote는 맞고 channel은 선택이라 생략만으로 결함은 아니다. aux_facts 객체와 prev_persona_message 객체는 필수 수정 1번의 실제 렌더 오류를 만든다. 특히 직전 메시지 타입 충돌은 web-admin 보고서의 남은 문제 목록에 없지만 이번 대조에서 새로 확인했다. |
| web-admin의 필드 요청: card_t_min·AI category | 카드 시각은 기존 계약의 evidence.context.card_at_t_min을 화면이 먼저 지원해야 한다. 새 섹션 필드를 워커에 강제할 근거는 없다. AI category는 합의되지 않았지만 전부 “기타”인 상태는 위임·맥락·검증 구분 완료가 아니므로 공통 예시를 확정해야 한다. |
| 테스트 13개 과잉 여부 | 과잉 아님. 기존 heartbeat 1개 외 새 실행 사례 12개는 카드별 rubric 4개·기록 없음 1개·그래프 happy path 2종·중복 승인·final 응답 유실 재전달·사용량 전송·금지어/근거 제거·DLQ로 완료 기준에 대응한다. 다만 usage는 저장 검증이 아니고 DLQ 테스트의 API 다운은 실제 API 중지가 아닌 MockTransport 장애다(`tests/test_dlq.py:61`). 통합 완료로 확대 해석하면 안 된다. |

확인한 정상 구현: `consumer.py:86`은 interrupt 체크포인트를 읽은 뒤 draft POST를 하고, `:233`은 처리 성공 후 ack한다. draft와 approval 노드를 나눠 승인 재개 시 LLM이 재실행되지 않는다. final은 checkpoint의 draft를 그대로 전달하므로 API의 `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, sha256 규칙과 일치한다(`internal.py:617`). 재시도는 attempt 1·2·3에서 각 5·15·45초 뒤 재발행/최종 DLQ이며 총 시도 3회다. publisher confirm 뒤 ack, 발행 실패 시 원본 nack, DLQ의 API 연결·5xx 장애 시 미ack 재시도도 설계와 맞는다. 카드별 rubric 값·합계, only_if·all·label+metric AND, 충족 항목만 근거 부착, 같은 세션 근거 ID 필터도 확인했다. 별도 서비스 확장 등 MVP 과잉은 발견하지 못했다.

## 4) 다른 트랙 주의사항

- **오케스트레이터·api-admin** — `report_worker/api.py:80`: usage 입력·저장과 카드별 events 응답을 공용 계약으로 결정해야 한다. report_failed/final 상태 제약과 content만의 해시 규칙은 유지한다. worker가 직접 계약·API 파일을 수정할 작업은 아니다.
- **web-admin·worker** — `report_worker/report.py:139`, `:236`, `:273`, `:289`: 맥락 객체·보조 사실 맵·응답 분·AI 구분을 하나의 실제 워커 fixture로 맞춰야 한다. 현재 “모양이 달라도 방어”는 성립하지 않고 정상 메시지 근거만으로도 화면이 실패한다. doc_view의 summary/문서명과 revision change_ratio를 표시할지도 함께 확정한다.
- **agent-session(observe)** — `report_worker/rubric.py:43`: metrics의 `{value,evidence_ids}`, label null/unclassified/no_evidence, window_missed 생산 형태와 null 사유를 공유해야 한다. 메시지 classification.related_card는 요소 ID로 읽으며 관찰 창 경계로 창 밖 메시지를 표시한다. 세션 메시지 전체 수집이 해결되기 전에는 정당한 근거도 수집 누락으로 사라질 수 있다.
- **foundation·오케스트레이터** — `services/report-worker/pyproject.toml:13`: psycopg binary·pyyaml·lockfile 변경의 소유권 예외를 정리해야 한다. worker 진입점 이관과 의존성 파일 소유권은 서로 다르다.
- **e2e-runner** — `report_worker/graph.py:29`, `report_worker/consumer.py:32`: thread는 `report:{session_id}`이며 DLQ까지 백오프 합은 약 65초다. 이번 리뷰에서는 실제 Postgres·RabbitMQ 연결 검증이 skip됐고, 전체 healthy 확인은 M3에서 남는다. usage DB 기록·실제 워커 JSON 화면 렌더·미발생/지연 카드 사유까지 통합 확인해야 한다.
