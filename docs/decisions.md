# 설계 결정 기록

| 날짜 | 결정 | 이유 | 대안 |
|---|---|---|---|
| 2026-10-20 | Recovery: LLM 호출 실패 시 2회 재시도 후 규칙 기반 폴백(고정 문장 "잠시만요"로 응답, 체크포인트에서 재개). 대체 모델은 두지 않음 | PRD 제약상 gpt-4o-mini만 사용 가능. 하네스 Recovery 요소를 PRD 변경 없이 충족 | 같은 모델 다른 설정을 대체 모델로 등록, 팀에 로컬 모델 허용 제안 |
| 2026-10-20 | 기술 스택은 PRD 부록 A.1 그대로: Next.js, FastAPI gateway, LangGraph agent, gpt-4o-mini, BGE-M3 로컬 임베딩, WebSocket, PostgreSQL+pgvector, Streamable HTTP MCP 2개(:9101, :9102), RabbitMQ, 자체 JWT, LangSmith, Docker Compose | 평가 요소(큐, MCP 2개, 관측, 인증)를 빠짐없이 자연스럽게 덮음 | 임베딩을 OpenAI로, 프론트를 Vite SPA로 가볍게 |
| 2026-10-20 | 평가 요소를 채용 건 단위로 1~4개 자유 선택. 요소별 이벤트 카드로 시나리오 조립, 시점은 L×1/4~3/4 균등 배치 | 기업 맞춤 평가와 비교 공정성을 같이 만족. 120분·4개면 PRD 원안과 동일 | 초대 단위 선택, 기업 기본값+초대 변경 |
| 2026-10-20 | 관찰은 규칙 지표 + 요소별 고정 레이블 LLM 분류(temperature 0) | 순수 규칙으로는 비난·해결 중심 같은 행동 유형 판별 불가. LLM만 쓰면 재현성 깨짐 | 규칙만, LLM만 |
| 2026-10-20 | 사람 승인은 리포트 "검토 완료"(F-09). F-06 문서 승인은 MVP 제외 | 원칙 "사람이 판단한다"와 일치, 버튼 하나. F-06은 사용자 가치 없이 구현량만 큼 | F-06 구현, 승인 없이 출력 검사만 |
| 2026-10-20 | 리포트 생성을 LangGraph 그래프로 만들고 draft 뒤 interrupt, 검토 완료가 큐로 같은 thread를 재개해 final 저장 | 레퍼런스의 "변경 전 멈춤·승인 후 재개"를 세션 그래프를 건드리지 않고 충족. 큐도 2종으로 자연스럽게 확장 | 세션 내 지원자 승인(확장 후보), F-06 부활, 설명만 |
| 2026-10-20 | 에이전트를 api(FastAPI) 프로세스 안의 모듈로 둠 | 분리하면 내부 API만 늘어남. MCP 경유 구조는 유지되어 평가 영향 없음 | 별도 agent 서비스 |
| 2026-10-20 | MVP 제외: F-05, F-06, F-07, F-25, 세션 길이 선택 UI, 타임라인 미리보기, LLM 페르소나 지원자 e2e | P1·선택이거나 평가 항목과 무관 | — |
| 2026-10-20 | e2e는 대본 픽스처가 지원자 역할. 짧은 세션은 내부 API로 생성, 기록은 파일로 커밋 | 결정적이고 CI 가능 | LLM 지원자 |
| 2026-10-20 | 개발은 Herdr pane 병렬(개발 Claude, 리뷰 Codex), pane마다 worktree, 한 pane에 역할 하나 | 사용자 지시 | 단일 pane 순차 |
| 2026-10-20 | 이어하기: 접속이 끊겨도 세션 시계는 계속 흐르고 이벤트는 예정대로 일어남 | 공정성과 단순성. 일시정지는 악용 가능하고 예약 재계산이 필요 | 일시정지 |
| 2026-10-20 | Codex 설계 리뷰 반영: 세션을 초대 시점에 생성, 내부 API 별도 포트, 이벤트 상태(pending·fired·done)와 run_id·seq 멱등, 큐 persistent·manual ack·미발행 재탐색, 문서 변경 로그·열람 기록, 시나리오 버전 고정, 하네스 수치화, foundation 선행 후 병렬, 최소 종단 흐름을 M1로 | 리뷰 지적 A1~A7, B1~B10, C, D | — |

