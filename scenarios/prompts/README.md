# prompts (prompts 트랙 소유)

| 파일 | 내용 |
|---|---|
| `colleague.md` | 동료(이도현) system prompt. `docs/agent/design.md` 페르소나 행동 계약 표의 동료 열을 그대로 규칙으로 옮긴다 |
| `manager.md` | 팀장(한서윤) system prompt. 같은 표의 팀장 열 |
| `assistant.md` | AI 어시스턴트 system prompt. 같은 표의 어시스턴트 열, 인용 형식 |
| `common_rules.md` | 공통: 판정 발언 금지, 문서명 인용, 평가 기준·연출 질문 안내문, 미래 상황 비공개 |
| `guard_patterns.yaml` | guard가 치환할 금지 패턴 목록과 치환 안내문 |

이 폴더 전체는 `catalog_version` 해시에 들어가고 채용 건 생성 시 `positions.scenario`에 복사된다. 실행은 복사본을 읽는다.
