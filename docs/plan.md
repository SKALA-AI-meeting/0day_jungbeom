# 개발 계획

혼자 개발하되 Herdr pane으로 도메인별 Claude 개발 pane을 병렬로 띄우고, 끝난 트랙은 Codex가 리뷰한다. pane마다 git worktree와 브랜치(`track/<이름>`)를 쓰고, 리뷰 통과 후 오케스트레이터가 main에 병합한다. 리뷰 반영(2026-10-20): 공용 기반을 먼저 한 트랙이 만들고, 최소 종단 흐름을 M1에 당긴다.

## 마일스톤

| 단계 | pane | 범위 | 의존 | 완료 기준 |
|---|---|---|---|---|
| M0 | (오케스트레이터) | 문서, 계약, 카탈로그, 회사 문서, 대본, compose, 스키마 | — | 완료 |
| M0.5 | foundation | 서비스 5개의 최소 앱(Dockerfile, `/health`, 의존성·lockfile), api 공용 기반(config, db, models, auth, SessionService, scenario, hub, queue, masking, AgentRunner+Fake), web 기본(Next 앱, 토큰, 공용 컴포넌트 props만, mocks/ 골격), 테스트 픽스처 골격 | M0 | `docker compose up` 전부 healthy(각 서비스는 /health만 응답), SessionService 단위 테스트, 조립 결과가 scenario-model.md 수치와 일치, Fake runner로 메시지→내부 저장→hub 브로드캐스트 단위 테스트(WS·rag 검색은 M1 트랙) |
| M1 | prompts | 페르소나 프롬프트, 카드 brief 문구, 금지어 패턴, 관찰 레이블 정의·예시. 코드 없음 | M0 | 리뷰 통과 |
| M1 | api-admin | /admin, /internal 라우터 | foundation | 계약 예시대로, 격리·검증·409 테스트 |
| M1 | api-candidate | /s, /sessions, WS, 스케줄러, 공개·만료·재발행 | foundation | 6분 세션 시계대로, 재시작 재실행, ack·재연결 |
| M1 | business-mcp | 도구 10개 | foundation | Inspector, 오류 코드, 멱등 전달 |
| M1 | rag-mcp | 색인·검색·공개 필터 | foundation | 검색 응답, 차단, 재색인 |
| M1 | web-admin | 관리자 5화면 | foundation(토큰·컴포넌트 props) | mock으로 전 화면, 7상태, draft/final 배지 |
| M1 | web-office | 지원자 화면과 가상 오피스 | foundation | mock으로 전 화면, ack·진행 표시·재연결 |
| M1 | worker | 리포트 그래프, 큐 2종, 재시도·DLQ | foundation | draft 멈춤→approve 재개→final, DLQ |
| M1 끝 | agent-min (agent-session 트랙의 1단계) | respond 노드 + MCP 클라이언트 + guard로 최소 종단 흐름 | api-*, mcp | 메시지→그래프→rag→post→WS 연결 테스트 |
| M2 | agent-session | 전이표 전체, observe(규칙·분류 포함), 카드 실행, 복구, 체크포인터 | agent-min, prompts | agent/design.md 완료 기준 |
| M2 | agent-assistant | 어시스턴트 그래프 | rag-mcp, prompts | 공개 문서만 인용, 한도 |
| M2 | web-polish | emilkowalski/skills로 디자인 다듬기, 모션, break-ui 점검 | web-* | review-animations·break-ui 통과 |
| M3 | e2e-runner | 러너, 대본 5개, 장애 주입, 근거 정확성 픽스처, 기록 | 전부 | 단언 전부 통과, 기록 커밋 |
| M3 | fix-* | 실패 영역별 | e2e | 해당 단언 통과 |
| M4 | docs-final | README 실행법, 레퍼런스 형식의 아키텍처 그림(6뷰·번호·금지 사항·Layer/Tier), 평가표 근거 표, 120분 실세션 기록 | 전부 | 새 환경에서 README만으로 기동 |

## 병렬 작업 방식

동시에 띄우는 개발 pane은 **최대 4개**다. 각 파도(wave)는 pane 4개 이하로 띄우고, 끝난 트랙부터 리뷰·병합한 뒤 다음 트랙을 채운다.

| 파도 | 동시 pane | 병합 순서 | 비고 |
|---|---|---|---|
| W0 | foundation (1) | 단독 | 끝나야 다음 파도 시작. 리뷰 후 main 병합 |
| W1 | prompts, api-admin, api-candidate, business-mcp | api-admin → api-candidate → business-mcp → prompts | 모두 foundation 위에서 mock으로 독립 |
| W2 | rag-mcp, web-admin, web-office, worker | 순서 무관 | W1 중 끝난 자리에 바로 채움 |
| W3 | agent-min → agent-session, agent-assistant, web-polish, e2e-runner | agent-session → agent-assistant → e2e-runner → web-polish | agent-min은 api-*·business-mcp 병합 후 시작 |
| W4 | fix-* (필요한 만큼, 4개 이내), docs-final | | |

