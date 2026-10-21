# 과제 평가표와 대응

출처: 과제 자료 "팀별 Capstone 평가표" (표 6-14). 기본 100점, 가산점 포함 110점.

| 항목 | 주요 내용 | 배점 | Day Zero의 근거 | 확인 위치 |
|---|---|---|---|---|
| Biz. 아이템 | 참신한 B2B·B2B2C 아이템. 상용화 효용성이 크면 팀 프로젝트 연속성 유지 가능(운영진·교수진 동의 시) | 10 | 리모트 스타트업이 구매하고 지원자가 사용하는 B2B2C. 채용 실패 비용이라는 구매 이유. 같은 채용 건의 모든 지원자가 같은 설계된 장면(5요소·카드 6장)을 겪는 공정한 비교. 담당자가 바로 쓰는 산출물: 토론 기록·제출 기획안 + AI 평가 에이전트의 BARS 수준 판단(근거·확신도) + 담당자 차원 단위 조정과 최종 평가(총점 없음) | PRD 1~4, 9, 12~14장 |
| 아키텍처 설계 | 전체 AI 아키텍처, ISO/IEC 25010 품질 고려 | 10 | 구성도·논리·런타임·배포·연결·Harness 뷰. 품질 특성 8개 대응표. 팀 공유 아키텍처 HTML(`docs/share/architecture.html`)은 브리프 "2단계 아키텍처 html 지침"(전체 구성도·에이전트 구성·흐름·MCP 역할 네 중심, 중복 제거)을 따른다 | `common/architecture.md`, `docs/share/architecture.html`, 최종 보고서 |
| AI Agent 설계 | State 구조, Graph 흐름(Node·분기·반복), Agentic 요소 | 15 | 토론 그래프 State 15필드(generation·seat_memory·card_progress 포함), 노드 11개(load·cards·turn·typing_on/off·respond·guard·stance_check·wait_typing·apply·fill), 세션별 메일박스가 자극 4종(message·phase_started·idle·card_due)을 직렬 소비, 분기(화자 0~2명·카드·칸 채움), 반복(화자마다 respond→guard→stance_check→apply, guard·stance_check 재생성 1회), 턴 매니저 + 성향 페르소나 3(고정 안·입장 규칙·must_not), 메일박스 안 실시간 의도 분류, 어시스턴트 그래프, 리포트 그래프의 평가 에이전트(요소별 독립 호출) | `agent/design.md` |
| AI Agent 구현 | Graph가 코드에 반영, 모델이 도구를 선택해 근거와 함께 답함, 상태 저장·재개, 진행 이벤트, Agentic 요소 | 15 | 그래프 코드, AI 어시스턴트의 도구 호출 루프(`search_materials`·`get_material`을 모델이 골라 최대 3회, 인용 포함), 페르소나 respond의 자료 인용(DebateState는 컨텍스트에 미리 넣음), PostgresSaver 재개(`debate:`·`assistant:`·`report:` thread), WS `message.ack{run_id}`·`typing`·`message.new`, 리포트 그래프 interrupt→승인 재개, 실제 모델 실행 기록과 trace | `services/api/app/agent/`, e2e 기록 |
| MCP 설계·구현 | MCP 서버가 조회·변경 도구와 설명을 갖추고 Agent가 연결해 호출. 오류·예외 처리 | 20 | MCP 3개 도구 16개(debate 조회 3·변경 4, rag 조회 2·변경 1, assessment 조회 4·변경 2), 노드별 허용 목록과 호출 주체 표(페르소나는 assessment 접근 불가, 토큰 분리), e2e 기록의 run_id별 도구 호출, 통일 오류 형식, 열리지 않은 자료 차단(`not_released`), upstream 장애 코드 | `common/contracts.md`, `mcp/design.md` |
| Harness | 주요 구성 요소의 적절한 적용 | 20 | 8요소 매핑표 | `common/harness.md` |
| 인증 | 사용자 인증 처리 | 10 | 관리자 JWT, 지원자 세션 JWT, 디브리핑 읽기 토큰, 내부 시크릿, 기업 간 격리. e2e 단언 8의 인증 경계 기록 | `api/design.md`, e2e `auth.md` |
| 가산점 (대기열) | RabbitMQ·Kafka 같은 큐로 작업 처리, 실패 재시도 | 10 | 리포트 생성 큐, 재시도 3회, DLQ | `worker-infra/design.md` |

## 레퍼런스와 다른 점 (평가 리스크)

| 레퍼런스 기대 | Day Zero | 대응 |
|---|---|---|
| 변경 도구 앞에서 interrupt로 멈추고 승인 후 같은 thread로 재개 (전체 흐름 2) | 리포트 그래프가 draft 뒤에서 interrupt로 멈추고, 관리자의 "검토 완료"가 큐를 통해 같은 thread를 재개해 최종 리포트를 저장 | 승인 대상 변경은 "초안을 최종본으로 확정하는 저장"이다. 증명: 승인 전 final 저장은 api가 409로 차단, final은 승인한 draft와 해시 동일, 워커 로그의 같은 thread_id. MCP 변경 도구 앞 승인과 같다고 표현하지 않고 "변경 저장 앞 승인"으로 설명. |
| 질문을 202로 접수하고 SSE로 진행 이벤트 | WebSocket 양방향(동료가 먼저 말을 걺) | 대응 관계: 202 접수 = `message.ack{run_id}`, 진행 = `typing{participant, start∣stop}`, 완료 = `message.new`. 재접속은 `/state` 스냅샷으로 복구 |
| 화면·업무 서버·Agent 서버 분리 | Agent가 api 프로세스 안의 모듈 | 논리 계층은 분리(라우터 → SessionService → AgentRunner 인터페이스 → 그래프 → MCP 어댑터), 배포 tier만 합침. 그래프 실행 중에도 HTTP·WS·스케줄러가 동작하는지 테스트로 확인. 단일 프로세스 제약과 향후 분리 지점(AgentRunner)을 plan.md에 기록 |
| Vue + Spring Boot | Next.js + FastAPI | 부록이 변경을 허용. 선택 이유: FastAPI는 LangGraph와 같은 Python 프로세스에서 비동기 WS를 처리, Next.js는 관리자·지원자 두 화면을 한 앱의 경로로. 업무 규칙의 소유자는 FastAPI뿐이고 Next.js 서버 영역은 쓰지 않음. 기능 동등성은 인증·진행 이벤트·MCP·승인 재개·큐 재시도 시연으로 증명 |
