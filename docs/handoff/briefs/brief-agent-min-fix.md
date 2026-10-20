# agent-min 마무리 라운드 (Codex 리뷰 반영 + 커밋 + 보고서)
현재 작업 트리는 커밋되지 않았다. 아래 순서로 끝낸다. 끝나면 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/agent-min-report.md 에 원래 브리프(/private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/brief-agent-min.md)가 요구한 보고서(완료 기준별 명령·결과, 수정 파일, 남은 문제, 변경 요청, 다른 트랙에 알릴 것, M2 구조 메모)를 저장. 마지막 응답은 경로 한 줄.
1. 먼저 현재 상태를 그대로 커밋한다(한국어 한 문장, 본문에 테스트 명령). 작업물 보존이 우선.
2. 리뷰 반영(리뷰 원문: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/review-agent-min-raw.txt). 오케스트레이터 결정:
   - 기본 runner가 Fake인 것은 브리프대로이므로 유지(`AGENT_RUNNER=session`으로 전환). 결함 아님.
   - 도구 호출 상한(설계 값) 도달 시 루프를 끝내고 폴백 응답으로 간다. 연속 도구 호출을 돌려주는 FakeLLM 사례를 기존 연결 테스트에 합친다.
   - guard: 점수 표현(`score` 그룹)은 `unless`보다 먼저 검사한다. 즉 문장에 점수 표현이 있으면 업무 지표가 같이 있어도 치환. 혼합 문장 "리드님 현재 점수는 80점이고 재참여율은 22%예요"를 hit 예문으로 테스트에 추가(`scenarios/prompts/guard_patterns.yaml`의 머리말·예문도 같이 고친다. 이번만 허용).
   - 페르소나별 도구 목록 분리: 동료는 search_documents·get_document·get_board·get_document_state, 팀장은 get_board·get_document_state만. 팀장의 rag 호출 거부 테스트 한 줄.
   - 미공개 문서: rag가 `not_released`를 돌려주면 코드가 "아직 공유되지 않은 자료예요" 문장을 결정적으로 응답에 넣는다(LLM 문구에 기대지 않음). live 단언은 유지.
3. `cd services/api && uv run pytest -q`, 루트 `make test`·`make lint`.
4. live 테스트 1회: `uv run pytest -q -m live tests/agent`(infra/.env의 키 사용, 값 출력 금지). 실패하면 원인과 함께 보고하고 멈추지 말고 보고서를 쓴다.
5. 수정분을 커밋.