## 2026-10-20 재검토 반영
- 분업 최소 조건: 2번은 지원자, 4·5 중 하나 이상은 동료 단독. 이유: 책임감·존중 카드의 전제를 모든 분업에서 보장. PRD 6.2에 반영.
- 미합의 자동 확정: 3회 조정 또는 다음 이벤트 도래 시 마지막 안으로 확정하고 알림. PRD F-21에 반영.
- 리포트 승인 순서는 interrupt 체크포인트 → draft 저장 → ack. 이유: ack 뒤 승인이 와도 재개 대상이 항상 있음.
- 파일럿 통과 기준과 가격 가설을 PRD 11·14에 잠정 수치로 둠.

## 2026-10-20 3관점 최종 리뷰 반영
- 리뷰어가 "설계 방향 변경"으로 표시한 3건은 PRD가 이미 요구하는 행동(상호 리뷰, 유연성 카드의 분담 재조정, 말없이 반영한 행동의 관찰)을 구현 규칙으로 확정한 것이라 기획 변경 없이 반영: 동료의 자기 파트 수정, 업무 중 재분업 1회, evidence 타입 확장.
- E8(MCP 변경 도구 앞 승인)은 "선택"이라 그대로 둠. 세션 내 지원자 승인은 확장 후보 유지.
- 프롬프트를 `scenarios/prompts/`로 옮김: 채용 건 고정(버전 해시) 약속을 지키기 위해. prompts 트랙 소유.
- F-25(무응답 확인)는 PRD 예외 흐름에 MVP 제외로 표기.

## 2026-10-20 지원자 리드 고정
- 지원자를 리드로 고정(카탈로그 `candidate_role: lead`). 분업은 동료가 묻고 리드가 정하며, 미결정 시 다음 이벤트에서 기본안으로 진행하고 `decided_by`에 남긴다. 이유: 결정·재지시 행동이 드러나 관찰 근거가 풍부해짐. 팔로워 역할은 brief 2개와 대본 추가로 붙일 수 있는 확장 후보.

## 2026-10-20 인재상 페르소나와 평가표
- 동료는 "회사가 원하는 인재상"으로 설정된 한 사람(카탈로그 `persona`). 성향은 자유, 의무 액션(카드)은 고정, 선점 금지 5개와 공통 금지로 평가를 보호. 이유: 규칙 묶음보다 자연스럽고, 점수는 지원자 행동만 세므로 동료 자유도가 점수를 깎지 않음. 기업별 인재상 편집은 확장.
- 평가표: 요소당 4항목, 규칙 산출 1/0/기록 없음, 담당자 항목 조정(메모 필수) 후 확정. AI는 점수를 매기지 않는다는 원칙을 "규칙 산출 + 사람 확정"으로 재정의하고 PRD 5·9·10, F-03/F-04/F-04a, 동의·디브리핑 문구를 갱신. 상세는 docs/common/rubric.md.
- 리포트에 산출물(기획안 최종본) 섹션 추가. 산출물 품질은 점수화하지 않음.
- MVP 기본값: 관리자 회사당 1명, 채용 건 생성 후 수정·삭제 없음, 전체 대화 열람 제외(근거 인용까지), 빈 파트 제출 허용, 지원자에게 점수 비공개.

