# 재설계 설계 리뷰

2026-10-20 · 판정: **아래 차단 항목을 정리한 뒤 개발 착수**.

브리프가 지정한 PRD·제안서·공통 설계·도메인 설계·계획·결정·개발 프로세스·과제 평가표를 대조했다. 기존 코드는 검토하지 않았다. 검증은 문서 계약 대조와 배치 공식의 독립 계산이며, 구현 테스트 통과를 뜻하지 않는다.

확인된 일치 사항: 인성 요소 5개·카드 7개 ID, 요소당 4항목, 기본 배치 공식 `L/4 + i·(L/2)/N`(i=0부터), 책임감 공개 지연 `L/12`. 전체 선택·120분의 시각은 **10·30·45·60·70(자료 공개)·75·90·110분**으로 계산된다. 반대 의견 고정·미공유 시 대체 대상·미선택 요소의 흐름 처리·미션/카탈로그 버전 고정 원칙도 명시돼 있다. 문제는 이를 실행하고 관찰하는 경계 계약이다.

## 1. 반드시 고칠 것 — 개발 시작 차단

### A1. 보고 화면이 서버에서 거부하는 채널만 열어 준다

- 위치: `docs/frontend/design.md:77`, `docs/common/contracts.md:119`, `docs/common/contracts.md:169`, `docs/agent/design.md:89`, `docs/api/design.md:58`.
- 근거: 화면은 팀장 DM으로 요청을 받고 DM만 쓰도록 하지만, 계약은 팀 채널만 허용하고 에이전트도 팀 채널에 요청하므로 정상적인 보고가 `session_ending`으로 거부된다.
- 필요 수정: 요청·입력·분류·종료 감지를 같은 채널로 통일하고 조기 제출→보고→종료를 그 채널로 검증한다. API 설계의 “팀장 DM도 보고 감지”도 함께 정리한다.

### A2. 관찰 레이블·보조 판정·근거 타입이 생산자와 소비자에서 다르다

- 위치: `docs/agent/design.md:113`, `docs/agent/design.md:178`, `docs/agent/design.md:184`, `docs/common/rubric.md:32`, `docs/common/rubric.md:50`, `docs/common/rubric.md:102`, `docs/common/contracts.md:204`, `docs/common/testing.md:36`.
- 근거: 에이전트의 `responded_with_feedback/help/explain/overclaim`은 평가표의 `feedback/help_now/explain_with_reason/misattributes`와 다르고, `credited_colleague`와 `credits_colleague`도 다르며, `revision/share/open` 근거는 계약의 허용 타입이 아니어서 점수 누락·오판정 또는 422가 발생한다.
- 필요 수정: 카드별 레이블·aux 키·근거 타입을 하나의 표로 확정해 에이전트·평가표·워커·픽스처가 공유한다. `promised_t_min` 등 실제 지표가 요구하는 aux도 빠짐없이 명시한다.

### A3. 저장 이력이 없어 문서 행동을 카드별로 복원할 수 없다

- 위치: `docs/common/data-model.md:15`, `docs/common/data-model.md:16`, `docs/common/data-model.md:19`, `docs/common/contracts.md:111`, `docs/common/contracts.md:199`, `docs/agent/design.md:161`, `docs/api/design.md:63`, `docs/api/design.md:73`.
- 근거: 계약은 자동 저장 때 현재 본문·updated_at만 덮어쓰고 보내기 때만 버전을 만들지만, observe와 AI 재사용 계산은 존재하지 않는 `document_revisions`의 과거 본문·시각을 요구하므로 나중 편집이 앞선 창의 증거를 지우고 미공유 편집도 복원하지 못한다.
- 필요 수정: 관찰에 필요한 저장 이력과 조회 계약을 최소 형태로 추가하거나, 이력이 필요 없는 평가·재사용 규칙으로 명시적으로 바꾼다. 최종본 편집·가져오기도 같은 기준에 포함한다.

### A4. 보드로 분업을 정하는 정상 경로가 없고, 보드와 에이전트 분업 상태가 갈라진다

