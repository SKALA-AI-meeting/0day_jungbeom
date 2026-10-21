# API contract — v3 (items 3–6)

Shared by Spring (`backend/`), the agent (`agent/`), business-mcp and the frontend. Internal JSON is `snake_case`,
browser-facing JSON for new resources is `camelCase` (existing session views keep their current keys).
Anything not listed here keeps its current shape.

## 1. Shared work items (artifacts) and markups (annotations)

### Artifact
| field | type | notes |
|---|---|---|
| `id` | string ≤16 | `a1`, `a2`, … unique per session |
| `kind` | `design` \| `result` \| `code` | 설계·기획 문서 / 결과(표·지표) / 코드 |
| `title` | string ≤80 | |
| `owner` | `lead` \| `peer` \| `team` | persona that owns it |
| `status` | string ≤20 | e.g. `검토 중`, `초안`, `확정 전` |
| `summary` | string ≤160 | one line |
| `lang` | string \| null | code only (`kotlin`, `python`, `sql`, `typescript`, …) |
| `body` | string ≤6000 | design/result: Markdown (may contain LaTeX `$…$`, `$$…$$`, tables); code: plain source, no fences |

Lines are `body.split("\n")`, 1-based. The agent generates artifacts (`app/artifacts.py: catalog`) and seeds them at START.