## 2026-10-20 동료 작업 기억
- State에 `work_notes`(담당 파트, 리드 지시 누적, 합의, 말한 진행 상태). 중간 초안(L/2, texture 이벤트)과 리뷰 완성본은 이를 반영하고 지시 반영 검사를 통과해야 함. 보드는 분업 시 doing, 리뷰 시 done. 이유: 리드 지시가 산출물에 드러나야 유연성·협력 근거가 선명하고, 동료의 일관성이 평가 품질을 좌우함. 앞서 둔 "중간 초안 없음" 기본값을 뒤집음.
- 평가표 세부 항목은 세션 전에 공개하지 않고(상황 노출) 디브리핑에서 공개. 동의 화면은 요소 이름과 "평가표가 있다"까지.

## 2026-10-20 개발·UX 리뷰 반영 (Codex design-reviewer2, Claude ux-reviewer)
- 책임감 알림은 지원자에게만(`notice` 채널). 팀장·동료가 모르는 상태여야 "먼저 알림"이 성립. 킥오프에서 인터뷰 요약 공유 예정 시각을 미리 알려 지연이 자연스럽게 보이게 함.
- 요소 관찰 창은 다음 요소 카드까지(흐름 카드·texture는 닫지 않음). 마지막 창은 세션 종료까지라 보고 중 지적도 들어감.
- 세션 실패 시 디브리핑(연출 설명) 없이 중단 안내만 → 재응시 가능. 재초대는 이전 응시와 연결.
- 리드가 킥오프 직후 정한 분업도 저장(kickoff 단계 DM → negotiate). 재분업 한도는 유연성 전 1회 + 후 1회.
- 동료 자유도는 유지하되 선점 금지 창에서는 `in_window_help`(정보·관점은 주고 결정만 돌림)로 범위를 데이터화. 리뷰어의 "자유도 제한" 제안은 이 범위 표준화로 대신함.
- 평가표 조정: 협력 `acknowledge_only` 레이블과 responded_to_request 지표, 책임감 대안 제시를 aux 판정으로 분리, 유연성 레이블 우선순위 명시, 존중 "비난 아님"은 언급했을 때만 판정(only_if). 0점은 근거 불요, 기록 없음에 사유.
- 멱등: seq는 노드별 고정 슬롯 + 실행 전 기존 행 조회 후 재사용. final 해시는 reports.content 정규화 해시. 조정은 항목당 1행, 트랜잭션.
- 분류 결과를 messages.meta.classification에 저장해 observe·지표가 읽음. 지표는 근거 id를 함께 반환.
- 초대 취소·만료 표시·안내 문안, 안 읽음 배지, 제출 확인 창, 동시 접속은 마지막 연결 유효, 정체 질문엔 AI라고 답함.
- 고영향 AI 해당 여부는 미확정으로 서술. 동의 문구를 "AI 분류를 입력으로 규칙 점수 계산, 사람이 확정"으로 통일.
- 받아들이지 않은 것: 책임감·유연성 함께 선택 시 시점 재배치(PRD 시점 규칙 유지, 압박은 의도), 창 밖 행동 점수화(사실 표시만), 전체 대화 열람(확장), 응답 시간 접근성 배려 기준(파일럿 뒤 결정), 타임드 동료 재방문(동료가 기대만 분명히 말함).