- 위치: `PRD.md:185`, `docs/frontend/design.md:64`, `docs/frontend/design.md:66`, `docs/common/contracts.md:35`, `docs/common/contracts.md:115`, `docs/agent/design.md:55`, `docs/agent/design.md:81`, `docs/common/rubric.md:90`.
- 근거: 보드 5장으로 분업하라고 안내하지만 tasks는 분업 확정 후에야 생성되고, 공개 task PUT에는 division 확정·최소 조건 검증·work_notes 갱신이 없어 보드만 사용한 결정은 확정되지 않거나 동료의 실제 담당과 어긋난다.
- 필요 수정: 분업 전 보드 초기 상태와 확정 경로를 정하고, 보드 재배정도 division·작업 기억·최소 조건과 일관되게 처리한다. 최초 확정에서 지원자 담당 변경의 task_event를 어떻게 남기는지도 정한다.

### A5. 카드 전에 먼저 계획한 지원자가 계획성 항목을 잃는다

- 위치: `docs/agent/design.md:80`, `docs/common/rubric.md:90`, `docs/common/rubric.md:91`, `docs/common/scenario-model.md:84`.
- 근거: 킥오프 직후 분업 결정을 저장하도록 허용하면서 배정·일정 지표는 L/12 이후 창 안의 확정·변경만 세고 창 밖 보드 근거를 금지하므로, 같은 계획도 먼저 정하면 미충족이 된다.
- 필요 수정: 분업 카드 이전에 유효하게 확정한 계획을 인정하는 시작 상태/근거 예외를 정의하고, 먼저 결정한 경우와 카드 후 결정한 경우의 판정이 같음을 확인한다.

### A6. 다음 창에서 지킨 도움 약속을 기존 관찰에 반영할 수 없다

- 위치: `docs/common/rubric.md:93`, `docs/agent/design.md:85`, `docs/agent/design.md:170`, `docs/common/contracts.md:204`, `docs/worker-infra/design.md:13`, `docs/common/testing.md:40`.
- 근거: 30분 도움 요청에 “50분에 돕겠다”고 하면 45분에 이미 관찰을 저장하는데, 50분 이행 뒤 재평가 경로가 없고 같은 관찰 키의 재저장은 기존 행을 반환하므로 약속을 지켜도 점수가 갱신되지 않는다.
- 필요 수정: 약속 만료/세션 종료 때 해당 지표를 확정하는 방식 등 하나를 정하고, 미래 행동 반영과 멱등 규칙을 함께 정의한다. 창 밖 메시지를 리포트에 표시하는 것만으로는 점수가 고쳐지지 않는다.

### A7. 적응성의 “방향 반영” 항목이 무관한 편집에도 충족된다

- 위치: `docs/common/rubric.md:33`, `docs/common/rubric.md:34`, `docs/common/rubric.md:99`, `docs/agent/design.md:188`.
- 근거: `adapt_applied_to_doc`는 레이블 조건 없이 “카드 뒤 아무 저장/버전 있음”만 보므로 기존 대상 문서의 오탈자 수정도 1점이고, “말없이 반영”은 허용하면서 불만 없음 항목의 근거 타입은 message만 요구한다.
- 필요 수정: 품질 평가를 추가하지 않고 대상 변경을 반영한 사실을 판정 조건에 연결한다. 말없이 반영한 경우에는 문서 근거로도 해당 항목을 증명할 수 있어야 한다.

### A8. 정직 항목의 전제와 미완료 사실 입력이 계산 가능한 계약으로 닫히지 않았다

- 위치: `docs/common/rubric.md:41`, `docs/common/rubric.md:79`, `docs/common/rubric.md:106`, `docs/common/contracts.md:197`, `docs/api/design.md:79`, `docs/worker-infra/design.md:13`.
- 근거: `only_if`의 “동료 공유 문서 있음/미완료 사실 있음/보고 메시지 있음”에 대응하는 facts·metric 이름이 없고, API·워커가 요구하는 “빈 파트”는 honesty_facts 응답의 출처 전용 final_sections에서 확인할 수 없다.
- 필요 수정: 세 전제를 허용 문법으로 명시하고 빈 섹션 등 미완료 사실의 필드를 확정한다. 적응성 미선택 때 `changed_after_adaptability=false`를 미완료로 오인하지 않는 규칙도 필요하다.

