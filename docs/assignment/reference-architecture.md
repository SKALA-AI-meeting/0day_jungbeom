# 레퍼런스 아키텍처 표현 참고

출처: 과제 자료 PDF 5장 "레퍼런스 아키텍처" 47~66쪽 (`Day64_AI_Agent_Capstone_MCP/materials/AI-Agent Capstone(+MCP).pdf`, 로컬 전용·저작권 표기 있어 저장소에 복사하지 않음). 최종 보고서의 아키텍처 장은 이 구성을 따라 쓴다.

## 쪽별 내용과 Day Zero 적용

| 쪽 | 내용 | Day Zero에서 쓸 방식 |
|---|---|---|
| 47 | 아키텍처 설계 기준: 요구 사항 → 아키텍처 결정 → 확인하는 도식 표 (응답 시간, 업무 규칙 한 곳, 노출 주소 최소, 변경은 사람 확인, 근거 문서) | 같은 표를 Day Zero 요구 사항으로 다시 쓴다. 예: "동료가 먼저 말을 건다 → WebSocket", "같은 채용 건은 같은 조건 → 시나리오 데이터화" |
| 48 | 뷰 구성: 전체 구성도(Container, Client-Server), 논리 뷰(Layered), 런타임 뷰(Sequence, Event-Driven), 배포 뷰(N-tier), 연결 뷰(Client-Server, Pipe-and-Filter), Harness(Microkernel) | 보고서 아키텍처 장을 이 6개 뷰로 구성 |
| 49 | 도식 표기 범례: 화면, Agent 코어, 저장소(원통), 처리 단계(화살 상자), Trust Boundary(점선), 컴포넌트, MCP Server(육각), 외부 서비스(구름), 배포 노드(상자), 논리 경계, 동기 호출(채운 화살), 비동기(열린 화살), 응답(점선), 처리 순서(번호), 상태(둥근), 생명선 | 모든 그림에 같은 범례를 쓴다. SVG 스타일 클래스로 고정 |
| 50~51 | 레퍼런스 구성도 + 번호별 처리 흐름 표(구간, 처리 내용, 프로토콜) | 구성도에 번호를 달고 아래에 번호별 표. Day Zero는 ① 지원자 메시지 WS ② api→agent 모듈 ③ LLM ④ MCP ⑤ business-mcp→/internal ⑥ rag→벡터 ⑦ 진행 이벤트 WS ⑧ 종료→큐→워커 |
| 52 | 구성 요소별 목적·역할·금지 사항 표 | web(권한 판단 금지, MCP 직접 호출 금지), api, agent 모듈(DB 직접 쓰기 금지), business-mcp(업무 규칙 복제 금지), rag-mcp(업무 데이터 변경 금지), worker, postgres |
| 53 | 계층별 기술과 기준 버전 표 | Presentation Next.js, Application·AI Serving FastAPI+LangGraph 1.x, Tool FastMCP, Knowledge pgvector+BGE-M3, Data PostgreSQL 16, Queue RabbitMQ, External OpenAI |
| 54~55 | 논리 아키텍처 계층 구조 그림 + Layer별 책임·금지·인터페이스 표. "아래에서 위로 가는 호출 예외"(business-mcp→/internal) | 같은 그림. Day Zero는 Application과 AI Serving이 같은 프로세스지만 계층은 분리해 그린다 |
| 56 | 동기 경로와 비동기 경로 그림 + 표 | 동기: 관리자 API, 문서 저장. 비동기: 페르소나 응답(WS), 이벤트 fire(스케줄러), 리포트(큐) |
| 57~59 | Sequence 3개: 질문 처리, 근거 검색, 변경 도구 승인과 완료 | Day Zero: ① 지원자 메시지→동료 응답 ② 이벤트 fire→observe→inject ③ 세션 종료→큐→워커→리포트→검토 완료 |
| 60 | API 계약 표(화면이 호출하는 API, 화면이 받는 이벤트) | `common/contracts.md`를 그대로 표로 |
| 61 | 진행 이벤트 발행과 구독(Event-Driven, Publish-Subscribe) 그림 | WS 이벤트별 화면 영역: message.new→메시지, agent.progress→입력 중, document.released→문서 탭, session.ended→디브리핑 |
| 62~64 | 배포 아키텍처(N-tier, Trust Boundary), compose 표(서비스·기술·포트·공개·선행), Layer별 Tier 배치 표 | 공개 포트는 web·api만. 내부: business-mcp 9101, rag-mcp 9102, worker, postgres 5432, rabbitmq 5672 |
| 65 | MCP 연결과 문서 색인(실시간 Client-Server, 오프라인 Pipe-and-Filter) 그림. Embedding 모델·차원을 메타데이터에 남김 | 같은 그림. doc_chunks에 model=bge-m3, dim=1024 기록 |
| 66 | Summary 표(설계 기준, 구성도, 두 경로, Trust Boundary, MCP 연결) | 보고서 아키텍처 장 마지막에 같은 요약표 |

## 보고서 작성 시 체크
- 그림마다 범례(49쪽) 모양을 지킨다.
- 구성도에는 번호, 번호별 표에는 프로토콜 열을 둔다.
- 금지 사항 표를 넣는다. 평가에서 "금지 사항을 어긴 코드가 없는지" 본다.
- Layer(논리)와 Tier(배포)를 구분해 표로 맞춘다.
