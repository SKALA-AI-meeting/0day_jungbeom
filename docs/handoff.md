# 오케스트레이터 핸드오프

다음 오케스트레이터(에이전트 세션)가 이 문서만 읽고 바로 이어가기 위한 상태 기록이다. 읽는 순서: 이 문서 → `AGENTS.md` → `docs/plan.md` → `docs/dev-process.md` → 필요한 역할 문서.

## 현재 상태 (2026-10-20)

- M0 완료. 문서·계약·카탈로그·회사 문서·대본·compose·스키마·Makefile·ruff 설정이 `main`에 있다. 앱 코드는 아직 없다(각 `services/*`, `apps/web`은 README만).
- Codex 설계 리뷰 1차 반영 완료(커밋 4aa8eca). 재검토 결과는 아래 "리뷰 상태".
- 환경: `infra/.env`에 OpenAI·LangSmith 키가 들어 있다(git 무시). `infra/.env.local`은 아직 없다(foundation이 만든다).
- 저장소: GitHub `SKALA-AI-meeting/Day-0_zaeho`, main 단일 브랜치. worktree 없음.
- Herdr: 리뷰 pane `design-reviewer`(w1J:p4, Codex)는 재검토가 끝나면 닫는다.

## 다음 행동

1. **W0 foundation pane 기동** (Claude, 편집·자동 검토). 브리프는 아래 템플릿 + `docs/plan.md` 파일 소유권의 foundation 행 + `docs/api/design.md` 구조 표. 완료 기준은 plan.md M0.5 행.
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

Herdr 기동(참고): `herdr pane split --current --direction right --cwd <worktree> --no-focus` → `herdr agent start <이름> --kind claude --pane <id> -- <플래그>`. 모델·플래그는 `~/.claude/skills/herdr-dispatch` 역할표(구현: sonnet/medium, 어려운 것: opus/high). 리뷰는 codex gpt-6.1-sol high 읽기 전용(`-s read-only -a never -c features.fast_mode=false`). Claude pane은 처음 보는 폴더에서 신뢰 확인에 멈추므로 worktree를 만든 뒤 사용자에게 한 번 열어 달라고 요청한다.

## 리뷰 상태

| 리뷰 | 결과 | 남은 항목 |
|---|---|---|
| 1차 설계 리뷰 (Codex) | A~E 반영 (커밋 4aa8eca) | — |
| 재검토 (Codex) | 해소 22 / 부분 해소 14 / 새 불일치 9 → 전부 문서에 반영 | — |
| 최종 리뷰 | 재검토 반영분 + plan·dev-process·handoff 확인 | (아래 갱신) |

재검토에서 반영한 결정(설계 방향은 바뀌지 않음, 세부 규칙만 확정):
- 카드 실패는 최초 포함 총 3회 시도 후 세션 failed. 재실행은 fired 시 기록한 같은 run_id를 쓴다.
- 멱등 키: 메시지 (run_id, seq) · 문서 수정 (part_no, run_id) · 관찰 (element, window_start). document_revisions에 본문 스냅샷 저장.
- 리포트 워커 순서: interrupt 체크포인트 → draft 저장 → ack. approve 발행도 outbox(`approve_enqueued_at`). DLQ는 워커 소비자가 report_failed 호출.
- 세션 종료: submitted_at 커밋 → end 실행(고정 run_id) → completed → 큐 발행. 마지막 관찰이 리포트보다 먼저 저장됨.
- RAG 청크 키에 catalog_version 포함, 검색은 채용 건 버전만.
- 분업 최소 조건(2번 지원자, 4·5 중 하나 동료 단독)과 미합의 시 다음 이벤트 도래 때 마지막 안 확정을 PRD 6.2·F-21에 반영.
- 시작 전 JWT 만료는 /consent 재호출, 시작 후는 /resume. 운영 목표 수치를 테스트 단언과 통일(±10초, 복구 90초, 동시 5 대본).
- web·report-worker healthcheck 추가. foundation 완료 기준에서 rag 검색·WS 제외. web-polish로 ui·globals.css 소유권 이양 시점 명시.

## 진행 표

| 파도 | 트랙 | pane | 상태 | 리뷰 | 병합 커밋 |
|---|---|---|---|---|---|
| W0 | foundation | — | 대기 | | |
| W1 | prompts | — | 대기 | | |
| W1 | api-admin | — | 대기 | | |
| W1 | api-candidate | — | 대기 | | |
| W1 | business-mcp | — | 대기 | | |
| W2 | rag-mcp | — | 대기 | | |
| W2 | web-admin | — | 대기 | | |
| W2 | web-office | — | 대기 | | |
| W2 | worker | — | 대기 | | |
| W3 | agent-min / agent-session | — | 대기 | | |
| W3 | agent-assistant | — | 대기 | | |
| W3 | web-polish | — | 대기 | | |
| W3 | e2e-runner | — | 대기 | | |
| W4 | docs-final | — | 대기 | | |

## 결정 요약 (자세한 것은 docs/decisions.md)

요소 선택은 채용 건 단위 1~4개. 에이전트는 api 모듈. 관찰은 규칙+레이블 분류. Recovery는 재시도 2회 후 폴백, 대체 모델 없음. 사람 승인은 리포트 그래프 interrupt. 시계는 접속과 무관하게 흐름. 임베딩 BGE-M3 로컬. MVP 제외 목록은 plan.md. 동시 pane 4개, 인프라만 docker.
