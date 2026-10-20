# 오케스트레이터 핸드오프

다음 오케스트레이터(에이전트 세션)가 이 문서만 읽고 바로 이어가기 위한 상태 기록이다. 읽는 순서: 이 문서 → `AGENTS.md` → `docs/plan.md` → `docs/dev-process.md` → 필요한 역할 문서.

## 현재 상태 (2026-10-20)

- M0 완료. 문서·계약·카탈로그·회사 문서·대본·프롬프트 폴더(README만)·compose·스키마·Makefile·ruff 설정이 `main`에 있다. 앱 코드는 아직 없다(각 `services/*`, `apps/web`은 README만).
- 설계 리뷰 5라운드(Codex 4, Claude UX 1) 전부 반영 완료. 마지막 반영 커밋은 `git log`의 최신. W0 foundation은 병합됐다(c9fa550). **W1 4개 트랙 진행 중**(브리프는 오케스트레이터 세션 scratchpad의 `brief-<트랙>.md`, 보고서는 `<트랙>-report.md`). `infra/.env.local`은 main에 있고 worktree마다 `.env`·`.env.local`을 복사해 준다.
- 환경: `infra/.env`에 OpenAI·LangSmith 키가 들어 있다(git 무시). `infra/.env.local`은 아직 없다(foundation이 만든다).
- 저장소: GitHub `SKALA-AI-meeting/Day-0_zaeho`, main 단일 브랜치. worktree 없음.
- Herdr: 열려 있는 리뷰·개발 pane 없음. Claude pane은 처음 보는 폴더(worktree)에서 폴더 신뢰 확인에 멈추므로, worktree를 만든 뒤 사용자에게 한 번 "Yes, I trust"를 눌러 달라고 한다. Claude pane의 긴 출력은 `herdr agent read`로 다 못 읽으므로 결과를 파일로 저장하게 시킨다. Codex 리뷰어는 별도 탭에 pane으로 띄우고(`-s workspace-write -a never`, read-only면 파일 저장이 막힘) 결과를 worktree의 `REVIEW.md`(추적 안 함, 병합 전 삭제)에 쓰게 한다. `codex exec`를 백그라운드로 쓰려면 반드시 `</dev/null`.

## 다음 행동

1. **W0 foundation pane 기동** (Claude, 편집·자동 검토). 브리프는 아래 템플릿 + `docs/plan.md` 파일 소유권의 foundation 행 + `docs/api/design.md` 구조 표 + `docs/dev-process.md`(app.run 두 리스너, compose.dev.yml, pytest live 마커, seed 위치). 완료 기준은 plan.md M0.5 행.
2. foundation 완료 보고 확인 → Codex 리뷰 pane → 반영 → squash 병합 → worktree 제거.
3. W1 pane 4개 기동(prompts, api-admin, api-candidate, business-mcp).
4. 이후는 `docs/plan.md` 파도 표대로.

## pane 브리프 템플릿

```
역할: <트랙 이름> 개발. worktree <경로>, 브랜치 track/<이름>.
읽을 것: AGENTS.md, docs/common/contracts.md, docs/common/<관련>.md, docs/<역할>/design.md, docs/plan.md의 소유권·완료 기준.
범위: docs/plan.md의 <트랙> 행. 소유권 밖 파일은 수정하지 않는다. 계약이 바뀌어야 하면 멈추고 보고한다.
방식: TDD, happy path 중심(docs/dev-process.md). LLM은 mock. 커밋은 자기 브랜치에만.
완료: 완료 기준의 각 줄을 직접 실행해 명령과 결과를 보고한다. 파일 수정 목록과 남은 문제를 함께.
```

Herdr 배치 규칙(사용자 결정 2026-10-20): **worktree(트랙)마다 탭 하나**를 만들고(`herdr tab create --workspace $HERDR_WORKSPACE_ID --cwd <worktree> --label <트랙>`; 루트 pane의 쉘이 홈에서 열리는 경우가 있으니 `herdr pane run <pane> "cd <worktree>"` 뒤에 agent start), 그 탭 안에 작업 pane과 리뷰 pane을 둔다. 오케스트레이터 탭에는 pane을 늘리지 않는다. 트랙이 병합되면 탭째 닫는다.

Herdr 기동(참고): `herdr pane split --current --direction right --cwd <worktree> --no-focus` → `herdr agent start <이름> --kind claude --pane <id> -- <플래그>`. 모델·플래그는 `~/.claude/skills/herdr-dispatch` 역할표(구현: sonnet/medium, 어려운 것: opus/high). 리뷰는 codex gpt-6.1-sol high 읽기 전용(`-s read-only -a never -c features.fast_mode=false`). Claude pane은 처음 보는 폴더에서 신뢰 확인에 멈추므로 worktree를 만든 뒤 사용자에게 한 번 열어 달라고 요청한다.