### A9. 문서 API 경로와 카드 메시지의 식별·멱등 계약이 연결되지 않는다

- 위치: `docs/api/design.md:73`, `docs/api/design.md:75`, `docs/mcp/design.md:14`, `docs/mcp/design.md:17`, `docs/common/contracts.md:113`, `docs/common/contracts.md:194`, `docs/common/contracts.md:200`, `docs/common/contracts.md:201`, `docs/agent/design.md:24`, `docs/agent/design.md:87`.
- 근거: API/MCP 상세는 `/shared-documents`·`/documents/send`·`GET /tasks`를 쓰지만 계약은 `/docs/shared`·`/docs/send`·`GET /board`이고, send 계약에는 event_id·메시지 seq가 없어 같은 run에서 여러 파트 문서와 반대 의견을 보낼 때 이벤트 귀속·중복 키를 보장할 수 없다.
- 필요 수정: 공개·내부·MCP 경로와 반환 ID를 계약에 맞추고, 문서 카드의 event_id 및 파트별 고정 seq/멱등 규칙을 명시한다. review와 collab_disagree의 각 event_id 메시지 존재 조건까지 연결해 검증한다.

### A10. 허용된 분업에서 책임감의 “동료 영향” 전제가 사라진다

- 위치: `PRD.md:185`, `docs/common/contracts.md:198`, `docs/agent/design.md:122`, `docs/common/rubric.md:26`.
- 근거: 1·2·3번=지원자, 4·5번=동료인 분업은 최소 조건을 충족하지만 2번에 의존하는 3번도 지원자 몫이므로 동료 영향 언급 항목의 상황이 성립하지 않는다.
- 필요 수정: 선택 요소가 요구하는 의존 관계를 분업 조건으로 보장할지, 영향이 없는 경우를 기록 없음으로 처리할지 결정해 PRD·계약·평가표에 함께 반영한다. 같은 채용 건에서 분업 선택만으로 충족 불가능한 항목을 만들면 안 된다.

### A11. 동료 문서 전송 장애를 지원자 미충족으로 계산할 수 있다

- 위치: `docs/common/harness.md:11`, `docs/agent/design.md:194`, `docs/common/rubric.md:31`, `docs/common/rubric.md:92`, `docs/common/rubric.md:69`, `docs/common/contracts.md:87`.
- 근거: 초안 전송 실패를 메시지 폴백으로 done 처리하면서 문서를 못 받은 지원자의 `draft_opened`는 false가 되고, `document_missing`은 평가표 기록 없음 사유/계약에 없어 시스템 장애가 점수 차이를 만든다.
- 필요 수정: 문서 제공 실패 때 영향을 받는 항목의 비적용 처리와 사유를 계약화하거나 필수 카드 실패로 처리한다. 다음 공유에서 누락 버전을 보내는 경우도 원래 카드의 관찰 가능 여부와 연결한다.

### A12. reporting 상태에서 재입장하면 보고를 이어갈 수 없다

- 위치: `docs/common/contracts.md:22`, `docs/common/contracts.md:104`, `docs/common/contracts.md:106`, `docs/frontend/design.md:80`, `docs/common/data-model.md:40`.
- 근거: reporting은 최대 5분 계속되는 사용자 입력 단계지만 resume은 in_progress에만 허용되고 완료 전 debrief_token도 없어, 링크로 재입장해 JWT를 복구하는 정상 경로가 막힌다.
- 필요 수정: reporting의 재입장·토큰 재발급·deadline 복원·허용 채널을 명시하고 보고 대기 중 재연결을 완료 기준에 포함한다.

## 2. 고치면 좋은 것

