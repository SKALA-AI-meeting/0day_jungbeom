# API contract — v4 (items 3–6, analytics through MCP)

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
to Spring or the browser. `GET /internal/sessions/{id}/state` carries `artifacts` and `annotations`; since v4 the analytics
bundle (§5, `analytics.build`) adds `artifact_checks: [{artifact_id, line, issue, spotted: bool, annotation_ids: [int]}]`
(spotted = an annotation's line range covers the checkpoint line, ±1), which the admin detail shows from Spring's snapshot.
The candidate view (`/agent/views/candidate`) never contains checkpoints.

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
  From v4 the agent-computed parts (scenario, painpoints, dilemma, condition details, detector, artifact_checks) are in `analytics` (§5).
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

## 5. Analytics & visualization through MCP (v4)

Before v4 the admin screens were built by a synchronous side channel (Spring → `POST /agent/views/admin|admin-rows`)
plus counting in the browser, and no MCP tool or agent workflow touched the visualizations. From v4 the numbers and charts are
produced by an MCP server, persisted by Spring as a snapshot, refreshed by agent tasks, and the admin screens never call the agent synchronously.
(The candidate view keeps `POST /agent/views/candidate` for now.)

### Analytics bundle (version 1) — computed by `agent/app/analytics.py: build(state)`
```json
{
  "version": 1, "session_id": "…", "computed_at": 1730000000.0,
  "source": {"state_rev": 42, "message_count": 17, "observation_count": 9, "detection_count": 7, "annotation_count": 2, "status": "active", "milestone_idx": 2},
  "row": {"category": "기획·PM · 핀테크", "scenario_title": "…", "axis": "원칙 ↔ 파격" , "choice": "통합안", "condition": "회피형 팀장 · 협력형 동료"},
  "context": {"scenario": {"…full catalog scenario as admin_view returned…"}, "painpoints": null,
              "artifacts": [{"id": "a1", "kind": "design", "title": "…", "owner": "lead"}]},
  "timeline": [{"key": "communicate", "label": "소통", "reached": true, "entered_idx": 0, "offset_s": 0, "offset_label": "+00:00", "messages": 5, "observations": 3,
                "obs": [{"id": "o3_0", "msg_idx": 3, "competency": "C01", "signal": "positive", "behavior": "…"}]}],
  "heatmap": {"competencies": [{"id": "C01", "name": "…"}], "milestones": [{"key": "communicate", "label": "소통"}],
              "cells": [{"cid": "C01", "mkey": "communicate", "n": 2, "positive": 1, "neutral": 1, "risk": 0}],
              "totals": {"C01": 4, "C02": 1, "C03": 0, "C05": 2}, "max_n": 3},
  "detector": {"…exactly detector.summarize(state)…"},
  "dilemma": {"…choice_detail…"}, "condition": {"…condition_detail…"},
  "artifact_checks": [{"artifact_id": "a3", "line": 5, "issue": "…", "spotted": true, "annotation_ids": [51]}],
  "figures": {"messages": 17, "candidate_messages": 8, "observations": 9, "by_signal": {"positive": 5, "neutral": 3, "risk": 1},
              "pooled_kappa": 0.31, "kappa_n": 32, "tki_estimate": "compromising", "checkpoints": "2/5", "milestones_reached": "3/4"},
  "charts": [{"id": "timeline", "type": "timeline", "title": "마일스톤 타임라인", "caption": "…", "available": true}]
}
```
`charts[].id` ∈ `timeline | heatmap | tki | agreement | checkpoints`. `figures` is the compact form used in prompts and the inbox.
Values must equal what the previous code produced for the same state (views.admin_view / detector.summarize / the browser's heatmap and timeline counting).
Ported 1:1 from the browser: `timeline[].reached` = `i <= milestone_idx`; `offset_s` rounds like JS `Math.round` and is never negative;
`heatmap.cells` holds all 16 (competency, milestone) pairs, zeros included; `heatmap.totals[cid]` = the report's count for that competency
when the session has a report, else the evidence count (the old total column).
- `figures.checkpoints` is `null` when the session has no planted checkpoints (no artifacts, legacy session); `pooled_kappa`, `kappa_n`
  (= `detector.agreement.n_judgements`, the message × competency judgements κ compares) and `tki_estimate` are `null` unless
  `detector.status == "ready"`; `milestones_reached` counts `reached` milestones (a new session reads `1/4`).
- `build` never raises on a partial state: an unknown scenario gives `null` row values / scenario / dilemma and `[]` checks; a malformed
  detection gives `detector: {"status": "unavailable", "messages": n}`. `detector.sources` keys are sorted (byte-stable JSON).
- Regression on the real d20 database (17 existing sessions + 2 e2e sessions): every stored bundle equals the 2a40dc7 `views.admin_view` / `admin_row` and the 2a40dc7
  browser counting on the same internal state, field by field (detector, dilemma, condition, artifact_checks, category, row, heatmap, timeline).

### analytics-mcp (`agent/mcp_servers/analytics/server.py`, `python -m mcp_servers.analytics.server`, :9104 on the compose network only, `ANALYTICS_MCP_URL`)
All tools are read-only (`readOnlyHint`, `idempotentHint`). The server reads `GET /internal/sessions/{id}/state` (BACKEND_INTERNAL_URL + X-Internal-Key)
and exposes `use_transport(t)` for tests, like business-mcp. It stores nothing.
- `session_analytics(session_id) -> bundle`
- `render_chart(session_id, chart_id) -> {chart_id, title, mime: "image/svg+xml", svg, available, caption, state_rev}` — deterministic, self-contained SVG
  (`app/charts.py`: no `<script>`, no `<foreignObject>`, no href, no event attributes, session text XML-escaped), width ≤ 720, Korean labels,
  white background, colours readable on white (print-like report). A chart without data returns a small placeholder card with the reason and `available: false`.
  The heatmap is shaded like the admin screen (`0.15 + n / max_n × 0.7` of the brand colour). `state_rev` = the state it was drawn from.
- `render_charts(session_id, chart_ids) -> {state_rev, charts: [{chart_id, title, mime, svg, available, caption}]}` — 1–5 ids, drawn from one
  state read, in the asked order, each once (the report's one call).
- `describe_charts() -> [{id, type, title, description, fields}]` (`fields` = every bundle key the chart reads, its availability caption included;
  `test_describe_fields_cover_what_the_charts_read` removes each unlisted key and checks the SVG does not change)

Errors: unknown session → `ToolError("404 …")` (Spring's message), unknown chart or malformed session id → `ToolError("400 …")`,
Spring unreachable → `"503 …"`, unreadable state → `"502 …"`.

### business-mcp
- `save_analytics(session_id, analytics) -> {stored: bool}` → `PUT /internal/sessions/{id}/analytics` (derived data, no approval).
  `400` before calling Spring when the bundle is not version 1, has no `source`, its `source.state_rev` is not a non-negative integer, its `session_id`
  is not this session, or `row`/`heatmap`/`figures` are not objects or `timeline`/`charts` not non-empty lists (Spring checks the same).

### Spring
- `V5__analytics.sql`: `sessions.analytics_json TEXT`, `sessions.analytics_at TIMESTAMPTZ`, `sessions.state_rev BIGINT NOT NULL DEFAULT 0`.
  `ChatSession` maps them read-only: `state_rev` moves only through `ChatSessionRepository.bumpRev` (an atomic `UPDATE … + 1`), the snapshot only through `storeAnalytics`.
- `state_rev` is bumped on every change that affects analytics: init, the candidate's message (and choice), the agent's turn, detection,
  annotation add/delete, report save, completion (finish or a turn with `completed`). Notes, report dismiss and analytics PUTs do not bump it.
  `GET /internal/sessions/{id}/state` includes `state_rev` (read with the session row first, so a concurrent change can only make a snapshot look older).
- `PUT /internal/sessions/{id}/analytics` (body = bundle), under a row lock: stored only if `source.state_rev >= stored source.state_rev` → 200 `{stored: true|false}`.
  `400` when `source.state_rev` is missing, not a JSON integer (`8.0`, `"8"`) or negative, when `version` is not 1, when `session_id` is missing or names another session,
  when `row`/`heatmap`/`figures` are not objects or `timeline`/`charts` are not non-empty lists (a rev alone never makes a session look fresh),
  or when the rev is ahead of the session's `state_rev`; `404` unknown session.
- `analytics_status` = `missing` (no snapshot) | `stale` (snapshot rev < current rev) | `fresh`.
- `GET /api/admin/sessions/{id}`: **no agent call.** The flat Spring state as before (`id, alias, company, scenario_id, status, milestone_idx, turns_in_milestone,
  condition` (raw assignment `{stratum, lead, peer, method, seed}`), `choice, milestone_log, notes, report_status, created_at, ended_at, state_rev, messages, observations, detections, report,
  annotations` (internal shape), `dialogue`) + public `artifacts`, `tasks`, `pending_approval` + `analytics` (stored bundle or null) + `analytics_status`
  + `analytics_task` (`{id, status}` of a QUEUED/RUNNING ANALYTICS task, or null). Scenario, painpoints, dilemma, condition details, detector,
  artifact_checks and category exist only inside `analytics`.
- `GET /api/admin/sessions`: **no agent call.** Same row keys as before (`id, alias, category, scenario_id, axis, choice, condition, status, milestone_idx, messages, observations, report_status, created_at`)
  filled from `analytics.row` when present (category falls back to `scenario_id`; axis, choice and condition stay null until a snapshot exists), plus `analytics_status`. Counts and status are Spring's, live.
- Task type `ANALYTICS` (`AnalyticsHandler`: not candidate-visible, not resumable, threadId `analytics:{sid}:{id}`; an `APPROVAL_REQUIRED` from the agent becomes FAILED;
  not `listedInHistory`: `GET /api/ai/tasks?mine=true` leaves it out for the admin too, `GET /api/ai/tasks/{id}` and the session detail's `tasks` still show it).
  `POST /api/ai/tasks {type: "ANALYTICS", sessionId}` → `AnalyticsService.request`: admin only (candidate → 403), same company (else 403), unknown session 404;
  under the session's row lock, a QUEUED/RUNNING ANALYTICS task is handed out again: 202 `{taskId, reused: true}`, else a new one: 202 `{taskId, reused: false}`.
- `POST /api/admin/analytics/refresh {sessionIds: [≤20]}` → for each of the company's listed sessions whose status is not `fresh`: create or reuse an ANALYTICS task
  → 202 `[{sessionId, taskId}]` in input order. Fresh, other companies' and unknown ids are skipped; more than 20 ids or no list → 400; candidate → 403.
- The REPORT inbox item passes through the approval payload's `figures` (null for a pre-v4 draft) and `charts` (`[]` if absent); `pending_approval.draft` carries them too.
  `GET /api/admin/inbox/count` → `{count}` (same number as the list, no cards): the top-bar badge polls this instead of the list with its chart SVGs.
- `GET /internal/conditions` reads only `condition_json` (a projection), never whole session rows with their snapshots.
- The candidate view never contains `analytics`, `figures` or charts (Spring also leaves `report` out of the state it sends to `/agent/views/candidate`).

### Agent
- `ANALYTICS` handler (not resumable): `analytics.session_analytics` (MCP) → `business.save_analytics` → DONE `{stored, figures}`; both TOOL_START/TOOL_END
  are emitted (the admin's loading checklist follows them). No sessionId → FAILED without retry; unknown session → 404, not retried.
- After a successful START and TURN (also when a retry finds it already applied) the runner refreshes the snapshot in the background, quietly
  (no TOOL events on the candidate's stream; failure only logged). After a TURN the detection runs first and then one refresh, so the stored snapshot already includes that message's judgement.
- Report graph: `load → backfill → analyze → summarize → approval → save`. `analyze` calls `analytics.session_analytics` and once `analytics.render_charts`
  (timeline, heatmap, tki, checkpoints; a chart the bundle marks `available: false` is skipped). The two calls read the state separately: when
  `render_charts.state_rev` differs from the bundle's `source.state_rev` (a late detection landed in between) the pair is read once more.
  analytics-mcp failing (`ToolFailure`) does not fail the REPORT: the draft goes on with `figures: null`, `charts: []`, `analytics_rev: null`
  (trace note `analytics_unavailable`, counted as a fallback); the report needs only the LLM and business-mcp;
  `summarize` gets `figures` as context (`prompts/summarize*.md` v2, `llm.figures_block`: numbers may only be quoted verbatim, never recomputed; the
  model is not required to cite them, and the gpt-4o-mini reports observed so far mostly do not); the approval payload adds `figures` and `charts: [{chart_id, title, svg}]`;
  `save` stores the report with `figures`, `charts` and `analytics_rev` (the bundle's `source.state_rev`), then, because saving the report bumps `state_rev`, recomputes the bundle
  and calls `business.save_analytics` (falls back to the `analyze` bundle; a rejected draft stores the `analyze` bundle). A snapshot failure is logged and never fails the report.
- `harness/tools.py`: `URLS["analytics"]` (`ANALYTICS_MCP_URL`); `analytics.*` is held to the same-tool cap like every non-business tool (a REPORT run makes
  1–2 `session_analytics` + 1–2 `render_charts`, its resume 1 `session_analytics`) and `analytics` is in `REDACTED_ARGS` (the bundle shows only as a size in TOOL_START).
- `/agent/views/admin` and `/agent/views/admin-rows` are removed (404); `views.py` keeps only `candidate_view`.

### Frontend
- Admin detail renders from `analytics` (no local counting; the heatmap colour is `n / max_n`, the checkpoint chip is `figures.checkpoints`). `missing`/`stale` with no running task → start an ANALYTICS task once per page load,
  follow it over SSE (checklist from TOOL_START/TOOL_END), reload on DONE/FAILED; a running `analytics_task` is followed instead. Stale data stays visible with a
  "최신 대화 반영 중…" note while a task is followed (plus "에이전트가 아직 작업을 받지 않았어요" after 15 s without an event: a QUEUED task while the agent is down),
  otherwise "최근 대화가 아직 반영되지 않았어요" with a "다시 계산" button.
  The dashboard, the detail and the inbox never wait for `/api/meta` (it goes through the agent); competency names come from `analytics.heatmap.competencies`,
  persona names from `analytics.context.scenario`, before the first snapshot from `/api/meta` when it answers, else the roles (팀장 / 동료, never "팀 공동").
- The live admin detail draws its timeline, heatmap, TKI plane and κ table in Vue from the bundle (interactive: filters, jumps to messages);
  `render_chart(s)` SVGs are the print form used by the report, the approval card and the inbox. Both read the same bundle and shade the heatmap
  alike. `agreement` is not in the report: it is an on-demand chart (MCP call), shown on screen as the κ table. A report without figures and charts
  (pre-v4, or drafted while analytics-mcp was down) says so and points to "리포트 다시 생성".
- Report and inbox show `charts` as `<img src="data:image/svg+xml;charset=utf-8,…">` (`utils/charts.js`, `ChartGallery.vue`; never inserted as HTML), figures as `FigureChips.vue`.
  The dashboard asks `/api/admin/analytics/refresh` for non-fresh rows (newest 20) at most once per change of that set; a row shows "분석 갱신 중" for
  90 s after its refresh was asked for, then "분석 최신 아님" (a failed or queued task does not pulse forever). Its task history omits ANALYTICS.
- `FigureChips` shows κ with its sample size (`κ 0.31 · 32건`); below 20 judgements the Landis–Koch word is replaced by "표본 적음".
- The chart overlay is modal: Escape and Tab are handled on the document while it is open, focus that leaves the dialog returns to its close
  button; on a phone the chart keeps 600 px and the sheet scrolls sideways.