## 2026-10-20 foundation 리뷰 반영 (Codex)
- 종료 run 실패: `complete()`는 종료 run이 `ok=False`여도 completed로 진행하고 리포트를 발행한다. agent_runs는 failed로 남기고 경고 로그를 찍는다. 이유: 지원자 작업물을 잃지 않기 위해. 대안: 세션 failed(작업물이 리포트로 가지 않음).
- 종료 직렬화: `complete()` 전체(상태 재검증 → 종료 실행 → 재사용 추정 → completed 커밋 → 발행)를 세션 Lock 안에서 하고, Lock 안에서 다시 읽은 상태가 in_progress가 아니면 아무것도 하지 않는다. `run_agent(lock_held=True)`로 같은 Lock의 재획득(교착)을 피한다. 이유: 제출과 만료가 겹쳐도 종료 실행·발행이 한 번만 일어나게.
- web mocks 소유권 분리: `mocks/index.ts`(foundation)는 `mocks/admin.ts`(web-admin)·`mocks/office.ts`(web-office)의 ROUTES를 합치기만 하고, fixture도 `fixtures/admin/`·`fixtures/office/`로 나눈다. 이유: W2의 두 화면 트랙이 같은 파일을 고치지 않게.
- 문서 파트 행: 세션 시작 시 `SessionService.start()`가 시나리오 parts 수만큼 `document_states`(빈 본문, revision 0)를 만든다. tasks는 분업 확정 때 api-candidate가 만든다. 이유: State 스냅샷과 문서 PUT이 행 존재를 전제로 단순해짐. 대안: PUT에서 upsert.
- `SCENARIOS_DIR`: 기본값(/scenarios)이 로컬에 없을 때만 저장소 `scenarios/`로 대체하고, 사용자가 지정한 경로가 없으면 설정 오류로 멈춘다. 이유: 잘못된 경로를 조용히 숨기지 않게.
- 소유권 예외 3건 수용: `scenarios/catalog.yaml`의 두 줄 인용(값 불변), `ruff.toml`의 Markdown 제외, `apps/web/README.md` 실행법.
- MVP 제외: 브로커가 발행을 확인한 뒤 큐가 유실된 경우의 복구(outbox는 `*_enqueued_at`이 비어 있는 세션만 재발행한다).

## 2026-10-20 api-admin 리뷰 반영
- 관찰 창(`current_element`): 가장 최근에 실행된 **요소 카드**의 요소다. 흐름 카드·결 메시지는 창을 닫지 않고, 마지막 요소 창은 제출 뒤 종료 실행이 끝날 때(completed 전)까지 열려 있다. 이유: 보고 단계의 지적도 창 안으로 봐야 한다. `scenario-model.md`·`agent/design.md`의 예전 "흐름 카드도 창을 닫음" 문구는 이 결정이 우선한다(문서 정합화는 오케스트레이터).
- `Idempotency-Key` 헤더를 MVP 계약에서 뺀다. 멱등은 도메인 규칙(세션 전이, 내부 저장 키, 리뷰 본문 비교)으로만 보장하고 화면은 생성 POST를 자동 재시도하지 않는다. 이유: 초대 토큰 원문이 DB에 없어 키 기반 재응답을 복원할 수 없고 저장소를 더하는 비용이 크다. 대안: 멱등 키 테이블(제외).
- 종료 뒤 쓰기: 내부 문서·task·분업 PUT은 세션이 in_progress일 때만 받는다(제출 직후 종료 실행 중에는 in_progress라 허용). 이미 저장된 run_id 재전달은 기존 결과를 돌려준다. 이유: 확정 리포트의 산출물이 바뀌지 않게.
- tasks 생성 담당 정정: 위 "foundation 리뷰 반영"의 "tasks는 분업 확정 때 api-candidate가 만든다"를 **api-admin의 내부 division PUT**으로 바꾼다(division과 tasks를 한 트랜잭션). api-candidate의 sync_tasks는 그쪽 수정 라운드에서 제거한다.
- 리뷰 오류 우선순위: 이미 제출된 세션은 `already_reviewed`(409)가 `memo_required`·`invalid_item`·`duplicate_item`(400)보다 먼저다.
- 내부 메시지 응답(GET·POST·분류 PUT)은 `meta`를 포함한다(공개 API는 제외). 요청 본문 검증 실패는 두 앱 공통으로 422 `invalid_input`.