- **B1. 지연의 원래 예정 시각과 실제 공개 시각을 구분:** `PRD.md:208`은 60분 공유 예정→10분 지연이지만 `docs/common/scenario-model.md:53`과 `docs/agent/design.md:78`은 킥오프 예정 시각에 실제 공개 70분을 넣는다. 현재 문구대로면 60분에 지연을 알릴 이유가 흐려지므로 expected/release 의미를 분리한다.
- **B2. 보고 타이머 시작과 최종 창 끝을 한 규칙으로 명시:** `PRD.md:326`은 보고 요청 뒤 보고/5분이면 종료로 읽히지만 `docs/api/design.md:56`은 110분 요청 뒤 제출까지 기다린다. `docs/common/scenario-model.md:84`의 completed 기준과 `docs/agent/design.md:168`의 submitted_at/ends_at 기준도 달라, 요청 시점·제출 시점·실제 보고 종료 시점 예시를 맞출 필요가 있다.
- **B3. 실제 완료 시각의 영속 원천 명시:** `docs/common/data-model.md:11`에는 completed_at이 없고 `docs/common/contracts.md:191`도 이를 반환하지 않지만 `docs/common/testing.md:39`는 마지막 window_end를 completed 시각과 비교한다. 보고 없는 시간 초과·종료 재시작에서도 같은 시각을 재사용할 수 있는 필드 또는 계산식을 정한다.
- **B4. 스케줄·문서 공유 시각을 클라이언트에 제공:** `docs/frontend/design.md:70`은 공개 예정 시각을 표시하지만 `docs/common/contracts.md:116`·`:131`은 공개 여부만 준다. 선택 요소 수에 따라 공개가 40/60/70분 등으로 달라지므로 고정 01:10 표시는 피한다.
- **B5. 초안의 파트 범위와 버전 번호 통일:** `docs/common/scenario-model.md:68`은 colleague_first의 v1만, `docs/agent/design.md:86`·`:140`은 동료 담당 파트 초안들을 요구한다. 처음 보내는 나머지 파트도 리뷰에서 v2가 되는지, both 골격의 발행 시점은 언제인지 명시한다.
- **B6. 일정 지표의 의미를 항목 문장과 맞춤:** `docs/common/rubric.md:30`은 누가·언제까지·어떤 순서인지지만 `:91`은 order 또는 due_min 변경 하나로 true다. 순서 한 번 이동한 경우를 전부 충족으로 볼지 기준을 좁히거나 문장을 바꾼다.
- **B7. 팀장에게 회사 문서 맥락을 전달할 경로 명시:** `docs/agent/design.md:97`은 회사 문서의 뜻에 답하지만 `docs/common/harness.md:7`의 팀장 입력과 `docs/common/contracts.md:249`의 도구에는 회사 문서 검색/조회가 없다. 필요한 고정 배경을 주입할지 공개 문서 도구를 줄지 정한다.
- **B8. 문서 정합화 잔여:** `docs/agent/design.md:120`의 candidate_role=lead는 `docs/common/scenario-model.md:9`의 primary와 다르다. `docs/frontend/design-direction.md:111`·`:114`의 실제 안내 문구도 주담당으로 고친다. `docs/api/design.md:83`·`docs/frontend/design.md:97`의 422와 `docs/common/contracts.md:44`의 400도 일치시킨다.
- **B9. 이벤트 시점 합격 기준 통일:** `docs/agent/design.md:26`은 fired ±10초·메시지 90초 이내지만 `docs/common/testing.md:31`은 fired→done과 메시지 발생 오차 ±10초를 요구한다. 발생률에서 측정하는 시각과 전달 지연 허용치를 하나로 정한다.

## 3. MVP 과잉·부족

