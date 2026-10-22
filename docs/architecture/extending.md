# 확장 가이드 — 화면·작업 종류·도구·차트를 더하는 법

이 문서는 "무엇을 어디에 더하면 끝까지 연결되는가"만 다룹니다. 필드 이름과 모양은 [api-contract.md](api-contract.md)가 기준입니다.

## 1. 화면(페이지)·모듈 추가 — `frontend/`

| 하고 싶은 것 | 고칠 곳 |
|---|---|
| 기존 영역에 페이지 하나 | 그 영역의 `src/modules/<area>/index.js` `routes`에 한 줄 (+ 필요하면 `nav`) |
| 새 영역(역할이 다른 화면 묶음) | `src/modules/<new>/index.js` 매니페스트(`id, role, login, home, nav, routes`, 선택 `signOutTo, brand, who`)를 만들고 `src/modules/index.js`의 `modules`에 추가. 새 `role`도 여기서 끝난다: `router.js`가 매니페스트의 역할을 `state/auth.js`에 등록하고(토큰 `dz_<role>_jwt`), 가드와 상단 바는 매니페스트만 읽는다. 그 역할의 로그인 화면은 `auth.set('<role>', token)`을 부른다 |
| 새 API 호출 | `src/api.js`의 `api` 객체에 동작 이름으로 추가. 브라우저는 `/api/**`(Spring)만 부른다 |
| AI 작업 진행 표시 | `streamTask(taskId, token, onEvent, signal?)`로 SSE를 받는다 (`TOKEN · TOOL_START · TOOL_END · PROGRESS · APPROVAL_REQUIRED · DONE · FAILED`) |
| 저장된 텍스트를 HTML로 | `src/utils/markdown.js`의 `renderMarkdown`만 쓴다 (markdown-it raw HTML off + KaTeX + DOMPurify). 다른 문자열을 `v-html`에 넣지 않는다 |

라우터(`src/router.js`)는 매니페스트에서 경로를 만들고, `meta.public`이 아닌 경로는 그 모듈의 `role` 로그인을 요구합니다.
권한 판단은 화면이 아니라 Spring이 합니다. 자세한 규칙은 [frontend/src/modules/README.md](../../frontend/src/modules/README.md).

## 2. 작업 종류(task type) 추가 — 끝에서 끝까지

예: 관리자가 세션 하나를 다시 요약해 달라는 `RESUMMARY` 작업.

```
Vue ─POST /api/ai/tasks─► Spring TaskService.create ─(rabbit|http)─► agent runner.HANDLERS[type].run
       ◄── SSE ── SseHub ◄── /internal/tasks/{id}/events ◄── EventPublisher (TOKEN/TOOL_*/DONE…)
                                     │ TaskFinishedEvent → TaskHandler.onFinished → (InboxContributor)
```

1. **Spring `TaskHandler`** — `backend/src/main/java/dev/dayzero/backend/task/ResummaryHandler.java`
   ```java
   @Component
   public class ResummaryHandler implements TaskHandler {
       @Override public String type() { return "RESUMMARY"; }
       @Override public boolean resumable() { return true; }          // 변경 도구 앞에서 사람 승인을 받는다면
       @Override public void onFinished(AiTask t, String status, Map<String, Object> data) { /* 업무 상태 반영 */ }
       @Override public Optional<Map<String, Object>> inboxItem(AiTask t) {
           return Optional.of(InboxItems.approval(t, json, "반영", "반려"));   // 체크리스트 카드 + actions 라벨
       }
   }
   ```
   - 빈으로 등록되기만 하면 `TaskHandlers`가 받는다. 등록되지 않은 type은 `TaskService.create`에서 400.
   - `candidateVisible()`이 `true`인 type만 지원자가 조회·구독할 수 있다(`TaskService.canSee`, `mine`).
   - `resumable()`이 `false`인데 Agent가 `APPROVAL_REQUIRED`를 보내면 Spring은 FAILED로 닫는다(영원히 멈춘 작업 방지).
   - thread id 형식은 `threadId(t)`를 재정의해 정한다(기본 `{type}:{taskId}`; `ReportHandler`는 `report:{sessionId}:{taskId}`).
   - 아직 type 이름으로 갈리는 곳: `Controllers.Tasks.create`(아래 2)와 `SessionService.adminView`의 `pending_approval`(세션 상세의
     보고서 승인 초안, REPORT 전용). 세션 상세에서 승인할 새 작업이면 이 두 곳도 고친다.
   - 사람 승인이 없는 작업의 예: `AnalyticsHandler`(ANALYTICS). `type()`과 `threadId`(`analytics:{sid}:{id}`)만 재정의하고
     `candidateVisible`·`resumable`은 기본값(false)이다. 만드는 규칙(관리자만, 같은 회사, 진행 중인 작업 재사용)은 `AnalyticsService`에 있다.