## 리뷰 상태

| 리뷰 | 결과 | 남은 항목 |
|---|---|---|
| 1차 설계 리뷰 (Codex) | A~E 반영 (커밋 4aa8eca) | — |
| 재검토 (Codex) | 해소 22 / 부분 해소 14 / 새 불일치 9 → 전부 문서에 반영 | — |
| 최종 리뷰 (Codex) | 재검토 항목 해소 23 / 부분 6 → 전부 반영. 새 문서 지적 8건 반영. 설계 방향 변경 없음 | — |
| 3관점 최종 리뷰 (Codex, 192f973 기준) | 기획 11·개발 11·평가 9·미결정 13 → 전부 반영. 설계 방향 변경 표시 3건은 PRD 범위 안의 행동 규칙 확정으로 처리 | — |
| 개발·기획 리뷰 (Codex, 38a7eb5 기준) + UX 리뷰 (Claude) | 개발 14·기획 7·평가표 8·미결정 7, UX 지원자 20·담당자 14·당황 10 → decisions.md 같은 날짜 절대로 반영. 받아들이지 않은 것도 거기 기록 | — (다음 리뷰는 foundation 완료 후) |

2026-10-20 사용자 결정(기획 변경): **지원자 리드 고정**, **동료 = 회사 인재상 페르소나(성향 + 의무 액션 + 금지)**, **평가표(규칙 산출 기본 점수 + 담당자 조정)**, 리포트에 산출물 섹션. 기본값으로 정한 것: 상호 리뷰 양방향은 성향에 맡김, 동료 파트는 리뷰 시점에 완성본, 파트당 300~600자, 빈 파트 제출 허용(미작성 표시), 지원자는 점수를 보지 않음, 관리자 회사당 1명, 채용 건 수정·삭제 없음, 평가자 대화 열람은 근거 인용까지, 존중 창은 리뷰~보고 요청, 한국어·고정 인물.

3관점 리뷰·재검토에서 확정한 세부 규칙은 `docs/decisions.md`의 같은 날짜 절에 있다.


## 진행 표

| 파도 | 트랙 | pane | 상태 | 리뷰 | 병합 커밋 |
|---|---|---|---|---|---|
| W0 | foundation | w1J:p8(닫음) | 병합 완료 | Codex 차단 5·권장 5 반영 | c9fa550 |
| W1 | prompts | 닫음 | 병합 완료 | Codex 차단 4 반영 | fb963e0 |
| W1 | api-admin | 닫음 | 병합 완료 | Codex 차단 6 반영 | 9447848 |
| W1 | api-candidate | w1J:pB | 리뷰 반영 중 | Codex 차단 7 | |
| W1 | business-mcp | w1J:pD(닫음) | 병합 완료 | Codex 차단 1·권장 1 반영 | 502b88b |
| W2 | rag-mcp | 닫음 | 병합 완료 | Codex 차단 1 반영 | (이 커밋) |
| W2 | web-admin | 탭 w1J:t6 | 진행 중 | | |
| W2 | web-office | 탭 w1J:t7 | 진행 중 | | |
| W2 | worker | 탭 w1J:t5 | 진행 중 | | |
| W3 | agent-min / agent-session | — | 대기 | | |
| W3 | agent-assistant | — | 대기 | | |
| W3 | web-polish | — | 대기 | | |
| W3 | e2e-runner | — | 대기 | | |
| W4 | docs-final | — | 대기 | | |

## 결정 요약 (자세한 것은 docs/decisions.md)

요소 선택은 채용 건 단위 1~4개. 지원자는 리드(분업 결정·재지시·보고). 동료는 회사 인재상 페르소나(성향 자유 + 의무 카드 + 선점 금지, 카탈로그 `persona`). 평가표는 요소당 4항목, AI 분류를 입력으로 규칙이 1/0/기록 없음 산출, 담당자가 조정해 확정(`docs/common/rubric.md`). 리포트는 산출물 + 관찰·평가표 + AI 활용. 에이전트는 api 모듈, 작업 기억 `work_notes`, 중간 초안 texture. 관찰은 규칙 지표 + 레이블 분류, 창은 다음 요소 카드까지. Recovery는 재시도 2회 후 폴백, 대체 모델 없음. 사람 승인은 리포트 그래프 interrupt(검토 완료 = 평가표 조정 확정). 시계는 접속과 무관하게 흐름. 임베딩 BGE-M3 로컬. MVP 제외 목록은 plan.md. 동시 pane 4개, 인프라만 docker.
