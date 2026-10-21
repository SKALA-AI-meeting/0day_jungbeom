# 브리프: 토론형 전환 (debate-pivot)

2026-10-21 사용자 결정. Day Zero의 과제를 "AI 동료와 2시간 업무 하루(기획안 작성)"에서 **"지원자 + AI 동료 3명의 채팅 토론으로 키워드 → 문제 상황 → 해결책을 합의하고 최종 기획안을 제출"**하는 형태로 바꾼다. 서비스의 목적(행동 관찰로 인성을 보고, AI는 기록하고 사람이 판단)은 그대로다. **핵심은 채팅 과정에서 지원자의 인성이 잘 분석되는 것이고, UI와 도구는 거기에 맞춘다.**

이 브리프가 이번 문서 개편의 정본이다. 기존 결정 F1~F12(원문은 git 33cfe90)와 업무 시뮬레이션 전용 내용(루프랩·모아런, 5섹션 브리프, 분업·보드·파트 문서, 팀장 한서윤, 10:50 압박 DM, 자료 지연 등)은 **대체**된다. decisions.md에는 대체 사실을 기록하고, 대체된 이전 결정 절은 "대체됨" 한 줄 요약으로 줄인다(원문은 git 33cfe90).

## 확정 결정

| ID | 결정 |
|---|---|
| D1 참여자 | 지원자 + AI 동료 3명 = 4명. 모두 동등한 참여자이고 진행자 없음. 시스템 안내 메시지가 "지금 할 일"과 남은 시간만 알린다. 팀장 캐릭터 없음 |
| D2 단계와 칸 | 단계는 **키워드 → 문제 상황 → 해결책 → 기획안 작성** 4개. 앞 3단계는 합의 패널의 칸 하나씩. 합의해서 칸을 채우고 확정하면 다음 단계로 넘어간다. 칸은 누구나(지원자·AI 동료) 채울 수 있다. 합의가 분명한데 아무도 안 채우면 AI 동료가 채운다. 단계 시간이 다 되면 AI 동료가 "시간이 다 돼서 가장 지지가 많았던 X로 할게요"라며 채우고 넘어간다. 칸마다 **합의/시간 초과**와 **누가 채웠는지**를 기록한다 |
| D3 공정성 | MVP: 채용 건마다 키워드 후보(예: 물·불·나무·바람)와 각 AI 동료가 단계마다 처음 미는 안을 **고정**(키워드별 문제·해결책 안을 미리 준비). 말투만 LLM이 자유롭게. 지원자가 후보 밖 의견을 내도 된다. 고도화(MVP 이후): 페르소나 성향에 따라 입장을 즉흥 생성 |
| D4 인성 요소 | 토론형 5요소: **설득/논리력**(내 안과 다른 안이 경쟁 → 근거를 들어 말하는가), **경청/존중**(고집형 동료가 강하게 밀어붙임 → 무시·비난 없이 대응하는가), **배려/포용**(조용한 동료가 의견을 못 냄 → 말할 기회를 주는가), **수용/유연성**(내 안이 채택되지 않음 → 승복하고 다음 단계에 기여하는가), **정직/공정**(최종 기획안 제출 → 남의 아이디어를 남의 것으로 적는가). 기업은 채용 건마다 1~5개 선택 |
| D5 페르소나 | 풀 5종: 고집형, 조용한 소극형, 비판형(반대 역할), 동조형, 발산형(아이디어 많음). 세션에는 3명. **선택된 요소가 페르소나를 정한다**(경청/존중 → 고집형, 배려/포용 → 소극형 필수), 남는 자리는 풀에서 채운다. 페르소나 유형은 지원자에게 보이지 않고 이름만 보인다 |
| D6 수용 카드 | 수용/유연성이 모든 지원자에게 일어나도록, 정해진 한 단계(기본: 문제 상황)에서 AI 동료 다수가 지원자 안과 다른 안을 지지한다 |
| D7 최종 기획안 | 지원자가 혼자 쓰고 제출. AI 동료는 채팅으로 기여(물어보면 내용 제공, 초안에 의견). 합의 패널은 단계별로 고른 결과만 짧게 쌓이고, **최종 기획안은 그 결과를 바탕으로 보고서 형태로 쓰는 별도 문서**. 템플릿: 키워드 · 문제 상황 · 해결책 · 근거 · 기대효과 · 아이디어 기여. 제출 → 디브리핑 |
| D8 세션 길이 | 60분: 키워드 10 · 문제 상황 20 · 해결책 20 · 기획안 작성 10. 일찍 확정하면 남은 시간은 다음 단계로 넘어간다. 데모용 압축(6분)은 같은 비율. 오피스 시계 표시는 유지(같은 비율 매핑) |
| D9 자료·어시스턴트 | 키워드별 참고 자료 세트(예: 물 → 물부족 통계·사례)를 두고 키워드가 확정되면 그 키워드 자료만 자료 탭에 열린다. AI 동료는 주장할 때 자료를 근거로 인용. 지원자는 AI 어시스턴트로 검색·요약. AI 활용은 기존처럼 점수 없이 사실 기록 |
| D10 멀티 에이전트 | MVP: **턴 매니저 + 페르소나 에이전트 3**. 지원자 메시지·타이머·카드 시점마다 턴 매니저가 규칙+LLM으로 누가 말할지(0~2명) 정하고, 페르소나 에이전트(자기 입장·기억·도구 허용 목록)가 발언. 고도화: 독립 비동기 에이전트로 자율성 확대 |
| D11 MCP 3개 | **debate-mcp**(손, business-mcp를 재정의): 토론 상태 조회·변경(get_debate_state, get_transcript, post_message, propose_option, set_stance, fill_slot, get_draft 등). **rag-mcp**(눈): 확정된 키워드의 자료만 검색(search_materials, get_material), 확정 전 자료 차단. **assessment-mcp**(기록자, 신규): record_observation, get_transcript_span, get_rubric, get_contributions(누가 어떤 아이디어를 처음 냈는지), 행동 코드 저장. **페르소나 에이전트는 assessment-mcp에 접근 불가**(평가 기준을 보고 행동을 맞추지 못하게, Harness 근거). 턴 매니저(결정적 노드)와 report-worker만 사용. scenario-mcp·웹 검색 MCP·가드 MCP는 두지 않는다(이유: 카탈로그는 debate-mcp로 충분, 웹 검색은 공정성·재현성 훼손, 출력 검사는 코드에서 무조건 실행해야 함) |
| D12 침묵 초대 | 지원자가 일정 시간 말이 없거나 현재 단계에서 의견을 안 냈으면 어울리는 페르소나(동조형·발산형 등, 고집형 제외)가 "OO님은 어떻게 생각하세요?"라고 묻는다. 단계당 최대 1회. 지원자 발언은 **자발 / 초대 후**로 구분 기록 |
| D13 화면 | 가운데 토론방, 우측 패널(탭: 합의 · 자료 · AI 어시스턴트 · 기획안), 상단 단계 진행바와 남은 시간. **세부 UI/UX 구조는 열린 항목**(3단계 UI/UX 디자인에서 시안으로 정함): 합의·확정 흐름(혼자 확정, 오클릭, 단계 전환 연출), 기획안 작성 화면, 기업 리포트 화면 |
| D13-1 채팅 표시 | 메시지마다 보낸 사람 **이름**(+이니셜 아바타)을 표시한다. 참여자 4명은 **말풍선 배경색을 사람별로 구분**해 누가 말했는지 한눈에 보이게 한다(지원자 본인 색은 따로, 시스템 안내는 중립 배경). 색은 디자인 토큰으로 정의하고 라이트·다크 모두 본문 대비를 지킨다. 색만으로 구분하지 않도록 이름은 항상 함께 보인다 |
| D13-2 디자인 컨셉 | **Apple스러운 디자인**(2026-10-21 사용자 결정, 지금 UI가 너무 'AI스럽다'는 피드백). 원칙: 넓은 여백과 분명한 위계(크고 굵은 제목, 차분한 본문), 흰색·연회색(#F5F5F7류) 바탕에 시스템 블루 계열 강조색 하나, 시스템 폰트 스택(-apple-system, SF Pro 계열) + 한글 Pretendard, 일관된 둥근 모서리와 얇은 구분선, 반투명(vibrancy)은 상단 바·패널 등 최소한으로, 절제된 부드러운 전환 애니메이션. 채팅은 iMessage처럼 말풍선 중심(지원자 본인은 오른쪽 강조색, AI 동료 3명은 Apple 시스템 색의 연한 틴트로 사람별 구분, 시스템 안내는 가운데 작은 회색 텍스트). **피하는 것**: 보라·파랑 그라데이션, 반짝이(✨)·로봇 아이콘, 글래스모피즘 남용, 네온, 과한 그림자, 카드만 반복되는 대시보드 느낌. 라이트·다크 모두 지원 |
| D13-3 이름·프로필 | 페르소나 풀은 5명이고 세션에는 그중 **AI 동료 3명**만 나온다. **지원자는 페르소나가 아니며 자기 표시 이름을 쓴다**: 입장(동의) 화면에서 표시 이름을 입력하고(기본값은 초대 시 이름, 수정 가능), AI 동료는 대화에서 "OO님"으로 부른다. 기업 리포트는 기존 원칙대로 별칭 표기 가능. **페르소나마다 고정 프로필 이미지**가 채팅 말풍선 옆·참여자 목록에 보인다(실존 인물 사진이 아닌 일관된 스타일의 일러스트/그래픽 아바타, 미션 카탈로그의 정적 에셋, 페르소나 유형을 암시하지 않는 중립적 표정·스타일). 지원자는 이니셜 아바타. **지금 이미지는 임시(placeholder)이고 나중에 팀이 원하는 사진으로 교체한다**: 이미지는 파일 경로만 바꾸면 되도록 미션 카탈로그의 `avatar` 필드와 정적 에셋 폴더로 분리하고, 코드·스타일이 특정 이미지 비율·화풍에 의존하지 않게 한다(원형 크롭, 고정 크기). 계약·데이터에는 자리별 `display_name`·`avatar_url`(지원자는 `display_name`)이 필요하다 |
| D14 합의 패널 | 단계마다 고른 결과만 짧게 쌓인다("키워드: 물 ✓ 합의 09:08"). 후보안·지지 현황은 화면에 보이지 않고 토론은 채팅으로만. 현재 단계 칸에만 입력과 [확정] |
| D15 채널 | 토론방 하나. DM 없음 |
| D16 의도 분류 | 지원자 메시지마다 작은 모델이 {의도: 제안/동의/반대/질문/기타, 대상 안}을 실시간 분류해 토론 상태(안별 지지자)에 누적. 턴 매니저 판단과 시간 초과 시 안 선택에 사용. 실패하면 '기타'로 두고 진행. AI 동료 입장은 시스템이 정하므로 이미 안다 |
| D17 응답 타이밍 | 턴 매니저가 화자를 정하면 "OO님이 입력 중…" 표시 후 완성 문장을 한 번에 게시. 여러 명이면 1~3초 간격 순차. 지원자가 입력 중이면 끼어들지 않고 기다림. 토큰 스트리밍 없음(금지 문구 검사와 충돌) |
| D18 분석 | **발언별 행동 코드 + 평가표 집계**. 지원자 발언마다 앞뒤 맥락을 보고 행동 코드(예: 근거 제시, 타인 의견 인용·요약, 인정, 반박, 무시, 비난, 발언 기회 제공, 승복, 다음 단계 기여 등)를 붙인다. 요소별 점수는 공개된 평가표 규칙으로 코드를 센 값이고 근거는 해당 메시지 원문. 카드 상황 반응은 카드에 연결. 사실 지표(발언 수, 자발/초대 후 비율, 응답 간격 등)도 함께. **리포트는 담당자가 평가할 때 보는 참고 자료**이고 합격·불합격·순위는 만들지 않는다. 정직/공정은 제출 기획안의 "아이디어 기여" 칸을 assessment-mcp의 get_contributions(실제 최초 제안자)와 대조 |
| D19 분석 시점 | 행동 코드는 **세션 종료 후 report-worker가 큐 작업으로 일괄** 부여(assessment-mcp로 저장, 실패 시 재시도). D16 실시간 의도 분류는 토론 진행용으로 별도 유지 |
| D20 코드 정리 | main에서 제자리 개편. 살림: 인증, WS, 큐, report-worker, RAG, 채팅 UI·탭·Markdown 뷰어. business-mcp → debate-mcp(이름·도구 교체), assessment-mcp 신규 서비스. 삭제: 보드·분업·파트 문서·팀장 이벤트 코드. `track/flow`(G1 픽스처)와 남은 워크트리는 정리 대상 |
| D21 구현 우선순위 | 1순위: 지원자 토론 세션 끝까지(4단계·페르소나 3·카드·제출) → 행동 코드 분석 → 기업 리포트 화면. 2순위: 기업의 채용 건 생성(요소 선택)·초대. 6분 데모 모드 |

## 기본값으로 정한 것

- 가상 설정: 루프랩·모아런 삭제, "새 프로젝트 팀"으로만 둔다.
- 유지: 오피스 시계, 디브리핑, 90일 보관, 금지 문구 검사(재생성 1회 → 안전 문구), 행동 유도 금지(F9 원칙: 화면 안내와 에이전트 문구는 기능 설명만), 인증(기업 관리자 / 초대 링크 지원자), 담당자 조정.
- 삭제: 보드, 분업안, 파트 문서·버전, 10:50 압박 DM, 자료 지연, 방향 변경 카드, 팀장 DM, reporting 관련 잔재.
- Harness 추가 규칙: AI 동료는 합의 전에 칸을 채우지 못한다(결정적 검사), AI 동료가 지원자 대신 결론을 내리거나 평가·판정 발언을 하지 않는다, 시간 초과 폴백, 페르소나의 assessment 접근 차단.
- 카드 배치(초안, 시나리오 문서에서 구체화): 키워드 단계 = 설득(경쟁 안), 문제 상황 단계 = 수용(다수가 다른 안) + 경청(고집형 압박), 해결책 단계 = 배려(소극형 침묵) + 설득, 기획안 작성 = 정직(기여 귀속). 선택 안 된 요소의 카드는 빠지고 흐름은 남는다.

## 개발 순서 (사용자 지정)

1. md 문서 전체 수정 → 1-1. 이를 기반으로 계획 문서(plan.md, handoff.md) 수정
2. 아키텍처 html(`docs/share/architecture.html`) 수정
3. UI/UX 디자인 수정 — **보고서용 목업 UI**(apps/web, 목업 데이터로 동작, 캡처 가능)
4. 서비스 간단 설명 + 아키텍처 + 주요 기능 및 구현 결과(UI 캡처)를 담은 HTML → A4 PDF 보고서
5. 나머지 개발(백엔드 개편과 실제 연결, 테스트)

계획은 **병렬 작업이 가능한 구조**로 짠다(트랙별 파일 소유권 분리, 공유 계약 먼저 고정, 웨이브와 게이트). 작업 방식: 오케스트레이터는 조율만 하고, 작업은 서브에이전트가 병렬로, 리뷰는 `codex exec`(pane 없음)로 돌린다.

## 시나리오 초안 (문서 작성자가 만든다)

키워드 후보 세트(4개)와 키워드별 문제 상황 후보·해결책 후보, 페르소나 5종의 이름·말투·단계별 고정 입장, 단계별 카드 배치·트리거, 행동 코드 목록과 정의, 요소별 평가표 규칙(코드 → 점수, 근거 조건), 침묵 초대 조건, 시간 초과 규칙. 사용자 검토 대상이므로 결정과 초안을 구분해 "초안" 표시를 한다.

## 웨이브 1 이름 정리 (오케스트레이터 결정)

웨이브 1 문서 사이 충돌은 아래로 통일한다. 이름의 정본은 `docs/common/contracts.md`(도구·이벤트·상태·경로), `docs/common/data-model.md`(테이블), `docs/common/scenario-model.md`(페르소나·카드·키워드·단계 규칙), `docs/common/rubric.md`(행동 코드·조건·지표)다.

- 칸 결과 필드: `resolution: consensus | timeout` (contracts/data-model의 `mode: agreed|timeout`은 이것으로 바꾼다)
- `filled_by`: `candidate | p1 | p2 | p3` (자리 id, 시간 초과도 공지한 자리 id. `system` 값은 없다). 페르소나 유형 id(stubborn 등)는 지원자에게 노출되는 곳에 쓰지 않고 `positions.scenario.seats`에서 자리와 매핑
- 행동 코드 저장: 워커는 `save_behavior_codes`, 카드 발동 기록은 턴 매니저 결정적 노드의 `record_observation`
- 자동 제출: `proposals.auto_submitted` bool + WS `session.ended{reason: timeout}` (scenario-model의 `submitted_by: timeout` 대체)
- 디브리핑 원천: `observations`(삭제된 `session_events` 참조 금지)
- 오피스 시계: 60분 세션 = 09:00~10:00, `09:00 + t_min × 60 / session_minutes`
- 서비스 디렉터리: `services/debate-mcp/`(business-mcp 이름 변경), `services/assessment-mcp/`(신규). env `ASSESSMENT_MCP_TOKEN`, 역할별 모델 env `MODEL_PERSONA`·`MODEL_TURN`·`MODEL_INTENT`·`MODEL_ASSISTANT`·`MODEL_REPORT`
- 지원자 호칭: "지원자"(대화 속에서는 "OO님"). "주담당" 호칭은 폐기

## D18·D19 개정: 행동 기준 척도(BARS) + 평가 에이전트 (2026-10-21 사용자 결정)

기존 D18(발언별 행동 코드를 평가표 규칙으로 센 점수)을 대체한다. 이유: 코드 개수로 세는 방식은 토론의 미묘한 행동을 놓친다. 평가표와 채팅 결과를 읽고 판단하는 것도 에이전트이므로 판단 자율성을 준다.

- 요소마다 **하위 차원 3~4개**, 차원마다 **1~5 수준과 수준별 대표 행동(앵커)**을 둔다(BARS). 앵커는 이 토론 시나리오의 실제 장면·예시 발언으로 쓴다.
- **평가 에이전트**(report-worker 안, 세션 종료 후 큐 작업)가 대화 전체·칸 기록·기획안·카드 발생 기록을 읽고 차원마다 `{level 1~5 | 기록 없음+사유, evidence_message_ids(1개 이상), rationale, confidence: high|medium|low}`를 낸다. 요소 수준은 차원 수준을 담당자가 읽기 쉽게 요약한 값(평균 반올림 + 서술 한두 줄)이다.
- 원칙 개정: "AI는 점수를 매기지 않는다" → **"AI 평가 에이전트가 공개된 척도로 근거를 들어 수준을 판단하고, 담당자가 그것을 참고해 최종 평가한다"**. 합격·불합격·지원자 간 순위는 여전히 만들지 않는다. 담당자는 차원 단위로 조정하고 메모를 남긴다.
- 사실 지표(발언 수, 자발/초대 후, 칸 기록, 아이디어 최초 제안자 등)는 결정적 계산으로 그대로 두고 평가 에이전트의 입력·리포트 보조로 쓴다. 행동 코드 20개는 독립 산출물에서 빠지고, 필요하면 앵커 작성의 참고 어휘로만 남긴다.
- 일관성 장치: 같은 척도·같은 프롬프트·낮은 temperature, 근거 없는 수준 금지(근거 메시지 없으면 기록 없음), 확신도 low는 리포트에 표시, 파일럿에서 사람 평가와 일치도 측정.
- assessment-mcp 도구 `save_behavior_codes`는 `save_evaluation`으로 바뀐다(정확한 입출력은 contracts.md에서 정한다).
- 리포트 그래프 노드 이름: `collect → aggregate(사실 지표) → evaluate(평가 에이전트) → draft → interrupt → finalize`. 기존 `code` 노드는 없앤다.
- 평가 실패 사유: `evaluate_failed`(화면 문구 "시스템: 판단 실패"). 기존 `classify_failed`(행동 코드 분류 실패)는 대체. 실시간 의도 분류 실패는 기존대로 의도 `other` 처리.
- PRD 11장 평가 일치도 통과 기준(사람 평가와 ±1 이내 80%)은 잠정값.
- 평가 입력 범위(사용자 확인): 평가 에이전트는 **세션 대화 전체**(+칸 기록·기획안·카드 발생·사실 지표)를 읽고 차원마다 판단한다. 카드 관찰 창은 "핵심 장면"을 가리킬 뿐이고, 판단은 세션 전체의 흐름(일관성, 장면 전후의 변화, 반복 패턴, 카드 밖 자연스러운 행동)을 함께 본다. `get_transcript_span`(앞뒤 몇 개 메시지)은 판단 입력의 한계가 아니라 **리포트에서 근거 메시지의 앞뒤 맥락을 보여 주는 용도**로만 쓴다(기본 앞 5·뒤 3으로 통일).

## 평가 결과 계약 (오케스트레이터 결정, BARS 통합 후)

rubric.md(BARS, 차원 19개)가 정본. 다른 문서는 아래 이름으로 맞춘다.

- 행동 코드 산출물 폐기: `behavior_codes` 테이블, `BehaviorCodeUnit`, `save_behavior_codes`, `/behavior_codes` 경로, `/rubric` 응답의 `behavior_codes`·`conditions`, 리포트의 `rubric.items`(조건 id·auto 1/0·basis·codes)·`met`·`unmet`·`total_score`·`auto_total`을 모두 없앤다. **총점·합계 없음**.
- assessment-mcp 도구: `get_rubric`, `get_session_record`(신규: 평가 입력 묶음 = 대화 전체·칸 기록·기획안 제출본·카드 발생 observations·사실 지표·Contributions), `get_transcript_span`(리포트 근거 맥락 표시용, 기본 앞 5·뒤 3), `get_contributions`, `record_observation`(턴 매니저 카드 발생), `save_evaluation`(워커). report-worker 허용 목록: get_rubric, get_session_record, get_transcript_span, get_contributions, save_evaluation.
- `save_evaluation` 입력: `{session_id, run_id, rubric_version, prompt_version, model, dimensions:[{dimension_id, level:1~5|null, no_record_reason?, evidence_refs[], rationale, confidence:high|medium|low|null}], elements:[{element, level, summary, dimension_count, no_record_count}]}`. 멱등 키 `(session_id, run_id)`. 요소 level은 워커가 차원 평균 반올림(.5 올림)으로 계산, summary는 에이전트 작성.
- 근거 참조 형식(`evidence_refs[]` 문자열): `msg:<message_id>`, `slot:<phase>`, `proposal:<field>`, `contribution:<option_id>`(맥락용, 개수에 안 셈).
- 기록 없음 사유: `no_activity | evaluate_failed | not_applicable | event_not_fired | auto_submitted_blank`.
- 테이블: `evaluations`(session_id, dimension_id, level, no_record_reason, evidence_refs jsonb, rationale, confidence, rubric_version, prompt_version, model, run_id, created_at; UNIQUE(session_id, dimension_id, run_id)). 요소 요약은 `reports.content.elements[]`. 담당자 조정 `rubric_adjustments`는 차원 단위 `(session_id, dimension_id, level|null, no_record_reason?, memo NOT NULL, adjusted_by, adjusted_at)`.
- 리포트 응답: `elements[]`(element, level, summary, adjusted_level?), `dimensions[]`(위 차원 필드 + adjusted_level?·adjust_memo? + 근거별 원문·오피스 시각·앞뒤 맥락), `facts`, `contribution_check`(안별 실제 최초 제안자 / 기획안에 적힌 기여자), `seats[]`, `slots`, `debrief`.
- `POST /admin/sessions/{id}/review`: `adjustments:[{dimension_id, level|null, no_record_reason?, memo}]`(memo 필수), 승인.
- 평가 호출: 요소마다 별도 LLM 호출, 다른 요소 결과는 입력 안 함, temperature 0~0.2, `MODEL_REPORT`. 워커 검증 실패(근거 없음 등)면 그 차원 1회 재시도 → 실패 시 `evaluate_failed`.
- 화면: 요소 "수준 N (1~5)", 차원별 확신도, low는 "근거 약함, 원문 확인 권장". 지원자 목록은 요소별 수준 칩 + low 차원 수, 정렬 없음. 조정은 차원 단위·메모 필수.

## 2단계 아키텍처 html 지침 (사용자 피드백, 2026-10-21)

- 현재 `docs/share/architecture.html`의 **전체 구성도 그림이 좋다는 평가**를 받았다. **그림 스타일과 페이지 디자인은 유지**하고 내용만 토론형으로 바꾼다.
- **중복되는 내용은 뺀다.** 같은 정보를 여러 뷰에서 반복하지 않는다(예: 티어별·레이어별 뷰가 구성도와 겹치면 합치거나 줄임).
- 중심은 네 가지: **설계 아키텍처(전체 구성도), 에이전트 구성과 역할(턴 매니저·페르소나 3·의도 분류·어시스턴트·평가 에이전트), 흐름(토론 세션·단계 전환·평가 파이프라인), MCP 역할(debate=손·rag=눈·assessment=기록자, 접근 경계)**. Harness는 이 흐름 안에서 필요한 만큼만.
- 기존 "6개 뷰 한 페이지" 구성은 위 네 가지 중심으로 재구성해도 된다(뷰 개수 고정 아님).

## UX 결정 (G-U, 2026-10-21 사용자: 모두 추천안)

`docs/review/ux-options.html`의 ★ 추천안으로 확정한다.
1. 혼자 확정: A 합의 여부와 상관없이 늘 같은 확정 흐름(판단은 평가가 함)
2. 오클릭 방지: A 확인 창 하나
3. 키워드 칸 입력: A 후보 4개 분절 버튼
4. 단계 전환 연출: A 진행바 이동 + 결과 줄 강조 + 가운데 회색 시스템 안내
5. 기획안 단계 진입: A 우측 탭이 기획안으로 자동 전환
6. 기획안 작성 화면: A 탭 안 6칸 세로 폼
7. 기업 리포트 구조: A 한 열 문서
8. 리포트 근거 보기: A 차원 아래 근거 목록 펼침(맥락 앞 5·뒤 3)
9. 라이트·다크: A 시스템 설정만 따름
10. AI 동료 틴트: A 자리 고정

## 리뷰 반영 결정 (2026-10-21, 기획자·지원자·시니어 엔지니어 리뷰 후)

- **R1 수용 카드 강도 완화 (D6 개정)**: 문제 상황 단계의 다수 고정을 "고집형 1명(확정 전 불변) + 다른 1명"으로 줄이고, 다른 1명은 설득 가능 규칙(지원자 반대·대안 2회)을 따른다. 지원자 안이 채택될 수 있다. 지원자 안이 채택되면 수용 요소는 기록 없음(`not_applicable`). 수용 차원 앵커에 "근거 있는 이의 제기도 높은 수준"을 명시. 동의 화면에 형식 안내 "토론 결과가 내 제안과 다를 수 있고, 안의 질은 평가하지 않으며 그 과정의 태도를 본다". 디브리핑 첫 문장은 "같은 채용 건의 모든 지원자가 같은 장면을 겪었고, 정답 없이 반응을 본다"로 시작하고 이의 제기 경로를 함께 준다. 리포트에는 담당자용으로 "설계된 장면"임을 표시.
- **R2 요소 5개 고정 (D4·D5 개정)**: 기업의 요소 선택(1~5개) 기능을 MVP에서 뺀다. 모든 세션이 5요소·카드 6장을 쓴다. 세션 페르소나는 **고집형(강한결)·소극형(윤하람)·비판형(서지안) 3명 고정**. 동조형·발산형과 "요소 미선택 시" 규칙, 요소→페르소나 결정 규칙은 MVP 이후 확장으로 문서에만 짧게 남긴다. 채용 건 생성 화면에서 요소 선택 UI 제거(세션 길이 등만). 키워드 4개·차원 19개는 유지.
- **R3 시간 (D8 개정)**: 60분 = 키워드 10 · 문제 상황 18 · 해결책 18 · 기획안 작성 14. 남은 시간 이월 유지. 데모·e2e 압축은 6분 → **15분**(같은 비율, 시각 오프셋 최소 20초). 시간 로직은 가짜 시계(주입) 단위 테스트로 검증하고 실 스택 e2e는 15분으로 1~2개.
- **R4 AI 합의 채우기 (D2 개정)**: 유지하되 의도 분류 출력에 `confidence: high|low`를 추가하고, high인 agree·propose만 지지로 센다. 합의 대기 1분(L/60)은 없앤다: 지원자 포함 3/4 지지가 되는 즉시 AI가 "그럼 X로 정리할게요"로 채운다. 의도 분류 eval(20문장)은 G-F 전에 실 모델로 정확도 기준선을 잰다.
- **R5 기술 단순화 (오케스트레이터 결정, 시니어 엔지니어·Codex 리뷰 반영)**
  1. 동시성: 세션 Lock·`lock_held`·`handled` 집합을 없애고 **세션별 메일박스**(asyncio Task 1개가 자극 큐를 직렬 소비)로 바꾼다. 지원자 메시지 저장 시(큐 밖) `sessions.generation` +1, 그래프는 게시 직전 generation이 바뀌었으면 남은 화자를 버린다. `advance_phase`는 `phase_started`를 큐에 넣기만 한다. 멱등은 `agent_runs.status` + DB 멱등 키만. 오래 걸린 run 재실행 기준 = 역할별 타임아웃 합 + 여유(200초).
  2. 시간 초과: 그래프가 아니라 **api가 결정적으로 직접** 채운다(선택 규칙 + 시나리오 고정 문장, 우선순위 자리 이름으로 게시). 그래프 자극에서 `timeout` 제거.
  3. 그래프 자극은 4종: `message`, `phase_started`, `idle`(지원자 침묵만, `room_quiet` 삭제), `card_due`. 침묵 초대는 단계별 `invite_delivered` 플래그로 추적하고, 스케줄러가 매 틱 조건을 다시 보고 미전달이면 다시 enqueue(같은 단계에 대기 중인 idle이 있으면 중복 enqueue 안 함).
  4. 카드 트리거는 **시각 기반 `card_due` 하나로 통일**(카드별 `offset_min`, 최소 20초). 이벤트 트리거 삭제. 카드는 담당 화자가 실제로 게시했을 때 `delivered`로 기록(observation은 첫 카드 발언 게시 뒤). 미전달 화자는 다음 run에서 이어서 말한다. 기준안(문제 상황 lead option)은 `card_due` 시점에 "지원자가 현재 지지하는 안이 아닌 첫 시나리오 안"으로 계산해 **잠근다**. 카드 전에는 고집형도 입장을 밝히지 않고 일반 발언만 한다.
  5. 칸 상태는 `empty | confirmed` 두 개. `filled`·`PUT slots`·`slot.filled` 삭제. 키워드 칸은 버튼(옵션 키)으로 확정. 문제·해결책 칸의 지원자 확정 값은 의도 분류가 만든 안 목록과 **정규화 문자열 일치** 또는 카탈로그 키로만 연결하고, 아니면 option_id null(확정 경로에 LLM 없음).
  6. 의도 분류 입력에 현재 단계의 **카탈로그 안 전체(아직 발언 안 된 것 포함)**를 넣어, 지원자가 카탈로그 안을 먼저 말하면 그 `scenario_option_key`로 같은 option_id를 만들고 proposer=candidate. 이후 AI가 같은 안을 propose해도 같은 행을 쓴다(최초 제안자 보존).
  7. 현재 지지: 참여자×안별 마지막 입장. 같은 안에 대한 후속 `oppose`는 지지를 철회한다.
  8. 페르소나가 계획 밖 입장을 내면 응답 전체를 1회 재생성, 실패하면 계획과 맞는 고정 문구로 교체(게시 문장과 입장 일치 검증).
  9. typing: 클라이언트는 입력 중 5초마다 `typing` 갱신, 서버는 6초 갱신이 없으면 만료. 그래프는 최대 10초 기다리고 그래도 입력 중이면 게시하지 않고 자극을 다시 큐에 넣는다.
  10. WS: 프레임 봉투에 세션 단위 `seq`, 세션별 단일 송신 큐로만 보낸다. 클라이언트는 seq가 비면 `/state` 재조회.
  11. 비용: 세션 예산은 달러로 관측(목표 $0.5). 토큰은 관측만, 세션 중 응답 중단 없음. 하드 상한 $2를 넘으면 페르소나는 고정 안전 문구만.
  12. 턴 LLM은 규칙 결과가 0명이고 자극이 `message`일 때만 호출. 페르소나 컨텍스트에 DebateState를 미리 넣어 조회 도구 왕복을 줄인다.
  13. 어시스턴트는 **tool-calling 루프**(`search_materials`·`get_material`, 최대 3회, 인용 포함)로 바꾼다(모델의 도구 선택 시연).
  14. 평가: api는 형식·세션 소속만 검증, 판단 규칙 검증은 워커. 확신도 상한 위반은 거부하지 않고 워커가 깎는다(clamp). 재요청은 형식 오류·근거 부재일 때 **요소 단위 1회**(이전의 "차원 단위 1회"를 대체) → 실패 차원은 `evaluate_failed`. 전송·타임아웃 실패는 저장하지 않고 큐 재시도. `evaluate_failed`가 섞인 결과는 리포트 재생성 때 새 run_id. 요소 요약은 `save_evaluation` 본문의 `elements`와 함께 DB에 저장(`evaluation_runs` 테이블: session_id, run_id, rubric_version, prompt_versions jsonb(요소별 해시), model, elements jsonb, created_at). `prompt_version` 단일 필드는 `prompt_versions` 맵으로.
  15. final 리포트는 draft content를 그대로 저장(해시 동일), 담당자 조정은 조회 시 병합.
  16. review 요청 필드는 `reviewer_name`, 검증 오류는 422 `invalid_input` 계열(계약 오류 코드 체계).
  17. BARS 단독 확정: 확정 행위는 `flex_decision_respect`가 판단, `flex_acceptance`는 결정 후 행동만(결정 후 발언 없으면 `no_activity`).
  18. 자료 원문도 `catalog_version`별로 DB에 시드해 목록·검색·본문이 같은 버전을 쓴다.
  19. 입장 응답에 `session_id`·초대 이름(표시 이름 기본값), consent·resume 응답에 `session_id`. 시작 전 `/state` 조회 허용(참여자 이름·아바타 포함).
  20. 초대 재발급: `POST /admin/sessions/{id}/reissue`(토큰·만료 교체, 같은 세션·별칭 유지). 재응시는 새 세션.
  21. 삭제 기준: `sessions.ended_at`(completed·failed·cancelled 모두 설정) + 90일.
  22. 의도 분류 출력 `confidence: high|low`(R4).
- **R6 계획 수정**: (a) W2~W3에 `agent-spike` 트랙 신설(메시지 → 의도 분류 → 규칙 턴 → 페르소나 1명 → debate-mcp post_message → WS 최소 경로, 실 LLM 지연·비용·메일박스 검증, 결과는 G-F 동결 입력) (b) W5-0 의존은 G-C만(G-M 제거), be-foundation은 W3와 병렬 가능 (c) W5-1은 4트랙 이하: api ∥ agent ∥ mcp(debate+assessment) ∥ report-worker, rag-mcp 정리는 be-foundation에 흡수 (d) G-F 교차 인터페이스 stub 파일(`app/agent/intent` stub 등)은 be-foundation 소유로 만들고 G-F 후 agent에 인계, api/agent 경계 `SessionPorts`(typing 전송·generation 조회·자극 enqueue)와 `services/api/pyproject.toml` 의존성은 be-foundation이 미리 넣는다 (e) agent 완료 기준은 가짜 MCP·가짜 hub 단위 기준만, WS·재시작은 web-integrate·e2e로 (f) 옛 테스트는 be-foundation이 코드와 함께 삭제. `track/debate`는 G-C~G-E 사이 승인된 기대 실패 목록을 허용하고 main 병합(G-E)은 기대 실패 0 (g) 트랙 표에 우선순위 열: P0 = 최소 경로·확정·시간 초과·제출·리포트 큐·인증, P1 = 카드 6장·침묵 초대·합의 채우기·restart, P2 = 관리자 생성 연결·동시 5세션·playtest (h) e2e 대본 P0는 all_five·timeout_all·honesty_claim, 장애 주입은 큐 DLQ·timeout 2종 (i) 보고서(W4)는 사용자 지정 순서대로 목업 캡처로 먼저 만들고, G-E 뒤 실제 캡처로 갱신하는 짧은 후속 작업을 둔다 (j) MVP 제외 목록의 옛 "F-25 무응답 확인" 삭제(현행 F-25 침묵 초대는 포함).
- **R7 기획 문구 보강 (기획자·지원자 리뷰)**: 동의 화면의 AI 어시스턴트 문구는 "AI가 평가 수준을 매기지 않으며, 요청·응답 기록은 담당자에게 사실로 제공된다"로. 지원자 화면의 내부 용어("칸", "합의 패널", "확정")는 지원자 말로("정할 항목", "결정 사항", "이걸로 정하기"). 실제 남은 시간과 오피스 시각을 한 줄에 같이 쓰지 않는다(남은 시간 중심, 오피스 시각은 메시지 타임스탬프에만). 시간 초과 문구는 "가장 지지가 많았던" 대신 "대화에서 가장 많이 모인 의견으로". 기획안 `idea_credit` 칸에는 무엇을 적는 칸인지만 중립적으로 안내("이 기획에 반영된 의견과 그 의견을 낸 사람"). 디브리핑에 본인 발언 원문 2~3개 읽기 전용 회고, 이의 제기 경로, 설문 자유 의견 한 칸. 리스크 표에 시나리오 유출, 채팅 숙련도·성향 편향, 접속 끊김 불이익(이어하기는 P0로), 평가 일관성(같은 세션 3회 재평가 변동 폭·사람 2인 일치도, 일치율 대신 차이 분포 보고), 규제 해석 미확정을 추가. PRD 6.1에 "지역 생활 문제 해결 공모에 낼 기획안을 정하는 회의" 같은 한 줄 목적. 해결책은 키워드 단위 "방향(데이터·참여·인프라)"으로 표현. 문서 예시의 옛 이름(민준·서연·지호) 정리.

## 2차 리뷰 결정 (오케스트레이터 결정, 앞선 R 결정과 다르면 이 목록이 우선)

- B1 카드 재전달: `card_due`는 담당 전원이 delivered될 때까지 enqueue마다 새 uuid4 run_id로 다시 넣는다. 멱등은 `session_cards.delivered_seats`로 판단한다.
- B2 공동 전달: `messages.card_ids text[]`(단일 card_id 대체), 내부 `POST /messages` 입력도 `card_ids`. 카드마다 `delivered_seats`에 자리를 더하고 observation은 카드마다 1건.
- B3 설득 카드: `persuasion_keyword`는 지원자와 다른 키워드를 민 자리 중 서지안 우선, `persuasion_solution`은 기본 서지안이고 지원자가 서지안 안을 지지하면 강한결. 담당만 바뀌고 고정 입장은 그대로.
- B4 의도 분류 위치: 메일박스 안. 큐 밖은 메시지 저장·generation +1·enqueue만. 메일박스는 message 자극마다 분류와 안·지지 반영을 반드시 하고, 낡은 자극에서 건너뛰는 것은 턴 선택·페르소나 발언 생성뿐.
- B5 run 완료 상태값은 `finished` 하나.
- B6 평가 재생성: 큐 본문 `{session_id, attempt, eval_round}`, run_id = `uuid5(session_id, "evaluate:"+eval_round)`.
- B7 현재 지지: 참여자당 하나. 다른 안 support는 이전 지지를 대체, 같은 안 oppose는 철회(R5-7 대체).
- B8 비용: `sessions.debate_cost_usd`(토론 LLM 비용, 하드 상한용)와 `sessions.cost_usd`(리포트 포함 전체 관측). `cost_left = SESSION_COST_HARD_USD − debate_cost_usd`, `budget.py`가 DB에서 읽어 DebateState로 전달.
- B9 합의 재판정: apply가 입장을 저장한 뒤 fill 노드가 지지를 다시 읽어 3/4 + 지원자 지지면 같은 run에서 채운다.
- B10 합의 공지 순서: `fill_slot`(조건부 갱신) 먼저, 성공 시에만 공지. 409면 문장 없이 종료.
- B11 디브리핑: 요소 이름과 "이렇게 봅니다" 한 줄만 공개, 척도 세부·차원 앵커는 비공개.
- N1 `filled_by`에 `system` 없음.
- N2 페르소나 도구: `get_transcript`·`get_draft`(proposal)·`search_materials`·`get_material`. `get_debate_state`는 바인딩하지 않고 컨텍스트로 주입.
- N3 `fill_slot`에 resolution 인자 없음(합의 전용), `record_observation`은 계약 인자대로, Stimulus에 generation 포함, 시간 초과 공지 seq 0.
- N4 `prompt_versions`: 평가 프롬프트 파일별 개별 해시 맵(계약 형식).
- N5 오피스 시각은 메시지 타임스탬프에만. 결정 사항 결과 줄은 단계와 결과만, 페르소나는 남은 시간으로 말한다.
- N6 회고 발언: 토론 단계마다 가장 긴 지원자 메시지 1개, 최대 3개.
- N7 `docs/review/ux-options.html`은 R2·R3·R7 이전 시안으로 표시.
- N8 `plan.md` 우선순위·배정을 `testing.md`에 맞춘다.
- N9 `decisions.md`의 Lock·lock_held·review 400·실패 시 ends_at 항목에 R5 대체 표시.
- N10 계약 Report 예시는 발췌 표시 또는 4차원 모두 채운다.
- N11 과제 대응 문서의 인증 단언 번호는 `testing.md` 기준.

## 3차 리뷰·스파이크 결정 (오케스트레이터 결정, 앞선 목록과 다르면 이 목록이 우선)

- C1 의도 분류 입력 단계는 저장된 `messages.phase`와 그 단계의 카탈로그. 현재 단계 검사는 턴·발언 생성 생략 판단에만 쓴다.
- C2 리포트 그래프 thread_id = `report:{session_id}:{eval_round}`. 새 회차는 새 thread라 이전 interrupt 체크포인트를 재사용하지 않고, 같은 회차 재시도만 체크포인트에서 재개한다. `report.approve` 본문에 `eval_round`.
- C3 합의 공지는 별도 `post_message`가 아니다. `fill_slot{session_id, option_id, seat, content, run_id}` → `{slot, phase, message}`, 내부 `POST /internal/sessions/{id}/slots/fill`(대상 단계 = option의 phase, `seat`가 공지 화자이자 `filled_by`). api가 한 트랜잭션에서 칸 confirmed → 공지 저장(seq 5, `meta.kind=consensus_fill`) → generation +1, WS `message.new` → `slot.confirmed` → `phase.changed` → `timer`. 같은 run_id 확정이 있으면 기존 칸·공지 반환, 아니면 `phase_not_open` → `slot_confirmed` → `no_consensus` 순 검사, 409면 아무것도 저장하지 않음. 턴 결정은 `fill = {option_id, seat}`이고 `announce_fill` 화자 목적은 없다. fill 노드 전용 분기가 respond·apply 없이 처리한다.
- C4 api enqueue 전 `agent_runs` 상태는 `queued`. cards 노드는 같은 시각의 미전달 카드를 함께 처리. 해결책 설득 담당은 조건부(지원자가 서지안 안을 지지하면 강한결).
- S1 `message` 자극의 generation은 그 메시지 저장이 올린 값.
- S2 `stance_check`: 자기 계획 안에 `oppose`·반대 발언도 계획 밖.
- S3 MCP 도구는 모두 `async def`.
- S4 역할 env `MODEL_INTENT`·`MODEL_TURN`·`MODEL_PERSONA`·`MODEL_ASSISTANT`·`MODEL_EVALUATOR`(`MODEL_REPORT`·옛 이름 폐기). be-foundation이 `.env.example`·`roles.py` 교체.
- S5 `message.ack`는 메시지 저장 직후, 의도 분류 전.
- S6 동결 의존성은 be-foundation·G-F 입력(`docs/plan.md` "agent-spike 결과").
- S7 실측 기준선(p50/p95 의도 1.0/1.2초·페르소나 1.2/1.4초·턴 1.2/1.5초, 60분 $0.08~0.11, 의도 정확도 0.85)은 문서·보고서용이고 완료 조건이 아니다.
- MVP 우선: P0 완료가 먼저이고 최적화·정확도 개선은 "MVP 이후" 목록(`docs/agent/design.md`, `docs/plan.md`)에 둔다.