2. **작업을 만드는 입구** — 브라우저가 만들면 `Controllers.Tasks.create`의 `switch`에 case를 추가하고 업무 규칙(권한·상태)을
   `SessionService` 같은 서비스에 둔다(예: `case "ANALYTICS" -> analytics.request(u, sessionId)`). 시스템이 만들면 서비스에서
   `tasks.create(type, sessionId, companyId, createdBy, payload)`. 규칙을 핸들러에 두면 `서비스 → TaskService → TaskHandlers → 핸들러` 생성자 순환이 생기므로 서비스에 둔다.
3. **Agent `Handler`** — `agent/app/runner.py`의 `HANDLERS`에 한 줄.
   ```python
   Handler("RESUMMARY", _resummary_run, _resummary_resume, description="세션 요약 다시 만들기, 관리자 승인 뒤 저장")
   ```
   승인이 없는 작업은 `resume` 없이 `Handler("ANALYTICS", _analytics_run, description=…)`처럼 등록한다(`resumable: false`).
   `run(msg, ctx)`는 DONE 데이터(dict) 또는 `{"_interrupt": ask}`(그래프가 사람을 기다림)를 돌려주고, `resume(msg)`는 같은 thread에서
   `Command(resume=msg["resume"])`로 이어 간다. 거절 결과는 `{"approved": False, …}`(→ REJECTED), 거절 자체가 결정이면 `decision` 키를 넣는다(→ DONE).
   `handlers.Registry`는 중복·소문자 type을 거부한다. Spring은 기동 시 `GET /agent/handlers`로 양쪽 목록과 `resumable`을 비교해 경고만 남긴다(`AgentHandlerCheck`).
4. **LangGraph 그래프** — `agent/app/<name>_graph.py`. 노드는 `graph.traced`로 감싸 span을 남기고, 사람 승인이 필요한 노드는
   `langgraph.types.interrupt(ask)`로 멈춘다(`ask`에 `tool, reason, recommendation, flags, draft`를 넣으면 체크리스트 카드에 그대로 보인다).
   그래프는 `runner.graphs()`에서 공용 checkpointer(`harness/memory.py`)로 컴파일한다. 참고: `report_graph.py`, `account_review.py`.
5. **MCP 도구** — 업무 데이터는 `agent/mcp_servers/business/server.py`에 `@mcp.tool`로 추가하고, 도구는 Spring `/internal/**`만 부른다
   (DB 직접 접근 금지, 규칙은 Spring이 다시 검증). Spring 쪽은 `Controllers.Internal` + 서비스 메서드. 호출은 `harness.tools.call("business", "<tool>", args)`.
   데이터를 바꾸는 도구 중 사람이 확인해야 하는 것은 `harness/guardrails.py`의 `APPROVAL_REQUIRED`에 넣는다(승인 전 호출은 `ApprovalRequired`).
   평가 데이터가 실린 인자는 `harness/tools.py`의 `REDACTED_ARGS`로 TOOL_START 이벤트에서 가린다.
   읽기 전용 계산 도구는 business-mcp가 아니라 그 일을 맡은 서버에 둔다(예: analytics-mcp `@mcp.tool(annotations={"readOnlyHint": True, …})`).
   새 MCP 서버는 `harness/tools.py`의 `URLS`(`*_MCP_URL`), `docker-compose.yml`의 서비스(같은 agent 이미지, 공개 포트 없음)와 agent `depends_on`,
   테스트용 `use_transport` + `tests/conftest.py`의 `tools.use_in_process(...)`를 함께 더한다.
