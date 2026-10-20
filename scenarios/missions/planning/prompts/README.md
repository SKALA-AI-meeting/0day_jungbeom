# prompts (미션 planning)

재설계 기간에는 scenario-redesign 트랙이 소유하고, 그 뒤 문구 다듬기는 prompts 트랙이 맡는다. 페르소나 데이터는 `../persona.yaml`, 카드 내용은 `../cards.yaml`이 정본이다.

| 파일 | 내용 |
|---|---|
| `colleague.md` | 동료(이도현) system prompt. `docs/agent/design.md` 페르소나 표의 동료 열과 `persona.yaml` colleague(values·style·must·must_not_preempt·in_window_help·identity·must_not)를 규칙으로 옮긴다. 작업 기억, 카드 brief 말하기, 반대 의견 고정 문장, 문서 인용 형식 |
| `manager.md` | 팀장(한서윤) system prompt. 팀장 DM 규칙(맥락 질문은 답, 정답·판단 요청은 주담당에게), 추가 자료 요청 고정 대응, 보고 응답 |
| `assistant.md` | AI 어시스턴트 system prompt. 공개 문서만 인용, 인용 형식, 사용 한도 안내 |
| `common_rules.md` | 공통: 판정 발언 금지, 정해진 안내문(평가 기준·연출·미래 상황·정체), 미래 상황 비공개, 문서명 인용, 길이 |
| `guard_patterns.yaml` | guard가 치환할 금지 패턴(정규식)과 치환 안내문, 걸려야 할·걸리면 안 될 예문, 인용 검사용 문서 제목·별칭 |
| `observe_labels.md` | observe 레이블 분류 지시문: 출력 형식, 카드 7장의 레이블·aux·근거 타입·판정 우선순위·예시(이름은 `docs/common/rubric.md` 표와 같음) |
| `fixtures/preemption.yaml` | 선점 금지 6건: 맥락, 지원자 발화, 동료가 해야 할 것·하면 안 되는 것, 검사 정규식 |
| `fixtures/manager_dm.yaml` | 팀장 DM 규칙 5건: 답할 질문·돌릴 질문 |
| `fixtures/grounding.yaml` | 근거 정확성 10건: 질문, 기대 도구, 허용 문서, 기대 인용, 핵심 사실 |
| `fixtures/context_leak.yaml` | 컨텍스트 유출 6건: 미래 상황 유도 3건, 보내지 않은 문서 1건, 역할 사칭 2건 |

미션 폴더 전체가 `catalog_version` 해시(`scenarios/version.py`)에 들어가고 채용 건 생성 시 `positions.scenario`에 복사된다. 실행은 복사본을 읽는다.

## 조립 방식 (agent-session·agent-assistant 로더용)

프롬프트 본문에는 치환 변수가 없다. system 메시지는 `common_rules.md` + 페르소나 파일 순으로 붙인다(observe는 `observe_labels.md`만). 실행 맥락은 코드가 아래 이름의 블록으로 붙이며, 프롬프트는 이 이름을 가리킨다.

| 블록 | 넣는 곳 | 내용 |
|---|---|---|
| `[실행할 카드]` | 동료·팀장 (kickoff·ask_division·inject·checkin·review·request_report) | 카드 brief(치환 변수 적용 후), brief_note, 채널. 반대 의견은 고른 고정 의견 하나와 대상 문장 |
| `[작업 기억]` | 동료 | `work_notes` JSON |
| `[문서 검색 결과]` | 동료·팀장·어시스턴트 | 검색·조회 결과(문서 제목 포함), 공개 여부 |
| `[최근 대화]` | 동료·팀장 | 페르소나별 허용 채널의 최근 메시지와 요약 |
| `[보드·문서 상태]` | 동료·팀장 | 태스크 보드, 보낸 문서 목록(지원자 문서는 보낸 버전만) |
| `[카드]`, `[창 안 지원자 활동]`, `[맥락]`, `[사실]` | observe | `observe_labels.md` 1절. 카드별 코드 계산 사실(`release_at`·`released_before_message`, `change_targets`, `card_t_min`, 정직 사실 입력)은 observe 전용이며 페르소나 블록에는 넣지 않는다 |

픽스처(`fixtures/`)와 `README.md`는 system 메시지에 붙이지 않는다. 필요한 프롬프트 파일만 이름으로 골라 조립한다.
