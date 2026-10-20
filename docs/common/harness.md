# 하네스 8요소

| 요소 | 구현 위치 | 수치·규칙 | 확인 방법 |
|---|---|---|---|
| Instructions | `scenarios/prompts/` 페르소나별 system prompt(manager, colleague, assistant), `common_rules.md`(판정 금지, 문서명 인용, 평가 기준 질문 안내문), `guard_patterns.yaml`. 행동 계약은 agent/design.md 표. 카드 `brief` 주입 | 프롬프트·guard 패턴은 catalog_version 해시에 포함되고 본문이 `positions.scenario`에 복사되어 채용 건에 고정. 실행은 scenario의 복사본을 쓴다 | 프롬프트 리뷰, 유출·미래 암시·역할 사칭 질문 테스트 |
| Tools | MCP 클라이언트 2개(`langchain-mcp-adapters`). 그래프별 허용 목록(contracts.md), session_id는 그래프가 주입 | 응답당 도구 호출 3회, 검색 top 3, 메시지 조회 50개, 도구 결과 2k자 절단 | respond 노드 로그, 허용 밖 도구 호출 거부 테스트 |
| Context | 페르소나별 허용 목록: 동료 = 팀·DM 최근 30개 + 요약 1개 + 보드·문서 상태 + 실행 중 카드 brief + rag 청크 3개. 팀장 = 팀 채널만. 어시스턴트 = 자기 대화 + 공개 문서 청크. **어느 페르소나에도 넣지 않는 것**: 아직 오지 않은 카드, 관찰 레이블·metrics, 어시스턴트 대화(동료·팀장에게), 미공개 문서 | 호출당 입력 6k 토큰, 초과 시 오래된 메시지를 요약으로 접음 | 토큰 메타, 미래 상황 유도 질문 3건·미공개 문서 질문·역할 사칭 질문 픽스처 |
| State·Memory | LangGraph PostgresSaver. thread `session:{id}`, `assistant:{id}`, 워커 `report:{id}` | 자극마다 체크포인트. 재시작 시 fired 이벤트 재실행 | restart 대본 |
| Agent Loop | recursion_limit 20, 분업 조정 3회, 업무 중 재분업 1회, 어시스턴트 60회/세션, 세션 토큰 예산 300k(입력+출력, 재시도 포함), `ends_at` 도달 시 강제 submit | 한도 초과는 고정 안내문. 예산 소진 뒤 페르소나 자유 응답은 안내문으로 대체하고 카드는 brief 없이 규칙 문장으로 계속 발행. 한도는 세션 단위, 초기화 없음 | e2e 단언, agent_runs.usage 합산 |
| Guardrails | `guard`: 점수·합격·순위·연출·평가 기준 패턴 → 고정 안내문 치환. 입력 마스킹: 전화번호·이메일. 사람 승인: 리포트 그래프 interrupt → 검토 완료가 같은 thread 재개 | 패턴 목록은 prompts 트랙이 관리. 승인 전 final 저장은 api가 409로 차단 | guard 단위 테스트, 승인 e2e |
| Recovery | LLM 래퍼: 타임아웃 30초, 재시도 2회(1·3초) → `FallbackText` | 일반 응답 실패: 고정 문장 저장, llm_failures+1. 필수 카드 실패: 이벤트 attempts+1로 재실행(최초 포함 총 3회). llm_failures 연속 3회 또는 카드 3회 실패 → 세션 failed. 성공 시 카운터 0 | 강제 실패 주입 테스트 |
| Observability | LangSmith trace(run_id를 metadata로), `agent_runs.usage`(run별 llm_calls, retries, tokens_in/out, latency_ms, tool_calls), `messages.meta`(응답별 토큰·지연·모델), `reports.usage`(워커), 구조화 로그에 run_id | 세션 비용 = agent_runs.usage + reports.usage 합. 접수→응답 지연 = message.ack 시각과 응답 message.new 시각 차 | trace 링크, e2e summary의 비용·지연 표 |

실패 유형별 폴백 형태: 페르소나 응답 → 고정 문장. 분업 분류 → "수락"으로 간주하지 않고 재질문 1회 후 마지막 안 확정. 관찰 분류 → label null(관찰 없음)로 기록. 어시스턴트 → "잠시 후 다시 시도해 주세요".