6. **프롬프트** — `agent/app/prompts/<name>.md` (첫 줄 `<!-- version: N -->`, `$name` 치환). 코드에서는 `instructions.render("<name>", **values)`만 쓴다.
   버전은 trace의 `prompt_versions`에 기록된다.
7. **테스트** — Spring: `BackendFlowTest`(H2, `DISPATCH=none`, `TaskService.onEvents`로 Agent 이벤트를 흉내). Agent: `tests/fake_backend.py`가
   Spring 내부 API를 흉내 내고 `tools.use_in_process`로 MCP 서버를 프로세스 안에서 돌린다(`tests/test_runner.py` 참고).

## 3. 루프 닫기 — 어떤 작업도 "아무도 모르게 멈춘 채" 남지 않게

| 끝나는 방식 | 무엇이 닫나 | 결과 |
|---|---|---|
| Agent가 DONE/FAILED를 보냄 | `TaskService.onEvents` → `TaskFinishedEvent` → `TaskHandlers.onTaskFinished` → `TaskHandler.onFinished` | 업무 상태 반영 (예: `ReportHandler` → `report_status`) |
| Agent가 아무것도 안 보냄 (다운·메시지 유실) | `TaskWatchdog` (`@Scheduled`, `dayzero.task-stale-minutes` 기본 10분, `TASK_STALE_MINUTES`) | QUEUED/RUNNING이 그 시간 동안 진행이 없으면 `TaskService.expire` → 일반 FAILED 경로(이벤트 저장, SSE, 훅) |
| 사람이 결정해야 함 | `WAITING_APPROVAL`은 시간 제한 없음. `TaskHandler.inboxItem`이 체크리스트 카드를 만든다 | `/admin/inbox` → 승인/반려 → `TaskService.approve` → 같은 thread로 RESUME |
| 실패를 사람이 처리해야 함 | `InboxContributor` 빈 (`ReviewErrorInbox`, `ReportFailedInbox`) | REVIEW_ERROR 계정, REPORT_FAILED 세션이 체크리스트에 올라옴 (`actions` 라벨 포함) |
| 지원자 첫 메시지 실패 | `StartHandler` + `SessionService.startStatus/restart` | `start_status: failed`이고 메시지 0개면 `POST /api/sessions/{id}/restart` |

`dayzero.task-stale-minutes`는 Agent의 작업 제한 시간(`agent/app/harness/loop.py` `Limits.task_timeout_s`, 기본 120초)보다 길어야 합니다.
그보다 짧으면 Agent가 아직 일하는 중인 작업을 watchdog이 먼저 FAILED로 닫고, 뒤늦은 DONE은 아래 규칙대로 버려집니다.

이미 끝난 작업에 늦게 온 이벤트는 버립니다(`onEvents`). 그래서 watchdog이 닫은 작업을 늦은 Agent 이벤트가 다시 열지 못합니다.
새 작업 종류는 `onFinished`에서 자기 업무 상태를 정리하고, 사람이 손대야 하는 실패면 `InboxContributor`를 하나 더 두면 됩니다.

## 4. 관리자 차트·수치 추가 — analytics-mcp

관리자 화면과 리포트의 수치·차트는 한 경로로만 만들어집니다: Spring 상태 → `analytics.build(state)`(번들) → `charts.render(bundle, id)`(SVG)
→ analytics-mcp 도구 → Agent 작업이 `business.save_analytics`로 저장 → Spring 스냅숏 → 화면. 화면은 세지 않고, Agent를 동기 호출하지 않습니다.
예: 단계별 지원자 발화 길이 막대 `turn_length`.

