# 브리프: fix-p3 트랙 (P2·P3 리뷰에서 모인 결함 일괄 수정, 개발 Codex)

역할: 아래 결함을 고친다. worktree `../Day-0_zaeho.worktrees/fix-p3`(현재 폴더), 브랜치 `track/fix-p3`. 기준 커밋 main 최신. 테스트는 각 항목당 1건(happy path + 그 결함의 반례). 커밋은 자기 브랜치에만, 한국어 한 문장 + 본문에 테스트 명령. 키 값 출력 금지. 주석은 역할·알아야 할 로직·예외 의도 수준. `docs/common/*`·`tests/fixtures/contracts/` 수정 금지(필요하면 보고서에 변경 요청). 같은 시각에 web-integrate(`apps/web/e2e/session.mjs`만)·e2e-runner(`tests/e2e`·`tests/eval`·`scenarios/e2e`, 실 스택 사용 중)가 돈다 — **실 스택·공용 DB dayzero를 쓰지 말고** 격리 DB·FakeLLM으로만 검증한다.

## 읽을 것
AGENTS.md, `docs/handoff.md`의 "P2 진행 중 모인 api 수준 변경 요청"·"P3에서 모인 fix 요청" 절, `docs/common/contracts.md`(agent.progress·내부 messages 페이징·Report connection_gaps), `docs/agent/design.md`(observe·노드), `docs/common/rubric.md`(aux 지표·근거), 보고서 `docs/handoff/reports/web-integrate-report.md` 2라운드 변경 요청, `agent-session-report.md`(문구 요청), `e2e-runner-report.md` 변경 요청 1.

## 항목 (전부)
1. **agent.progress 시각** (`services/api/app/agent/session/nodes.py` route/분류): 메시지 실행 시작(분류 LLM 앞)에 `started`, 응답 저장 뒤 `finished`. 테스트: FakeLLM 분류 지연 중 hub에 started가 먼저 옴.
2. **refresh_messages 페이징** (`app/agent/session/common.py`): `since_t_min - 0.02` 대신 (created_at, id) 또는 offset 커서로. 반례: 같은 t_min에 assistant 메시지 50개 + 뒤의 DM 1건 → DM을 찾음. 페이지 한도 소진 시 성공처럼 처리하지 않음.
3. **정직 aux 근거** (`app/agent/observe/`): aux 지표(claims_colleague_work 등)의 `evidence_ids`에 판정한 보고 메시지 id를 넣는다(true·false 모두). 반례: fair_report + claims_colleague_work=false → 워커 `honest_no_misattribution`이 충족(기록 없음 아님). 워커 쪽 수정이 더 맞으면 `services/report-worker/`도 허용.
4. **팀장 보고 요청 문구** (`scenarios/missions/planning/prompts/manager.md`·`cards.yaml` honesty_report brief): 팀장이 스스로 현황을 정리하거나 킥오프 끝에 "다 됐다고 전해도 되죠?"가 붙지 않게 규칙 문장 추가. 카탈로그 변경이므로 catalog_version이 바뀐다 → 보고서에 새 값.
5. **리포트 짧은 끊김** (`apps/web/components/admin/report-view.tsx`·`format.ts`): 연결 끊김 목록에서 1분 미만은 "짧은 끊김 n회"로 접고, 펼치면 초 단위. 카드 창 겹침 칩은 그대로. vitest 1건.
6. **"입력 중…" 채널 구분** (`apps/web/components/office/`): active_runs의 실행이 DM 응답이면 DM 채널에만 표시(run의 채널 정보가 State에 없으면 변경 요청으로 적고 보류).

## 완료
`make test`·`make lint` 통과. 보고서 `docs/handoff/reports/fix-p3-report.md`: 항목별 파일·테스트·결과, 새 catalog_version, 변경 요청, e2e-runner에 알릴 것(재실행 필요한 대본). 마지막 응답은 경로 한 줄.
