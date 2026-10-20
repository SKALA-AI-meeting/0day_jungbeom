# Day Zero 설계 문서

PRD(`../PRD.md`)를 구현 가능한 수준으로 구체화한 문서다. `review/design-review.pdf`는 2026-10-20 1차 설계 시점의 검토 요약(스냅샷)이며 이후 리뷰 반영으로 세부(킥오프 분담안, State 필드, 색인 도구명, 상태 수, 트랙 구성)가 바뀌었다. 정본은 항상 이 폴더의 md 문서다. 역할별 폴더로 나눴고, 각 역할은 `common/`과 자기 폴더만 읽으면 작업할 수 있다.

## 읽는 순서

| 역할 | 먼저 | 그다음 |
|---|---|---|
| 모두 | `common/architecture.md`, `common/scenario-model.md`, `plan.md` | `decisions.md` |
| 프론트 | `common/contracts.md`, `frontend/design-direction.md` | `frontend/design-system.md`, `frontend/design.md` |
| api(서버) | `common/contracts.md`, `common/data-model.md` | `api/design.md` |
| 에이전트 | `common/harness.md`, `common/contracts.md` | `agent/design.md` |
| MCP | `common/contracts.md`, `common/data-model.md` | `mcp/design.md` |
| 워커·인프라 | `common/data-model.md` | `worker-infra/design.md` |
| 테스트 | `common/scenario-model.md` | `common/testing.md` |
| 에이전트·워커·프론트(리포트) | `common/rubric.md` | 평가표 규칙·지표 정의 |

## 파일

- `common/architecture.md`: 구성 요소, 원칙, 요청 흐름, 저장소 구조, ISO/IEC 25010 대응
- `common/rubric.md`: 평가표 항목 값·점수 규칙, 조건 문법, 지표 정의, 담당자 조정
- `common/scenario-model.md`: 요소 카탈로그, 이벤트 카드, 시나리오 조립과 시점 배치
- `common/data-model.md`: 테이블, 상태 전이
- `common/contracts.md`: REST·WebSocket·내부 API·MCP 도구 계약과 예시
- `common/harness.md`: 하네스 8요소의 구현 위치
- `common/testing.md`: 세션 빠른 조립, e2e 러너, 기록, 단언
- `plan.md`: 마일스톤, 파도별 병렬 작업 방식, 파일 소유권, 모델 운영 규칙
- `dev-process.md`: 도구, 로컬 실행, TDD 범위, 브랜치·리뷰·병합 규칙
- `handoff.md`: 다음 오케스트레이터가 바로 이어가기 위한 현재 상태·다음 행동·진행 표. `handoff/{briefs,reports,reviews}/`에 트랙별 브리프·완료 보고·Codex 리뷰 원문
- `share/`: 팀 공유용 아키텍처 한 장(HTML)과 기획 보고서(HTML·PDF)
- `frontend/`, `api/`, `agent/`, `mcp/`, `worker-infra/`: 역할별 상세 설계와 완료 기준. 프론트는 `frontend/design-direction.md`(오피스 형태·협업 모델) → `design-system.md`(토큰·컴포넌트) → `design.md`(화면 규칙) 순
- `assignment/evaluation.md`: 평가표와 항목별 근거, 레퍼런스와의 차이
- `assignment/reference-architecture.md`: 과제 레퍼런스 아키텍처의 뷰·표기·표 구성과 보고서 적용 방법
- `decisions.md`, `prd-change-proposals.md`, `review/`