1. **수치** — `agent/app/analytics.py`의 `build(state)`에 키를 더한다(예: `bundle["turn_length"] = [...]`). 순수 함수로 유지한다: 상태만 읽고,
   같은 상태면 같은 값, 빠진 필드(새 세션, 과거 세션)에도 예외 없이 빈 값. 번들 version 1에 키를 **더하는** 것은 호환된다.
   키 이름을 바꾸거나 빼면 `VERSION`을 올리고 business-mcp `save_analytics`의 version 검사와 화면을 함께 바꾼다.
   그 수치가 Spring의 새 종류 변경에 따라 바뀐다면, 그 변경에서 `ChatSessionRepository.bumpRev`를 불러야 스냅숏이 stale로 보인다.
2. **차트** — `agent/app/charts.py`
   - `SPECS`에 `{id, type, title, description, fields}`를 한 줄 더한다 → `describe_charts`가 그대로 내보내고, `index(bundle)`이 번들 `charts[]`에 넣는다.
   - `_status(b, id)`에 그릴 수 있는지와 캡션 한 줄(없으면 이유)을 더한다. 데이터가 없으면 `placeholder`가 대신 그려진다.
   - `_turn_length(b, title, caption)`을 쓰고 `_RENDER`에 등록한다. `_svg`·`_el`·`_text`·`_title` 도우미만 쓴다: 가로 ≤ 720, 흰 배경, 세션 텍스트는 `_esc`,
     `<script>`·`<foreignObject>`·href·이벤트 속성 금지, 색만으로 뜻을 전하지 않기(범례·숫자·`<title>`), 신호 색은 `frontend/src/constants.js`와 같게.
3. **MCP** — 바꿀 것 없음. `render_chart`/`render_charts`가 `charts.CHART_IDS`로 검증하고 `session_analytics`가 새 키를 돌려준다.
   `SPECS[].fields`에는 차트와 캡션이 읽는 번들 키를 빠짐없이 적는다(`test_describe_fields_cover_what_the_charts_read`가 확인).
4. **리포트에 싣기(선택)** — `agent/app/report_graph.py`의 `REPORT_CHARTS`에 id를 더하면 `analyze`가 그려 승인 카드와 저장된 리포트에 싣는다
   (`render_charts` 한 번에 모두 그리므로 차트 수가 늘어도 같은 도구 3회 제한에 걸리지 않는다). 요약에 쓸 숫자라면 `figures`와 `llm.FIGURE_LABELS`에도 더한다.
5. **화면** — `frontend/src/modules/admin/SessionDetail.vue`에서 `an.<키>`(= `d.analytics`)로만 그린다. 캡션은 `cap('<id>')`.
   SVG를 보여 줄 때는 `ChartGallery.vue` / `utils/charts.js`의 `svgSrc`로 `<img>`에만 넣고 `v-html`에 넣지 않는다. 스냅숏이 없을 때(`missing`)의 빈 상태도 둔다.
6. **테스트·계약** — `tests/test_analytics.py`의 차트 테스트는 `charts.CHART_IDS`를 돌므로 새 차트도 XML 파싱·안전 요소·이스케이프·결정성 검사를 받는다
   (`test_describe_specs`의 목록은 직접 고친다). 새 키의 모양은 [api-contract.md §5](api-contract.md#5-analytics--visualization-through-mcp-v4)에 적는다.

## 5. 같이 보는 과제(artifacts) 추가

`agent/app/artifacts.py`의 `catalog(scn, scenario_id)`가 시나리오별 과제 3개(설계·결과·코드)와 심어 둔 `checkpoints`를 만듭니다.
START에서 `without_checkpoints(...)`만 `init_session(artifacts=…)`으로 Spring에 보내고, `problems()`가 체크포인트가 실제 줄을 가리키는지 스스로 검사합니다.
새 시나리오는 builder 함수 하나를 추가하고 `_build`에 연결합니다. `tests/test_artifacts.py`가 29개 시나리오 전체를 검사합니다.
