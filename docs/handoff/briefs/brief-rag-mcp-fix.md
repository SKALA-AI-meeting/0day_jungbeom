# rag-mcp 수정 라운드 (Codex 리뷰 반영)
리뷰 전문: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/review-rag-mcp.md. 오케스트레이터 결정. 같은 브랜치에 커밋. 끝나면 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/rag-mcp-report-2.md 에 수정 목록·검증 명령·결과 저장(worktree의 REVIEW.md 삭제). 마지막 응답은 경로 한 줄.

## 반드시
- P1 전문 버전 고정: `get_document`는 파일을 읽지 않고, 세션의 catalog_version에 해당하는 `doc_chunks`를 chunk_no 순으로 이어 붙여 본문을 만든다(400자 슬라이스라 strip된 원문이 복원됨). 해당 버전 청크가 없으면 `upstream_unavailable`(retryable). title은 내부 GET /documents 응답 값. 기존 재색인 테스트에 "문서를 바꿔도 V1 세션은 V1 본문"을 확인하는 단언 1개를 합친다. API·계약 변경 없음.
## 같이
- 오류 매핑·재시도 테스트가 DB 없이 돌도록 conftest의 API mock 픽스처를 DB 픽스처와 분리.
- `top_k=0` → invalid_input 테스트 1개(완료 기준 "잘못된 입력").
- README·docstring에 `indexed`는 "색인된 청크 수"로 명시(계약 반영은 오케스트레이터).
## 하지 않을 것
compose·env 수정(병합 때 오케스트레이터가 hfcache 볼륨을 /models로 맞춤), 3GB 메모리 실측(M1 연결 때).
