# Day Zero — 협업 인성 관찰 (PR1)

AI 페르소나 2명(팀장 한서윤 · 개발자 이도현)과 지원자가 **한 채팅방에서 3자 대화**를 하고,
조용한 관찰 에이전트가 대화에서 **C01·C02·C03·C05** 행동 근거를 수집한다. Admin은 근거를 시각적으로 확인한다.
(C04 문제 해결, C06 AI 활용은 PR1 범위 밖 — 인성 관찰에 집중)

## 실행

```bash
# 1) 백엔드 (루트 .env 의 OPENAI_API_KEY 사용, 모델은 LLM_MODEL 로 변경 가능)
cd backend && uv sync --python 3.12
uv run --python 3.12 uvicorn app.main:app --port 8765     # 8000 은 다른 서비스가 쓰는 경우가 많아 8765 사용

# 2) 프런트 (Vite proxy → 8765. 바꾸려면 VITE_API_TARGET)
cd frontend && npm install && npm run dev                  # http://localhost:5173
```

- 지원자: `/` (별칭 → 카테고리 → 상황·동의 → 3자 대화방 + 마일스톤 + 노트)
- 관리자: `/admin` (목록) → `/admin/:id` (타임라인·히트맵·근거·원문·painpoint 출처)
- `MOCK_LLM=1` 이면 키 없이 결정적 mock 으로 동작 (테스트용): `cd backend && uv run --python 3.12 pytest`
- `ADMIN_TOKEN` 을 설정하면 `/api/admin/*` 에 `x-admin-token` 헤더가 필요(화면에서 입력). 미설정 시 열려 있음.
- `backend/scripts/smoke_real.py <delay|scope|conflict|workload>` : 실제 LLM 으로 스크립트 대화를 돌려 근거를 출력

## 구조

```
backend/app/
  scenarios.py  4개 카테고리 × (소통→조율→타협→설득) 고정 비트, 역량 정의, 지원자 공개용 변환
  graph.py      LangGraph: START→(observe ∥ plan)→react→gate→{stay | beat | closing}
  llm.py        director / persona / observer 프롬프트 (OpenAILLM, MockLLM)
  service.py    세션 수명주기, SSE 이벤트, 리포트 생성(실패 시 3회 재시도 후 failed)
  store.py      SQLite 문서 저장 / main.py FastAPI
frontend/src/   Home · Session(채팅+단계+노트) · AdminList · AdminDetail
docs/painpoints.{json,md}   카테고리별 현업 painpoint 웹 조사(출처·한계 병기)
```

## 설계 원칙 (PRD 반영)
- **같은 조건**: 단계 진입 시점과 전달 내용(`must_convey`)은 고정, 문장은 페르소나가 바꿔 말함. 단계당 지원자 발화 2회로 전환.
- **상황 비공개 / 종료 후 디브리핑**: 지원자 API 는 비트·페르소나 입장·관찰 결과를 내려주지 않고, 종료 후 `debrief` 로 설명.
- **점수·합격 없음**: 관찰은 `positive/neutral/risk` 신호(면접 확인용)일 뿐이며, 관련 행동이 없으면 "기록되지 않음".
- **근거 검증**: 관찰 `quote` 가 지원자 실제 발화에 없으면 폐기(환각 근거 차단).

## 알려진 한계 / 다음 PR
- 인증은 선택적 공유 토큰 수준. 사용자 인증·초대 링크(72h)·기업 분리는 미구현.
- MCP(business-mcp, rag-mcp), Harness, 큐(재시도)는 평가표 항목이나 PR1 범위 밖.
- 마일스톤 전환은 규칙 기반(단계당 2턴). 지원자 반응 기반 분기는 없음.
- painpoint 일부는 오래된/벤더 자료(각 항목에 한계 표기). 시나리오 설계 참고용이며 통계적 근거로 쓰지 말 것.
- 페르소나가 지원자에게 대체로 우호적으로 수렴하는 경향이 있어, 갈등 강도 조절은 추가 튜닝 필요.
