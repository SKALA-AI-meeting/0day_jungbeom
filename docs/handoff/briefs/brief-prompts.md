# 브리프: prompts 트랙 (W1, 코드 없음)
역할: prompts 작성. 브랜치 track/prompts.
## 공통 규칙
- worktree는 현재 폴더, 커밋은 자기 브랜치에만. main 병합·push 금지.
- 읽을 것: AGENTS.md, docs/plan.md(자기 트랙 행·파일 소유권·병렬 작업 규칙), docs/dev-process.md, docs/common/contracts.md, docs/decisions.md 맨 아래 "foundation 리뷰 반영" 절.
- foundation 결과를 먼저 본다: 보고서 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report.md 와 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report-2.md 의 "다른 트랙에 알릴 것" 절(자기 트랙 항목).
- 소유권 밖 파일(foundation 소유 파일, contracts.md, 다른 트랙 폴더)은 수정하지 않는다. 바꿔야 하면 보고서에 "변경 요청"으로 적고 가능한 범위에서 계속 진행한다.
- TDD, happy path 중심. 완료 기준 한 줄당 테스트 하나. LLM 호출 없음(mock). DB는 공용 postgres(`make infra-up`은 main 저장소에서 이미 떠 있음, localhost:5432). api 테스트는 실행마다 임시 DB를 만드는 conftest를 그대로 쓴다. 통합 스택은 한 번에 하나이므로 `make up`·`app.run` 상시 기동 금지(필요하면 잠깐 띄우고 내린다).
- `infra/.env` 키 값은 출력·복사 금지.
- 커밋 메시지는 한국어 한 문장, 본문에 실행한 테스트 명령.
- 끝나면 완료 기준 각 줄을 직접 실행해 명령·결과, 수정 파일 목록, 남은 문제, 변경 요청, 다른 트랙에 알릴 것을 Markdown으로 저장한다. 마지막 응답은 그 파일 경로 한 줄만.
## 추가로 읽을 것
PRD.md 6·7장, docs/agent/design.md 전체(특히 전이표, 페르소나 3층 표, observe·레이블 규칙, 완료 기준의 작업 기억·선점 금지 픽스처), docs/common/rubric.md, docs/common/scenario-model.md, scenarios/catalog.yaml 전체(persona, 카드 brief, labels, label_texts, rubric), scenarios/documents/*.md, scenarios/prompts/README.md, scenarios/e2e/*.yaml.
## 범위
`scenarios/prompts/`: colleague.md(이도현, 카탈로그 persona의 values·style·must·must_not_preempt·in_window_help·identity·must_not을 규칙으로; 작업 기억 work_notes 사용법; 카드 brief를 받아 말하는 법; 문서 인용 형식), manager.md(한서윤), assistant.md(공개 문서만 인용, 인용 형식, 한도 안내), common_rules.md(판정 발언 금지, 평가 기준·연출 질문 안내문, 미래 상황 비공개, "AI 맞죠?" 답), guard_patterns.yaml(금지 패턴과 치환 안내문, 정규식), observe_labels.md(요소별 레이블 정의·판정 예시 2개씩·aux 기준), 카탈로그 `scenarios/catalog.yaml`의 brief·labels·label_texts·debrief 문구만 다듬기(구조·키·시점·rubric 조건은 변경 금지), 픽스처 문장 `scenarios/prompts/fixtures/preemption.yaml`(선점 금지 5개 각 1건: 지원자 발화 + 동료가 해야 할 것/하면 안 되는 것)과 `fixtures/grounding.yaml`(근거 정확성 10건: 질문·기대 도구·허용 문서·기대 인용). 모든 프롬프트는 한국어, 페르소나는 고정 인물. 점수·합격·연출 언급 금지가 프롬프트 안에 있어야 한다.
## 완료 기준
파일이 전부 존재하고 README 표와 일치, catalog.yaml이 YAML로 파싱됨(`python -c "import yaml; yaml.safe_load(open('scenarios/catalog.yaml'))"`), agent/design.md 페르소나 표의 각 행이 어느 파일 어느 절에 반영됐는지 대응표를 보고서에 포함. 루트 `make lint` 통과.
## 보고서 경로
/private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/prompts-report.md
