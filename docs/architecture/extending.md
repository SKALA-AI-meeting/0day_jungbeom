# 확장 가이드 — 화면·작업 종류·도구를 더하는 법

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
2. **작업을 만드는 입구** — 브라우저가 만들면 `Controllers.Tasks.create`의 `switch`에 case를 추가하고 업무 규칙(권한·상태)을
   `SessionService` 같은 서비스에 둔다. 시스템이 만들면 서비스에서 `tasks.create(type, sessionId, companyId, createdBy, payload)`.
3. **Agent `Handler`** — `agent/app/runner.py`의 `HANDLERS`에 한 줄.
   ```python
   Handler("RESUMMARY", _resummary_run, _resummary_resume, description="세션 요약 다시 만들기, 관리자 승인 뒤 저장")
   ```
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

## 4. 같이 보는 과제(artifacts) 추가

`agent/app/artifacts.py`의 `catalog(scn, scenario_id)`가 시나리오별 과제 3개(설계·결과·코드)와 심어 둔 `checkpoints`를 만듭니다.
START에서 `without_checkpoints(...)`만 `init_session(artifacts=…)`으로 Spring에 보내고, `problems()`가 체크포인트가 실제 줄을 가리키는지 스스로 검사합니다.
새 시나리오는 builder 함수 하나를 추가하고 `_build`에 연결합니다. `tests/test_artifacts.py`가 29개 시나리오 전체를 검사합니다.
