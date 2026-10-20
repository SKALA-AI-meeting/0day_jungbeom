# 개발 계획

혼자 개발하되 Herdr pane으로 도메인별 Claude 개발 pane을 병렬로 띄우고, 끝난 트랙은 Codex가 리뷰한다. pane마다 git worktree와 브랜치(`track/<이름>`)를 쓰고, 리뷰 통과 후 오케스트레이터가 main에 병합한다.

## 마일스톤

| 단계 | pane | 범위 | 의존 | 완료 기준 |
|---|---|---|---|---|
| M0 | (오케스트레이터) | 문서, 스캐폴딩, 계약, 카탈로그, 회사 문서, compose, 스키마 | — | 이 문서 세트와 `infra/` 기동 |
| M1 | prompts | 페르소나 프롬프트, 카드 brief 문구, 금지어 패턴, 관찰 레이블 정의. 코드 없음 | docs | 리뷰 통과 |
| M1 | api-core | 인증 3종, 관리자 REST, 초대, 상태 전이, 내부 API, 시나리오 조립 | skeleton | 계약의 엔드포인트가 예시대로 동작 |
| M1 | api-realtime | 지원자 REST, WebSocket, 스케줄러, document_releases, 진행 이벤트 중계 | skeleton | 6분 세션이 시계대로 종료되고 큐 발행 |
| M1 | business-mcp | 도구 10개, 오류 형식, api 호출 | skeleton | Inspector로 도구 확인, 오류 코드 테스트 |
| M1 | rag-mcp | 색인, 검색, 공개 전 차단, 도구 4개 | skeleton | 시드 후 검색 응답, 차단 테스트 |
| M1 | web-design | emilkowalski/skills로 디자인 토큰, 로고·워드마크, 공용 컴포넌트, 핵심 화면 프로토타입 2~3안 | skeleton | 토큰·컴포넌트 문서와 프로토타입 페이지 |
| M1 | web-admin | 로그인, 채용 건 목록·생성, 지원자 목록·초대, 리포트·검토 완료 | web-design | mock으로 전 화면 동작 |
| M1 | web-office | 링크 입장, 동의, 대기, 가상 오피스(메신저·문서·보드·회사 문서·어시스턴트·타이머·진행 표시), 제출, 디브리핑 | web-design | mock으로 전 화면 동작, WS 재연결 |
| M1 | worker | 리포트 그래프(collect→draft→interrupt→finalize), 체크포인터, 큐 2종 소비, 금지어 검사, 재시도·DLQ | skeleton | 픽스처로 draft 후 멈춤, approve로 같은 thread 재개, 강제 실패 시 DLQ |
| M2 | observe-rules | 규칙 지표, 레이블 분류 호출, 재사용 판별. 순수 함수 + 단위 테스트 | prompts | pytest 통과 |
| M2 | agent-session | 세션 그래프, 체크포인터, guard, 하네스, MCP 클라이언트 | api, mcp, prompts, observe-rules | 6분 세션에서 카드 4개 정시 발생, 재시작 후 이어하기, trace |
| M2 | agent-assistant | 어시스턴트 그래프, 60회 한도, 인용 | rag-mcp, prompts | 공개 문서만 인용, 금지 질문 안내문 |
| M3 | e2e-runner | 러너, 대본 3개 + restart, 기록 | 전부 | 단언 전부 통과, 기록 커밋 |
| M3 | fix-* | e2e 실패 영역별로 그때그때 | e2e | 해당 단언 통과 |
| M4 | docs-final | README 실행법, 그림, 평가표 근거 표, 120분 실세션 기록 1회 | 전부 | 새 환경에서 README만으로 기동 |

## 파일 소유권 (같은 서비스를 나눈 트랙)

| 트랙 | 소유 | 공유(추가만, 충돌 시 오케스트레이터) |
|---|---|---|
| api-core | `services/api/app/routers/admin.py`, `auth.py`, `internal.py`, `models/`, `scenario.py` | `app/main.py` 라우터 등록 |
| api-realtime | `app/routers/candidate.py`, `ws.py`, `app/scheduler.py`, `app/hub.py` | `app/main.py` |
| agent-session / agent-assistant / observe-rules | `app/agent/session/`, `app/agent/assistant/`, `app/agent/observe/` | `app/agent/__init__.py` |
| web-design | `apps/web/components/ui/`, `app/globals.css`, `app/(design)/`, `public/brand/` | — |
| web-admin | `apps/web/app/admin/`, `components/admin/` | `components/ui/`(web-design이 만든 것만 사용) |
| web-office | `apps/web/app/s/`, `components/office/`, `lib/ws.ts` | `components/ui/` |

## 병렬 작업 규칙

- 트랙은 `docs/common/contracts.md`를 바꾸지 않는다. 바꿔야 하면 보고하고 멈춘다.
- 다른 트랙 폴더를 수정하지 않는다. 필요한 것이 없으면 mock을 자기 폴더에 둔다.
- 완료 시 자기 완료 기준을 직접 실행하고 명령과 결과를 보고한다.
- 커밋은 자기 브랜치에만. main 병합은 오케스트레이터.

## 모델 운영

- 개발 Claude, 리뷰 Codex(gpt-6.1-sol). 같은 모델이 만들고 검토하지 않는다.
- Codex 한도 소진 시 같은 역할을 개발과 다른 Claude 모델로 바꾼다.
- 끝난 pane은 바로 닫는다. 맥락이 바뀌면 새 pane.
- 오케스트레이터는 브리프·기동·병합·판단만 한다.

## MVP 제외

F-05 근거 원문 이동, F-06 회사 문서 관리·승인, F-07 면접 질문 제안, F-25 무응답 확인, 세션 길이 선택 UI, 타임라인 미리보기, LLM 페르소나 지원자 e2e, 리치 에디터, 동시 편집.

## 확장 후보 (M3 이후, 시간이 남으면)

- 세션 내 승인: 상호 리뷰에서 동료가 지원자 파트를 고치기 전에 허락을 구함. `write_document_part` 앞 interrupt, 메신저에 수락·거절 카드, 지원자 응답으로 같은 thread 재개. 존중·협력 관찰 신호로도 활용 가능.

## worktree

```
sh scripts/worktree.sh api-core      # ../Day-0_zaeho.worktrees/api-core 에 track/api-core 브랜치
sh scripts/worktree.sh --remove api-core
```
