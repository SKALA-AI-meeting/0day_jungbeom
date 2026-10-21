# arch-refresh 보고서

대조 기준: track/debate `f3a1b08`. 대상: `docs/share/architecture.html`, `docs/share/architecture-assets/*.svg`(평가 파이프라인·단계 전환 그림은 HTML 인라인본과 같이 고침).

## 바꾼 주장 (전 → 후, 근거)

| # | 전 | 후 | 근거 |
|---|---|---|---|
| 1 | 평가 검증: 수준 4·5는 근거 2개 이상(위반 시 거부) | 근거 1개의 수준 4·5는 거부 없이 3으로 깎음, 금지어는 거부, 확신도 상한은 clamp | `services/report-worker/report_worker/evaluate.py:178-181`, `:419-422` |
| 2 | 형식 오류·근거 부재 → 요소 단위 1회 재요청 | 차원별 거부 사유를 붙여 요소 단위 1회 재요청 | `evaluate.py:351-358`, `:399-408` |
| 3 | evaluate_failed 표시 언급 없음 | 리포트에서 "판단 보류 · 근거 부족 — 원문 기록 확인 권장"으로 표시 | `apps/web/components/admin/format.ts:47`, `docs/common/harness.md:16` |
| 4 | 칸마다 resolution·filled_by만 | 표시용 outcome(합의·지원자 결정·시간 초과)을 계산해 내림, 리포트 slots에 포함 | `services/api/app/services/common.py:102,125`, `docs/common/contracts.md:109` |
| 5 | 평가 입력 "사실 지표" | 사실 지표(빈칸 제출 여부는 맥락 참고만) | `services/api/app/services/facts.py:198-199`, `session.py:113-116`, `rubric.md:607` |
| 6 | 페르소나: 계획 밖 입장 1회 재생성 → 고정 문구 | 정해진 안내문 부착(자르기 → 검사 → 부착), 반복 발언 1회 재생성(도구 3회 예산 공유) 추가 | `docs/agent/design.md:80-81`, `agent/debate/persona.py:33-34,156` |
| 7 | 턴 규칙: 지명 응답 | 지명 응답은 먼저 부른 순서, 진행 질문인데 LLM이 0명이면 비판형 한 명 | `docs/agent/design.md:67` |
| 8 | guard: 연출 언급·판정 등 | 기획안 단계의 기여 칸 선점(credit 그룹, 해당 단계 발언에만) 추가 | `agent/guard/__init__.py:8`, `scenarios/missions/*/prompts/guard_patterns.yaml:107-110` |
| 9 | 한도: 응답당 도구 3회 | 응답당 도구 3회(반복 재생성과 예산 공유) | `persona.py:30,223-228` |
| 10 | 테스트: 가짜 시계 단위 테스트만 | 단계 시드(`make stage`)·시간 당기기·`LLM_FAKE`/`LLM_FAULT`·Playwright 단계 화면 테스트·playtest 드라이버·`eval-live` | `Makefile:62,71-74,98-100`, `tests/playtest/README.md`, `routers/internal.py:616,627` |

## 확인만 하고 그대로 둔 항목

약 25개: 서비스 8개와 포트(compose 서비스 목록), MCP 도구 이름·개수(debate 7, rag 3, assessment 6 — 그림의 "도구 7"은 debate-mcp), 토론 그래프 노드 이름(load·cards·turn·respond·guard·stance_check·wait_typing·apply·fill), 재시도 백오프 5·15·45초와 3회(`consumer.py:33-34`), heartbeat 30초/90초, typing 5초/6초(`hub.py:22`), 대기 최대 10초(`graph.py:42`), 메모리 3GB, assessment 토큰 헤더, 5요소·19차원, 카드 6장, 비용 상한 표기 등.

## 판단이 필요한 것

- 테스트 키트(항목 10)를 ③-2 그림 설명 문장 안에 한 문장으로 넣었다. 아키텍처 페이지 범위로는 길다고 보면 줄이거나 `docs/common/testing.md` 링크성 언급으로 줄일 수 있다.
- 빈칸 제출 경고 확인(`blank_warning_shown`)의 저장·표시는 페이지에 "맥락 참고만"으로만 적었다. 리포트 화면에 어떻게 보이는지는 별도 확인하지 않았다.
- `docs/handoff/reports` 외 문서는 건드리지 않았다.

## 리뷰 반영 (2차)

- `evaluate_failed`만 "판단 보류 · 근거 부족 — 원문 기록 확인 권장"이고, 활동 없음·해당 없음·이벤트 미발생·자동 제출 빈칸은 별도 사유임을 명시 (`apps/web/components/admin/format.ts:45-50`, rubric.md 5장).
- 표 3-2에 "지원자 제출" 행 추가: 저장 → 빈 칸 검사 → 빈칸 경고 → 제출 확인 → submit{blank_warning_shown}, 빈 칸 목록·경고 확인 여부 저장·관리자 표시 (`docs/frontend/design.md:188`, `contracts.md:300`). 평가 입력 문구도 이에 맞춤.
- outcome 기준 명시: 확정 시점 지지 3/4 이상이면 합의, 아니면 지원자 결정, 시간 초과 별도, AI 채우기는 항상 합의 (`contracts.md:109`).
- 정해진 안내문은 그 run 첫 화자에게만, 카드 고정 한 줄에는 안 붙임 (`docs/agent/design.md:80`).
