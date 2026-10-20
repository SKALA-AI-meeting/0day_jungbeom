# 과제 평가표와 대응

출처: 과제 자료 "팀별 Capstone 평가표" (표 6-14). 기본 100점, 가산점 포함 110점.

| 항목 | 주요 내용 | 배점 | Day Zero의 근거 | 확인 위치 |
|---|---|---|---|---|
| Biz. 아이템 | 참신한 B2B·B2B2C 아이템. 상용화 효용성이 크면 팀 프로젝트 연속성 유지 가능(운영진·교수진 동의 시) | 10 | 리모트 스타트업이 구매하고 지원자가 사용하는 B2B2C. 채용 실패 비용이라는 구매 이유. 기업이 요소를 고르는 맞춤 평가 | PRD 1~4, 12~14장 |
| 아키텍처 설계 | 전체 AI 아키텍처, ISO/IEC 25010 품질 고려 | 10 | 구성도·논리·런타임·배포·연결·Harness 뷰. 품질 특성 8개 대응표 | `common/architecture.md`, 최종 보고서 |
| AI Agent 설계 | State 구조, Graph 흐름(Node·분기·반복), Agentic 요소 | 15 | State 13필드, 노드 9개, 분기(route·합의), 반복(분업 조정·observe→inject), respond의 도구 선택 | `agent/design.md` |
| AI Agent 구현 | Graph가 코드에 반영, 모델이 도구를 선택해 근거와 함께 답함, 상태 저장·재개, 진행 이벤트, Agentic 요소 | 15 | 그래프 코드, 문서명 인용, PostgresSaver 재개, WS `agent.progress`(tool_start·tool_end·finished) | `services/api/app/agent/`, e2e 기록 |
| MCP 설계·구현 | business-mcp·rag-mcp가 조회·변경 도구와 설명을 갖추고 Agent가 연결해 호출. 오류·예외 처리 | 20 | 도구 14개(조회 8, 변경 6), 통일 오류 형식, 공개 전 문서 차단, upstream 장애 코드 | `common/contracts.md`, `mcp/design.md` |
| Harness | 주요 구성 요소의 적절한 적용 | 20 | 8요소 매핑표 | `common/harness.md` |
| 인증 | 사용자 인증 처리 | 10 | 관리자 JWT, 지원자 세션 JWT, 내부 시크릿, 기업 간 격리 | `api/design.md` |
| 가산점 (대기열) | RabbitMQ·Kafka 같은 큐로 작업 처리, 실패 재시도 | 10 | 리포트 생성 큐, 재시도 3회, DLQ | `worker-infra/design.md` |

## 레퍼런스와 다른 점 (평가 리스크)

| 레퍼런스 기대 | Day Zero | 대응 |
|---|---|---|
| 변경 도구 앞에서 interrupt로 멈추고 승인 후 같은 thread로 재개 (전체 흐름 2) | 리포트 그래프가 draft 뒤에서 interrupt로 멈추고, 관리자의 "검토 완료"가 큐를 통해 같은 thread를 재개해 최종 리포트를 저장 | 해소. 확장 후보: 상호 리뷰에서 동료가 지원자 파트를 고치기 전 허락을 구하는 세션 내 승인(`write_document_part` 앞 interrupt, 지원자가 수락·거절) |
| 질문을 202로 접수하고 SSE로 진행 이벤트 | WebSocket 양방향(동료가 먼저 말을 걺) | 진행 이벤트 이름을 레퍼런스와 맞춤(tool_start·tool_end·done·failed) |
| 화면·업무 서버·Agent 서버 분리 | Agent가 api 프로세스 안의 모듈 | 논리 계층은 분리 유지(라우터 vs agent 모듈), 배포 tier만 합침을 구성도에 명시 |
| Vue + Spring Boot | Next.js + FastAPI | 부록에서 스택 변경 허용 |