## 2026-10-20 prompts 리뷰 반영
- `silent`(와 `apply_silently`)의 evidence는 문서 revision만 쓴다. 창 안에 지원자 revision이 없으면 silent로 분류하지 않고 `label: null`(→ unclassified)로 둔다. 이유: agent/design.md의 evidence 계약을 유지해 트랙마다 다른 의미의 관찰이 저장되지 않게. 대안: 다른 활동 id 허용(계약 완화, 기각).
- observe 책임감 입력: `[카드]` 블록에 코드가 계산한 `release_at`(실제 공개 시각, 분)과 `released_before_message`(지원자 메시지 id별 공개 전/후 bool)를 넣는다. LLM은 알림 본문의 "약 15분"으로 공개 시각을 추정하지 않는다. 이유: 실제 지연은 세션 길이에 따라 달라(6분 세션 0.75분) 본문으로 추정하면 오분류한다. 이 값은 observe 전용이고 페르소나 컨텍스트에는 넣지 않는다.
- 관찰 창 종료: 흐름 카드(report_request 포함)는 창을 닫지 않고, 마지막 요소 창은 제출(세션 종료)까지다. agent/design.md 전이표와 scenario-model.md의 "흐름 카드 포함" 문장을 observe 절에 맞춰 고쳤다. 이유: 마감 보고 메시지의 첫 지적도 존중 창에 들어가게. 대안: report_request에서 닫기(보고 속 지적 누락).
- 책임감 레이블은 공개 전후와 무관하게 알린 내용으로 고른다. `notify_only`는 "지연 사실만 알리고 대안 없음", `notify_with_alternative`도 시간 조건 없이 "알리고 대안 제시"다. 공개 전 알림 여부는 지표 `notified_before_release`(항목 `resp_notified_before_release`)가 따로 센다. 이유: 레이블과 지표가 같은 사실을 이중으로 세지 않게, 공개 뒤 알림이 null로 빠지지 않게.
- guard 판정 패턴은 지원자·리드·응답에 대한 평가나 진행 중인 평가 운영 문맥으로 좁히고, 숫자 점수는 별도 `score` 그룹(업무 지표 문장은 `unless`로 보존)으로 막는다. 컨텍스트 유출 픽스처(`scenarios/prompts/fixtures/context_leak.yaml`, 미래 유도 3건·역할 사칭 2건)는 prompts 트랙 담당이다.

## 2026-10-20 api-candidate 리뷰 반영 (Codex)
- 카드 실행은 세션별 due_at 직렬: 미완료(fired) 묶음이 done·failed·skipped가 되기 전에는 뒤 묶음을 디스패치하지 않는다. 재시작 복구도 같은 순서를 따른다. 이유: 상태를 가진 세션 그래프가 카드 순서를 뒤집어 처리하지 않게. 대안: retry를 events보다 먼저 호출(60초 미만 fired와 여러 pending 묶음 문제가 남음).
- 지원자 문서 PUT 권한: 분업 확정 전에는 모든 파트(리드가 초안을 잡을 수 있음), 확정 뒤에는 candidate·both만, colleague 단독 파트는 403. 이유: 동료 파트(정책 위반 포함)를 지원자가 직접 덮어쓰면 관찰 전제가 깨진다.
- 지원자 문서 PUT은 세션 Lock 안에서 상태를 다시 확인하고 저장한다. 내부 라우터는 Lock을 잡지 않는다. 이유: complete()와 직렬화해 종료 뒤 쓰기를 막되, 실행 중 runner의 내부 API 호출이 자기 Lock을 기다리는 교착을 피하려고. 대안: DB 행 잠금으로 complete와 공유(종료 경로 전체를 바꿔야 함).
- 디브리핑 기한은 세션 종료 시각(submitted_at, 진행 중 실패면 실패 시각) + 7일로 고정하고 debrief_token exp를 그 시각으로 발급, 지나면 410 expired. 진행 중 실패 시각은 `fail(session)`이 ends_at을 실패 시각으로 당겨 기록한다(별도 컬럼 없이). 리포트 단계 실패는 세션 종료가 submitted_at이므로 그 기준. 이유: GET마다 "지금부터 7일"을 발급하면 기한이 무기한 연장된다.
- 카드 3회 실패의 failed 기록과 SessionService.fail을 한 트랜잭션으로 하고, failed 필수 카드가 남은 in_progress 세션은 스케줄러 retry 단계가 fail로 수렴시킨다. 이유: 두 커밋 사이에 죽으면 세션이 진행 중으로 남아 만료 때 리포트까지 발행된다.
- 시작 공개 문서는 `SessionService.start()`가 시작 트랜잭션에서 released_at을 바로 기록한다. 이유: 첫 tick(최대 5초)까지 423이 되는 공백 제거, 지원자·내부·rag가 같은 시점부터 같은 상태를 봄.
- assistant_reuse의 revision 컬럼은 보류: 현재 내부 REST·워커 소비 계약에 revision이 없어 컬럼만 추가하는 효과가 없다. 순수 함수 반환값에만 revision을 둔다.
- `submitted_at` 이후 message.send는 상태와 무관하게 session_ending(접수 함수가 submitted_at을 status보다 먼저 검사).

