# 하네스 8요소

| 요소 | 구현 위치 | 확인 방법 |
|---|---|---|
| Instructions | `services/api/app/agent/prompts/` 페르소나별 system prompt(manager, colleague, assistant)와 `common_rules.md`(판정 금지, 문서명 인용, 평가 기준 질문 안내문). 카드 `brief`를 주입 | 프롬프트 파일 리뷰 |
| Tools | MCP 클라이언트 2개(`langchain-mcp-adapters`). 도구 결과 길이 제한(검색 top 3, 메시지 50개), 응답당 도구 호출 3회 | respond 노드 로그 |
| Context | 최근 메시지 30개 + 이전 요약 1개. 토큰 예산 초과 시 요약 갱신. rag 결과는 청크 3개만 주입 | 토큰 메타 |
| State·Memory | LangGraph PostgresSaver, thread_id = session_id. 어시스턴트는 `assistant:{session_id}` | 재시작 후 /state 이어하기 |
| Agent Loop | 그래프 실행당 노드 반복 상한(recursion_limit 20), 분업 조정 3회, 어시스턴트 60회, `ends_at` 도달 시 강제 submit | e2e 단언 |
| Guardrails | 출력 검사 `guard`: 점수·합격·연출·평가 기준 언급 패턴 → 고정 안내문 치환. 입력 마스킹: 전화번호·이메일. 사람 승인: 리포트 그래프가 draft 뒤 interrupt로 멈추고 관리자의 검토 완료가 같은 thread를 재개 | guard 단위 테스트 |
| Recovery | LLM 호출 2회 재시도(지수 백오프) → 실패 시 고정 문장("잠시만요, 확인하고 다시 말씀드릴게요")으로 응답하고 다음 자극에서 체크포인트 재개. 리포트는 큐 재시도 3회 → DLQ | 강제 실패 테스트 |
| Observability | LangSmith(`LANGCHAIN_TRACING_V2`), 응답마다 `messages.meta`에 토큰·지연·모델, 구조화 로그 | trace 링크, meta |