**Planted checkpoints (agent-only).** Each catalog artifact also carries `checkpoints: [{line, issue}]` — 1–2 deliberate
problems (a bug, a questionable number, an ambiguous scope line) that a careful teammate would mark. They are **not** sent
to Spring or the browser. Spring passes `artifacts` and `annotations` in the state it sends to `/agent/views/{candidate|admin}`;
the agent's **admin** view adds `artifact_checks: [{artifact_id, line, issue, spotted: bool, annotation_ids: [int]}]`
(spotted = an annotation's line range covers the checkpoint line, ±1). The candidate view never contains checkpoints.

### Annotation
Internal: `{id: int, artifact_id, anchor: {line_start: int|null, line_end: int|null, quote: str|null}, kind: question|risk|suggest|ok, text, msg_idx: int, created_at: float epoch s}`
Public: `{id, artifactId, anchor: {lineStart, lineEnd, quote}, kind, text, msgIdx, createdAt: ISO-8601}`

`msg_idx` = number of messages in the session when the annotation was created (the idx the next message gets).

### Storage (Spring, Flyway)
- `V3__artifacts.sql`: `session_artifacts(session_id FK sessions, artifact_id, ord, kind, title, owner, status, summary, lang, body TEXT, PK(session_id, artifact_id))`,
  `annotations(id identity PK, session_id FK sessions, artifact_id, line_start INT NULL, line_end INT NULL, quote VARCHAR(300) NULL, kind VARCHAR(10), text VARCHAR(500), msg_idx INT, created_at TIMESTAMPTZ)`
- `V4__dialogue.sql`: `ALTER TABLE sessions ADD COLUMN dialogue_json TEXT`

### Browser API (candidate, Bearer CANDIDATE token, own session only)
| method | path | body | result |
|---|---|---|---|
| GET | `/api/sessions/{id}` | – | existing view **+ `artifacts: [PublicArtifact]`** (each with `annotations: [PublicAnnotation]`) **+ `start_status: running\|failed\|done`**. Never includes `dialogue`. |
| POST | `/api/sessions/{id}/annotations` | `{artifactId, anchor: {lineStart?, lineEnd?, quote?}, kind, text}` | 201 PublicAnnotation |
| DELETE | `/api/sessions/{id}/annotations/{annotationId}` | – | 204 |
| POST | `/api/sessions/{id}/restart` | – | 202 `{taskId}` — only when the session has 0 messages and its latest START task is FAILED; else 409 |

Annotation validation: session `active` (else 409); artifact exists (404); `kind` ∈ {question, risk, suggest, ok} (400);
`text` trimmed 1..500 (400); anchor must have lines (`1 ≤ lineStart ≤ lineEnd ≤ line count`) and/or a non-empty `quote`
(≤300, substring of the body) (400); at most 40 annotations per session (409).

### Browser API (admin)
- `GET /api/admin/sessions/{id}`: existing **+ `artifacts`** (public shape, with annotations) **+ `dialogue`** (object or null).
- `GET /api/admin/inbox`: every item gains `actions: {approve: label, reject: label}`.
  New kind **`REPORT_FAILED`** (session whose `report_status` is `failed`):
  `{id: "report:{sessionId}", kind, sessionId, title: "리포트를 만들지 못했어요", subject: {label: alias, detail: scenarioId, sessionId}, reason: <last REPORT error>, recommendation: "retry", flags: [], createdAt, actions: {approve: "다시 만들기", reject: "넘기기"}}`
  - approve → `POST /api/ai/tasks {type: "REPORT", sessionId}` (existing, 202 `{taskId}`)
  - reject → `POST /api/admin/sessions/{id}/report/dismiss` → 200 `{report_status: "dismissed"}`; the item leaves the inbox.
- Default labels: ACCOUNT_REVIEW 승인/반려, REPORT 공개 승인/반려, ACCOUNT_REVIEW_ERROR 직접 승인/직접 반려.

### Internal API (agent via business-mcp; `/internal/**`, internal port + X-Internal-Key)
| method | path | change |
|---|---|---|
| POST | `/internal/sessions/{id}/init` | optional `artifacts: [Artifact]` (replace-all, idempotent) |
| GET | `/internal/sessions/{id}/state` | adds `artifacts` (full), `annotations` (all, id asc), `dialogue` (object or null) |
| GET | `/internal/sessions/{id}/artifacts` | `[{id, kind, title, owner, status, summary, lang, line_count, annotation_count}]` |
| GET | `/internal/sessions/{id}/artifacts/{artifactId}` | full Artifact + `annotations` (404 if unknown) |
| GET | `/internal/sessions/{id}/annotations?since_idx=N` | annotations with `msg_idx >= N` (default 0) |
| POST | `/internal/sessions/{id}/turn` | optional `dialogue` object → replaces `sessions.dialogue_json` |

### business-mcp tools (`agent/mcp_servers/business/server.py`)
- `init_session(session_id, condition, message, artifacts: list[dict] | None = None)`
- `append_turn(..., dialogue: dict | None = None)`
- `list_artifacts(session_id) -> list[dict]`, `get_artifact(session_id, artifact_id) -> dict`, `list_annotations(session_id, since_idx: int = 0) -> list[dict]` (read-only, no approval)

### Agent module `app/artifacts.py` (signatures are fixed)
`catalog(scn, scenario_id) -> list[Artifact]`, `context_block(session, *, new_ids=None) -> str`, `render_for_model(artifact) -> str`, `ARTIFACT_TOOL` (LLM tool `open_shared_artifact(artifact_id)`).
Personas execute the tool with `tools.call_for_model("business", "get_artifact", {"session_id", "artifact_id"})` and show `render_for_model(...)` to the model.

## 2. Dialogue ledger (item 6)

`session["dialogue"]` comes from `/internal/sessions/{id}/state`; the turn graph returns `dialogue` in its final state;
`runner._turn` passes it to `append_turn(dialogue=…)`; Spring stores it opaque. Version 1 shape (extra keys allowed):

```json
{
  "version": 1,
  "summary": "older turns, compacted",
  "issues": [{"id": "i1", "title": "…", "status": "open|agreed|parked", "raised_by": "user|lead|peer", "last_idx": 5}],
  "commitments": [{"who": "user|lead|peer", "what": "…", "due": "오늘 3시", "idx": 7}],
  "positions": {"lead": {"claim": "…", "conceded": null}, "peer": {"claim": "…", "conceded": "…"}, "user": {"claim": "…"}},
  "turns": {"lead": {"last_idx": 9, "count": 4}, "peer": {"last_idx": 8, "count": 3}},
  "markups_seen": ["12", "13"],
  "cited": ["개인정보·보안 검토 규정 §3"]
}
```
Admin detail shows `summary`, `issues`, `commitments`, `positions` read-only. The candidate never sees it.
Feature flag: `DIALOGUE_HARNESS` (default `1`); `0` reproduces the previous behaviour for before/after evaluation.

## 3. Task lifecycle (item 5)

Spring `dev.dayzero.backend.task`:
```java
public interface TaskHandler {
  String type();                                   // START, TURN, REPORT, ACCOUNT_REVIEW, …
  default boolean candidateVisible() { return false; }
  default boolean resumable() { return false; }
  default void onApprovalRequired(AiTask t, Map<String, Object> ask) {}
  default void onFinished(AiTask t, String status, Map<String, Object> data) {}   // DONE | FAILED | REJECTED
  default Optional<Map<String, Object>> inboxItem(AiTask t) { return Optional.empty(); }
}
```
A `TaskHandlers` registry (by type) replaces hard-coded type checks in TaskService/InboxService; unknown types are rejected.
Non-task inbox items (REVIEW_ERROR accounts, REPORT_FAILED sessions) come from `InboxContributor` beans.
`TaskWatchdog` (`@Scheduled`, `dayzero.task-stale-minutes`, default 10): QUEUED/RUNNING tasks without progress → FAILED
(an event is appended so SSE subscribers see it) → `TaskFinishedEvent` → handler hooks close the loop.
WAITING_APPROVAL never times out (a person decides; it is on the checklist).

Agent `app/handlers.py`: `Handler(type, run, resume, description)` registry; `runner.HANDLERS` is built from it;
`GET /agent/handlers` (internal key) → `[{type, resumable, description}]`.

## 4. Rendering (item 3)

Persona lines and artifact bodies may contain Markdown and LaTeX. Text is stored raw; the frontend renders with
markdown-it (raw HTML off) + KaTeX (`throwOnError: false`) + DOMPurify. Agent-side text cleanup must keep line breaks.
