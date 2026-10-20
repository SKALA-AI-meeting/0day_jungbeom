# 하네스 8요소

| 요소 | 구현 위치 | 수치·규칙 | 확인 방법 |
|---|---|---|---|
| Instructions | `services/api/app/agent/prompts/` 페르소나별 system prompt(manager, colleague, assistant)와 `common_rules.md`(판정 금지, 문서명 인용, 평가 기준 질문 안내문). 카드 `brief` 주입 | 프롬프트는 파일로 버전 관리, 카탈로그 버전과 함께 채용 건에 고정 | 프롬프트 리뷰, 유출 질문 테스트 |
| Tools | MCP 클라이언트 2개(`langchain-mcp-adapters`). 그래프별 허용 목록(contracts.md), session_id는 그래프가 주입 | 응답당 도구 호출 3회, 검색 top 3, 메시지 조회 50개, 도구 결과 2k자 절단 | respond 노드 로그, 허용 밖 도구 호출 거부 테스트 |
| Context | 최근 메시지 30개 + 이전 요약 1개 + 카드 brief + rag 청크 3개 | 호출당 입력 6k 토큰, 초과 시 오래된 메시지를 요약으로 접음 | 토큰 메타 |
| State·Memory | LangGraph PostgresSaver. thread `session:{id}`, `assistant:{id}`, 워커 `report:{id}` | 자극마다 체크포인트. 재시작 시 fired 이벤트 재실행 | restart 대본 |
| Agent Loop | recursion_limit 20, 분업 조정 3회, 어시스턴트 60회/세션, `ends_at` 도달 시 강제 submit | 한도 초과는 고정 안내문. 한도는 세션 단위, 초기화 없음 | e2e 단언 |
| Guardrails | `guard`: 점수·합격·순위·연출·평가 기준 패턴 → 고정 안내문 치환. 입력 마스킹: 전화번호·이메일. 사람 승인: 리포트 그래프 interrupt → 검토 완료가 같은 thread 재개 | 패턴 목록은 prompts 트랙이 관리. 승인 전 final 저장은 api가 409로 차단 | guard 단위 테스트, 승인 e2e |
| Recovery | LLM 래퍼: 타임아웃 30초, 재시도 2회(1·3초) → `FallbackText` | 일반 응답 실패: 고정 문장 저장, llm_failures+1. 필수 카드 실패: 이벤트 attempts+1로 2회 재실행. llm_failures 연속 3회 또는 카드 2회 실패 → 세션 failed. 성공 시 카운터 0 | 강제 실패 주입 테스트 |
| Observability | LangSmith trace(run_id를 metadata로), `messages.meta`에 토큰·지연·모델, 구조화 로그에 run_id | 세션당 비용 합산 가능 | trace 링크, meta 집계 |

실패 유형별 폴백 형태: 페르소나 응답 → 고정 문장. 분업 분류 → "수락"으로 간주하지 않고 재질문 1회 후 마지막 안 확정. 관찰 분류 → label null(관찰 없음)로 기록. 어시스턴트 → "잠시 후 다시 시도해 주세요".
