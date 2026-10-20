# prompts (prompts 트랙 소유)

| 파일 | 내용 |
|---|---|
| `colleague.md` | 동료(이도현) system prompt. `docs/agent/design.md` 페르소나 표의 동료 열과 카탈로그 `persona`(values·style·must·must_not_preempt·in_window_help·identity·must_not)를 규칙으로 옮긴다. 작업 기억 사용법, 카드 brief 말하기, 문서 인용 형식 |
| `manager.md` | 팀장(한서윤) system prompt. 같은 표의 팀장 열, 추가 자료 요청 고정 대응, 보고 응답 |
| `assistant.md` | AI 어시스턴트 system prompt. 같은 표의 어시스턴트 열, 공개 문서만 인용, 인용 형식, 사용 한도 안내 |
| `common_rules.md` | 공통: 판정 발언 금지, 정해진 안내문(평가 기준·연출·미래 상황·정체), 미래 상황 비공개, 문서명 인용, 길이 |
| `guard_patterns.yaml` | guard가 치환할 금지 패턴(정규식)과 치환 안내문, 걸려야 할·걸리면 안 될 예문, 인용 검사용 문서 제목·별칭 |
| `observe_labels.md` | observe 레이블 분류 지시문: 출력 형식, aux 기준, 요소별 레이블 정의·판정 우선순위·판정 예시 2개씩 |
| `fixtures/preemption.yaml` | 선점 금지 5개 각 1건: 맥락, 지원자 발화, 동료가 해야 할 것·하면 안 되는 것, 검사 정규식 |
| `fixtures/grounding.yaml` | 근거 정확성 10건: 질문, 기대 도구, 허용 문서, 기대 인용, 핵심 사실 |
| `fixtures/context_leak.yaml` | 컨텍스트 유출 5건: 미래 상황 유도 질문 3건, 역할 사칭 질문 2건. 지원자 발화, 기대 응답 요지, 금지 패턴 |

이 폴더 전체는 `catalog_version` 해시에 들어가고 채용 건 생성 시 `positions.scenario`에 복사된다. 실행은 복사본을 읽는다.

## 조립 방식 (agent-session·agent-assistant 로더용)

프롬프트 본문에는 치환 변수가 없다. system 메시지는 `common_rules.md` + 페르소나 파일 순으로 붙인다(observe는 `observe_labels.md`만). 실행 맥락은 코드가 아래 이름의 블록으로 붙이며, 프롬프트는 이 이름을 가리킨다.

| 블록 | 넣는 곳 | 내용 |
|---|---|---|
| `[실행할 카드]` | 동료·팀장 (inject·kickoff·ask_division·review·request_report) | 카드 brief(치환 변수 적용 후), brief_note, 채널 |
| `[작업 기억]` | 동료 | `work_notes` JSON |
| `[문서 검색 결과]` | 동료·어시스턴트 | 검색·조회 결과(문서 제목 포함), 공개 여부 |
| `[최근 대화]` | 동료·팀장 | 페르소나별 허용 채널의 최근 메시지와 요약 |
| `[보드·문서 상태]` | 동료·팀장 | 태스크 보드, 파트별 담당·작성 상태 |
| `[카드]`, `[창 안 지원자 활동]`, `[맥락]` | observe | `observe_labels.md` 1절. 책임감 `[카드]`에는 코드가 계산한 `release_at`(실제 공개 시각, 분)과 `released_before_message`(지원자 메시지 id → 공개 전이면 true)를 넣는다. 알림 본문의 "약 15분"으로 공개 시각을 추정하지 않는다. 이 두 값은 observe 전용이며 페르소나 블록에는 넣지 않는다 |

픽스처(`fixtures/`)와 `README.md`는 system 메시지에 붙이지 않는다. 필요한 프롬프트 파일만 이름으로 골라 조립한다.