- **유지할 최소 구성:** `docs/common/harness.md:5`의 8요소, `docs/common/contracts.md:218`의 MCP 2개, `docs/worker-infra/design.md:11`의 큐·재시도·승인 재개, `docs/common/contracts.md:14`의 인증은 재설계 뒤에도 남아 있다. 과제 필수 요소의 삭제는 발견하지 못했다.
- **과잉 — 생성 화면 미리보기:** `docs/common/contracts.md:33`은 평가표·타임라인 미리보기를 여전히 요구해 `PRD.md:250`의 뜻/관찰 설명만 표시하는 화면 및 `docs/plan.md:84`의 제외 항목과 충돌한다. 카드 상황·시점을 유추시키는 미리보기는 빼는 편이 MVP 결정과 맞는다.
- **과잉 — 최종본 뒤에 붙이기:** `docs/frontend/design.md:40`의 append는 계약 `docs/common/contracts.md:114`의 전체 복사·단일 source·edited=false로 표현되지 않는다. MVP에서는 덮어쓰기만 남기거나, append 후 내용·출처·edited 처리까지 정의해야 한다.
- **부족 — 관찰 원천과 평가 실패 보호:** A3·A6·A8·A11은 구현 편의 기능이 아니라 점수를 재현하기 위한 최소 데이터/규칙이다. 화면 기능을 더하기 전에 해결해야 한다.
- **부족 — 평가표 대응 수치 정정:** `docs/assignment/evaluation.md:9`의 State 16필드는 `docs/agent/design.md:30`의 18필드와 다르고, `evaluation.md:11`의 business 조회 4·변경 6은 `docs/common/contracts.md:224`부터의 조회 4·변경 7과 다르다. 필수 요소는 있으나 제출 증거표의 수치를 갱신해야 한다.

## 4. 개발 순서·소유권의 위험

- **D1. 병렬 트랙 사이 연결 책임 공백:** `docs/plan.md:21`·`:22`는 web(mock)과 scenario(백엔드)의 개별 통과만 요구하고, `:25`·`:66`의 web-polish는 UI 내부만 맡으므로 새 API와 실제 화면을 연결할 담당이 없다. e2e-runner 소유(`:67`)에도 앱 수정 권한이 없다. web 통합 담당과 “실 API로 문서 공유→열람→통합→제출→보고→리포트” 완료 기준을 명시한다.
- **D2. scenario-redesign의 필수 변경 파일이 소유권에서 빠짐:** `docs/plan.md:65`는 scenario·라우터·모델·worker rubric만 명시하지만 reporting은 SessionService·scheduler·runs 경계, 새 도구는 business-mcp, 버전 고정은 version.py/색인 경계 변경이 필요하다(`docs/api/design.md:31`, `:44`, `docs/common/contracts.md:231`, `docs/common/scenario-model.md:39`). `docs/plan.md:70`의 중지 규칙과 충돌하지 않게 파일 단위 이관/후속 담당을 지정한다.
- **D3. prompts와 카탈로그 본문 소유권 중복:** `docs/plan.md:58`은 prompts에 미션 prompts와 카드 문구를, `:65`는 scenario-redesign에 missions 전체를 준다. `:23`은 옛 prompts 완료를 의존으로 보지만 새 7카드 프롬프트 완료 기준은 `:22`의 test/lint뿐이다. 재설계 기간 문구 소유자를 하나로 정하고 레이블·선점 금지·팀장 DM 규칙 검증을 인수 조건에 넣는다.
- **D4. UI 확인 이후 개발이라는 결정과 병렬 착수가 충돌:** `docs/prd-change-proposals.md:102` 및 `docs/decisions.md:108`은 사용자 mock 확인 뒤 코드를 요구하지만 `docs/plan.md:40`은 scenario-redesign을 동시에 실행한다. 병합만 나중에 하는 것과 개발을 나중에 하는 것은 다르므로 사용자 확인이 막는 범위를 먼저 확정한다.
- **D5. 기준 문서가 서로 다른 정본을 유도:** `docs/mcp/design.md:29`는 catalog.yaml+documents 해시, `docs/common/scenario-model.md:39`는 미션 폴더 전체(프롬프트 포함) 해시다. `docs/plan.md:55`의 version.py 소유권과 함께 하나의 함수·정의로 닫아, 같은 채용 건의 프롬프트/색인 버전 고정이 깨지지 않게 한다.
- **D6. 완료 기준은 핵심 반례를 포함해야 함:** `docs/plan.md:22`의 test/lint와 시점 계산만으로는 A1~A12를 검증하지 못한다. 정상 문서 왕복에 더해 보드만으로 분업 확정, 카드 전 계획, 창 밖 약속 이행, 무관한 편집, 문서 제공 실패, reporting 재접속을 해당 계약의 최소 테스트로 배정한다. 별도 전수 조합 테스트는 필요 없다.