## 2026-10-20 worker 리뷰 반영 (Codex)
- 리포트 워커 산출 형태를 web-admin이 읽는 형태로 확정: 근거 `context.prev_persona_message`는 문자열 "<보낸이> · <t>분: <본문>", `context.card_at_t_min`은 실제 카드 메시지 시각, 섹션 `aux_facts`는 문장 배열, `out_of_window_messages`는 `[{t_min, channel, quote}]`, 항목 `minutes`(응답 시간 항목만, 관련 메시지 없으면 null)·`no_record_reason`, AI 활용 근거 `category`(delegate·context·verify, 규칙 부여). 이유: 객체 맵·객체 맥락이 관리자 화면 렌더를 깨뜨렸다. 실제 워커 출력 `services/report-worker/tests/fixtures/report_sample.json`을 기준 예시로 둔다. 대안: 화면이 객체를 풀어 읽음(화면 트랙 재작업).
- usage: draft 본문에 `usage`를 받아 `reports.usage`에 저장(재전달은 최초 값). 해시는 content에만. 이유: 세션 비용 = agent_runs.usage + reports.usage 합(harness Observability).
- events: `GET /internal/sessions/{id}`에 `events: [{id, card_id, element, status, due_at, fired_at}]`. 워커는 카드 발생(status fired·done), 실제 카드 시각(같은 event_id의 첫 메시지), 전달 지연(예정보다 90초 초과 → window_missed)을 이걸로 판단하고 메시지 시각 기반 대용 추정은 지웠다. 이유: review와 respect처럼 같은 시각의 다른 카드를 구별 못 했다. `id`는 메시지 event_id와 맞추려고 넣었다.
- messages `offset`: 정렬에 id를 더하고 offset 쿼리를 둔다. 워커는 limit 500으로 끝까지 읽는다. 이유: 1,000건 이후 근거가 수집되지 않아 정상 근거까지 제거됐다. 대안: since_t_min 커서(반올림 경계 누락).
- null 지표 사유: aux 판정 지표(response_specific·proposes_alternative·proposes_fix)가 null이면 레이블이 정상이어도 `classify_failed`. 그 밖의 null은 레이블 unclassified·null이면 classify_failed, 아니면 no_activity. `window_missed`는 관찰 `metrics.window_missed: {value: true, evidence_ids: []}`(bool 허용)로 확정.
- 소유권 예외: worker `pyproject.toml`·`uv.lock` 변경 승인(런타임 `psycopg[binary]`: slim 이미지에 libpq가 없음, dev `pyyaml`: 테스트가 카탈로그를 읽음). 이 라운드에 한해 worker 트랙이 `services/api/app/routers/internal.py`(events·offset·usage)와 해당 테스트, `contracts.md`·`decisions.md`를 고쳤다.
- 금지어 보강: 1위·N위·N등·만점·감점·가산점·상위/하위 N%·등수. 업무 "우선순위", 근거 원문 quote, 평가표 숫자는 검사하지 않는다. 설정은 OPENAI_MODEL이 gpt-4o-mini가 아니면 시작 시 오류.