규칙:
- 한 pane은 트랙 하나, 트랙이 끝나면 pane을 닫는다. 리뷰 pane은 별도로 띄우고 끝나면 닫는다.
- 파도 안에서 서로 파일을 공유하지 않는다(소유권 표). 공유 파일이 필요하면 foundation 변경 요청으로 올린다.
- 병합 전 `main`에서 `make test`와 `make lint`가 통과해야 한다.
- 오케스트레이터는 파도마다 "띄움 → 완료 보고 확인 → 리뷰 → 병합 → 다음" 기록을 `docs/handoff.md`의 진행 표에 남긴다.

## 파일 소유권

| 트랙 | 소유 | 비고 |
|---|---|---|
| foundation | `services/*/Dockerfile`, `pyproject.toml`·lockfile 전부, `services/api/app/{main,config,db,auth,hub,queue,masking}.py`, `app/models/`, `app/services/`, `app/agent/runner.py`, `apps/web/{package.json,app/layout.tsx,app/globals.css,components/ui/,mocks/,lib/api.ts}`, `tests/conftest.py`, `tests/fixtures/` | 이후 변경은 오케스트레이터 승인 |
| api-admin | `app/routers/{admin,internal}.py`, 해당 테스트 | |
| api-candidate | `app/routers/{candidate,ws}.py`, `app/scheduler.py`, 해당 테스트 | |
| prompts | `services/api/app/agent/prompts/`, `scenarios/catalog.yaml`의 brief·labels·debrief 문구 | |
| agent-session | `app/agent/{session,observe,llm,guard,mcp_client}/` | agent-assistant는 llm·guard·mcp_client를 import만 |
| agent-assistant | `app/agent/assistant/` | |
| business-mcp, rag-mcp, worker | 각 `services/<이름>/` | |
| web-admin | `apps/web/app/admin/`, `components/admin/` | ui 컴포넌트 내부는 수정하지 않음 |
| web-office | `apps/web/app/s/`, `components/office/`, `lib/ws.ts` | |
| web-polish | `components/ui/` 내부, `globals.css`, `public/brand/` | foundation 병합 후 W3 시작 시점에 이 두 경로의 소유권이 foundation에서 web-polish로 넘어온다. props 변경 금지 |
| e2e-runner | `tests/e2e/`, `tests/eval/`, `scenarios/e2e/`, `scripts/make_session.py` | |

## 병렬 작업 규칙
- 트랙은 `docs/common/contracts.md`와 foundation 소유 파일을 바꾸지 않는다. 필요하면 보고하고 멈춘다.
- 다른 트랙 폴더를 수정하지 않는다. 필요한 것이 없으면 mock을 자기 폴더에 둔다.
- 완료 시 자기 완료 기준을 직접 실행하고 명령과 결과를 보고한다. 연결 테스트는 M1 끝에 한다.
- 커밋은 자기 브랜치에만. main 병합은 오케스트레이터.

## 모델 운영
- 개발 Claude, 리뷰 Codex(gpt-6.1-sol). 같은 모델이 만들고 검토하지 않는다.
- Codex 한도 소진 시 같은 역할을 개발과 다른 Claude 모델로 바꾼다.
- 끝난 pane은 바로 닫는다. 맥락이 바뀌면 새 pane. 오케스트레이터는 브리프·기동·병합·판단만 한다.

## 운영 제약
- api는 단일 프로세스(세션 Lock이 메모리). 수평 확장은 범위 밖, 향후 분리 지점은 AgentRunner 경계.

## MVP 제외
F-05 근거 원문 이동, F-06 회사 문서 관리·승인, F-07 면접 질문 제안, F-25 무응답 확인, 세션 길이 선택 UI, 타임라인 미리보기, LLM 페르소나 지원자 e2e, 리치 에디터, 동시 편집, 색인 도구의 임의 경로·업로드, 복수 디자인안 비교.

## 확장 후보 (M3 이후, 시간이 남으면)
- 세션 내 승인: 상호 리뷰에서 동료가 지원자 파트를 고치기 전에 허락을 구함(`write_document_part` 앞 interrupt, 지원자 수락·거절로 같은 thread 재개). 리포트 승인이 끝난 뒤에만 고려한다.

## worktree
```
sh scripts/worktree.sh api-admin      # ../Day-0_zaeho.worktrees/api-admin 에 track/api-admin
sh scripts/worktree.sh --remove api-admin
```
