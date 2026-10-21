# Day Zero 설계 문서

PRD(`../PRD.md`)를 구현 가능한 수준으로 구체화한 문서이고, 이 파일이 문서 구조의 유일한 색인이다. 과제는 **"지원자 + AI 동료 3명의 채팅 토론(키워드 → 문제 상황 → 해결책 → 기획안)"**이다(2026-10-21 토론형 전환, `decisions.md` "2026-10-21 토론형 전환" 절). 업무 시뮬레이션 시기의 문서·브리프·보고·리뷰는 지웠고 git 33cfe90에 있다. 어긋나면 PRD와 `common/`이 맞다.

역할별 폴더로 나눴고, 각 역할은 `common/`과 자기 폴더만 읽으면 작업할 수 있다.

## 정본

| 무엇 | 정본 |
|---|---|
| 기획 | `../PRD.md` (`PRD.html`은 `sh build/build.sh`로 생성) |
| 토론형 전환 결정 | `handoff/briefs/brief-debate-pivot.md`(원문), `decisions.md` "2026-10-21 토론형 전환"(기록) |
| 구조, 하네스 | [architecture/overview.md](architecture/overview.md), [architecture/harness.md](architecture/harness.md) |
| MCP 도구, REST·WS 이벤트, 세션·칸 상태, 경로 | [contracts/README.md](contracts/README.md) (+ G-C 뒤 `tests/fixtures/contracts/`) |
| 테이블과 컬럼 | [architecture/data-model.md](architecture/data-model.md) |
| 페르소나, 카드, 키워드, 단계 규칙 | [product/scenario.md](product/scenario.md) |
| 요소별 하위 차원, 수준 앵커(BARS), 평가 에이전트 출력, 사실 지표 | [product/rubric.md](product/rubric.md) |
| 테스트 | [guides/testing.md](guides/testing.md) |
| 역할별 설계와 완료 기준 | [services/api.md](services/api.md), [architecture/agents.md](architecture/agents.md), [services/mcp.md](services/mcp.md), [services/report-worker.md](services/report-worker.md), [product/user-flows.md](product/user-flows.md)·[architecture/design-system.md](architecture/design-system.md) |
| 계획(단계·게이트·트랙 소유 파일) | `plan.md` |
| 작업 방식·도구·로컬 실행·리뷰·병합 | [guides/contributing.md](guides/contributing.md) |
| 현재 상태·진행 표·셋업·브리프 템플릿 | `handoff.md` |
| 결정 기록 | `decisions.md` |
| 과제 평가 기준 | `assignment/evaluation.md`, `assignment/reference-architecture.md` |

이름이 충돌하면 contracts(도구·이벤트·상태·경로) > data-model(테이블) > scenario-model(페르소나·카드) > rubric(평가) 순으로 따른다.

## 읽는 순서

| 역할 | 먼저 | 그다음 |
|---|---|---|
| 모두 | [architecture/overview.md](architecture/overview.md), [product/scenario.md](product/scenario.md), `plan.md` | `decisions.md` |
| 오케스트레이터 | `handoff.md`, [guides/contributing.md](guides/contributing.md) | `plan.md` 4절 |
| 프론트 | [contracts/README.md](contracts/README.md), [architecture/design-system.md](architecture/design-system.md)(관찰 목적·디자인 컨셉·레이아웃·UX 결정) | [architecture/design-system.md](architecture/design-system.md) |
| api(서버) | [contracts/README.md](contracts/README.md), [architecture/data-model.md](architecture/data-model.md) | [services/api.md](services/api.md) |
| 에이전트(턴 매니저·페르소나·의도 분류·어시스턴트) | [architecture/harness.md](architecture/harness.md), [contracts/README.md](contracts/README.md), [product/scenario.md](product/scenario.md) | [architecture/agents.md](architecture/agents.md) |
| MCP(debate·rag·assessment) | [contracts/README.md](contracts/README.md), [architecture/data-model.md](architecture/data-model.md) | [services/mcp.md](services/mcp.md) |
| 워커·인프라 | [architecture/data-model.md](architecture/data-model.md), [product/rubric.md](product/rubric.md) | [services/report-worker.md](services/report-worker.md) |
| 테스트 | [product/scenario.md](product/scenario.md) | [guides/testing.md](guides/testing.md) |
| 리포트(에이전트·워커·프론트) | [product/rubric.md](product/rubric.md) | 하위 차원·수준 앵커·평가 에이전트 출력·사실 지표 |

## 구조

```
docs/
├── README.md                 이 색인
├── plan.md                   단계·웨이브·게이트, 트랙 소유 파일, 정리 표
├── [guides/quickstart.md](guides/quickstart.md)            작업 방식, 도구, 로컬 실행, TDD 범위, 브랜치·리뷰·병합
├── handoff.md                현재 상태, 진행 표, 다른 머신 셋업, 브리프 템플릿
├── decisions.md              결정 기록(대체된 결정은 한 줄 요약)
├── common/                   architecture · contracts · data-model · scenario-model · rubric · harness · testing
├── frontend/                 design.md(관찰 목적·컨셉·레이아웃·화면 규칙·UX 결정) · [architecture/design-system.md](architecture/design-system.md)(토큰·컴포넌트)
├── api/ agent/ mcp/ worker-infra/   역할별 design.md
├── assignment/               evaluation.md · reference-architecture.md
├── handoff/briefs/           진행 중 트랙 브리프(brief-debate-pivot.md는 전환 결정 원문)
├── handoff/reports/          진행 중 트랙 완료 보고
├── handoff/reviews/          진행 중 트랙 리뷰 원문
├── review/ux-options.html    UX 시안(G-U 결정 근거)
└── share/architecture.html   팀 공유용 아키텍처 한 장
```

`handoff/` 아래 브리프·보고·리뷰는 트랙이 병합되면 지운다([guides/contributing.md](guides/contributing.md) "작업 방식").
