// 지원자 화면 mock 서버. 메모리 안의 세션이 계약(docs/common/contracts.md)대로 상태를 바꾸고,
// WS는 MockSocket이 프레임을 흘린다. 끊긴 동안의 변화도 서버 상태에 남아 재연결 뒤 /state로 복원된다.
//
// 링크 토큰(/s/<토큰>):
//   demo      처음부터(동의 → 대기 → 오피스 0분, 보드 담당 없음)
//   live      진행 중 47.5분에 재입장(state.json)
//   reporting 보고 대기 중 재입장(state_reporting.json)
//   done      완료(디브리핑 다시 보기)   failed  세션 중단 안내
//   expired·cancelled  410 안내          그 밖   404
// 장면 진행·연결 끊기·시간 이동은 오피스 왼쪽 아래 "mock 조작" 패널(mockControls)로 한다.
import type {
  Assignee,
  AssistantCall,
  Channel,
  CompanyDoc,
  DocRef,
  Entry,
  FinalSection,
  Gap,
  Message,
  MyDocument,
  ReceivedDocument,
  SendFrame,
  ServerFrame,
  SessionStatus,
  StateSnapshot,
  Task,
} from "@/components/office/types";

import entryFixture from "./fixtures/candidate_entry.json";
import debriefFixture from "./fixtures/debrief.json";
import debriefFailed from "./fixtures/debrief_failed.json";
import documentsFixture from "./fixtures/documents.json";
import internalDocs from "./fixtures/internal_docs.json";
import script from "./fixtures/office_script.json";
import assistantFixture from "./fixtures/assistant_response.json";
import stateFixture from "./fixtures/state.json";
import reportingFixture from "./fixtures/state_reporting.json";
import wsEvents from "./fixtures/ws_events.json";
import type { MockRoute } from "./types";
import { LONG_ALIAS, LONG_DOC, LONG_MESSAGE, WORST } from "./worst";

export const SESSION_MINUTES = 120;
const MINUTE = 60_000;
const REPORT_MINUTES = 5;
const PART_TITLES: Record<number, string> = {
  1: "문제 정의와 대상 사용자",
  2: "사용자 인터뷰에서 찾은 근거",
  3: "핵심 기능 제안",
  4: "비슷한 서비스 사례",
  5: "성공 지표와 출시 일정",
};
const DEFAULT_DIVISION: Record<string, Assignee> = {
  "1": "candidate",
  "2": "candidate",
  "3": "both",
  "4": "colleague",
  "5": "colleague",
};
export const DIVISION_RULE =
  "2번은 나, 3번은 도현 또는 같이, 4·5번 중 하나 이상은 도현 단독이어야 분업이 정해집니다.";

export class MockApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message?: string,
  ) {
    super(message ?? code);
  }
}

type Scene = (typeof script.scenes)[number];

type MockSession = {
  token: string;
  id: string;
  alias: string;
  status: SessionStatus;
  failedStage?: "session" | "report";
  startedAt: number | null;
  submittedAt: number | null;
  deadlineAt: number | null;
  autoSubmitted: boolean;
  reportRequested: boolean;
  reported: boolean;
  division: StateSnapshot["division"];
  messages: Message[];
  myDocs: MyDocument[];
  received: ReceivedDocument[];
  /** 동료 문서 doc_id → version → 본문 */
  colleagueText: Record<string, Record<number, string>>;
  final: FinalSection[];
  tasks: Task[];
  documents: CompanyDoc[];
  assistant: AssistantCall[];
  activeRuns: StateSnapshot["active_runs"];
  gaps: Gap[];
  opens: { doc_id: string; version: number; t_min: number }[];
  firedScenes: Set<string>;
  socket: MockSocket | null;
  dropAt: number | null;
  seq: number;
  sent: Map<string, [string, string]>;
  timers: ReturnType<typeof setTimeout>[];
  survey: boolean;
};

const MESSAGE_POOL = new Map<string, Message>();
for (const m of [
  ...(stateFixture.messages as Message[]),
  ...(reportingFixture.messages as Message[]),
  ...(wsEvents as { type: string; payload: unknown }[])
    .filter((f) => f.type === "message.new")
    .map((f) => f.payload as Message),
  ...(script.extra_messages as Message[]),
]) {
  if (!MESSAGE_POOL.has(m.id)) MESSAGE_POOL.set(m.id, m);
}

const COLLEAGUE_TEXT: Record<string, Record<number, string>> = {};
for (const doc of internalDocs.documents) {
  if (doc.owner !== "colleague") continue;
  COLLEAGUE_TEXT[doc.doc_id] = Object.fromEntries(doc.versions.map((v) => [v.version, v.content]));
}

const INITIAL: Record<string, { status: SessionStatus; failedStage?: "session" }> = {
  demo: { status: "invited" },
  live: { status: "in_progress" },
  reporting: { status: "reporting" },
  done: { status: "completed" },
  failed: { status: "failed", failedStage: "session" },
};

const sessions = new Map<string, MockSession>();

function blankSession(token: string): MockSession {
  const base = structuredClone(stateFixture) as unknown as StateSnapshot;
  return {
    token,
    id: `mock-${token}`,
    alias: "지원자A",
    status: "invited",
    startedAt: null,
    submittedAt: null,
    deadlineAt: null,
    autoSubmitted: false,
    reportRequested: false,
    reported: false,
    division: null,
    messages: [structuredClone(MESSAGE_POOL.get("m-1")!)],
    myDocs: base.my_documents.map((d) => ({
      ...d,
      content: "",
      revision: 0,
      versions: [],
    })),
    received: [],
    colleagueText: {},
    final: base.final.sections.map((s) => ({ ...s })),
    tasks: base.tasks.map((t) => ({
      ...t,
      assignee: null,
      status: "todo",
      order: t.part_no,
      due_min: null,
    })),
    documents: structuredClone(documentsFixture) as CompanyDoc[],
    assistant: [],
    activeRuns: [],
    gaps: [],
    opens: [],
    firedScenes: new Set(),
    socket: null,
    dropAt: null,
    seq: 0,
    sent: new Map(),
    timers: [],
    survey: false,
  };
}

/** 픽스처 스냅샷(state.json·state_reporting.json)에서 세션을 만든다. */
function fromFixture(token: string, fixture: unknown, tMinOf: number): MockSession {
  const snap = structuredClone(fixture) as StateSnapshot;
  const s = blankSession(token);
  // 픽스처의 절대 시각(분업 확정)을 지금 시계로 옮겨 세션 분이 픽스처와 같게 한다
  const startedAt = Date.now() - tMinOf * MINUTE;
  if (snap.division) {
    const offset = Date.parse(snap.division.decided_at) - Date.parse(snap.session.started_at!);
    snap.division.decided_at = new Date(startedAt + offset).toISOString();
  }
  Object.assign(s, {
    status: snap.session.status,
    startedAt,
    division: snap.division,
    messages: snap.messages,
    myDocs: snap.my_documents,
    received: snap.received,
    colleagueText: structuredClone(COLLEAGUE_TEXT),
    final: snap.final.sections,
    tasks: snap.tasks,
    documents: snap.documents,
    assistant: snap.assistant,
    activeRuns: [],
    gaps: snap.connection_gaps,
  });
  for (const scene of script.scenes) if (scene.at_min <= tMinOf) s.firedScenes.add(scene.id);
  return s;
}

function create(token: string): MockSession {
  const initial = INITIAL[token];
  if (token === "live") return fromFixture(token, stateFixture, 47.5);
  if (token === "reporting") {
    const s = fromFixture(token, reportingFixture, 111);
    s.submittedAt = Date.now() - MINUTE;
    s.deadlineAt = s.submittedAt + REPORT_MINUTES * MINUTE;
    s.reportRequested = true;
    scheduleDeadline(s);
    return s;
  }
  const s = blankSession(token);
  s.status = initial.status;
  s.failedStage = initial.failedStage;
  if (s.status !== "invited") s.startedAt = Date.now() - SESSION_MINUTES * MINUTE;
  return s;
}

/** ?data=worst: 긴 별칭, 공백 없는 URL이 든 긴 메시지, 긴 문서 */
function worst(s: MockSession) {
  s.alias = LONG_ALIAS;
  for (const m of s.messages) m.content = m.content.replace("지원자A", LONG_ALIAS);
  MESSAGE_POOL.get("m-1")!.content = MESSAGE_POOL.get("m-1")!.content.replace(
    "지원자A",
    LONG_ALIAS,
  );
  s.messages.push({
    ...structuredClone(MESSAGE_POOL.get("m-3")!),
    id: "m-long",
    t_min: 1.4,
    content: LONG_MESSAGE,
  });
  s.myDocs[0].content = LONG_DOC;
}

function session(token: string): MockSession {
  if (token === "expired") throw new MockApiError(410, "expired");
  if (token === "cancelled") throw new MockApiError(410, "cancelled");
  if (!INITIAL[token]) throw new MockApiError(404, "not_found");
  let found = sessions.get(token);
  if (!found) {
    found = create(token);
    if (WORST) worst(found);
    sessions.set(token, found);
  }
  return found;
}

function byId(id: string) {
  return session(id.replace(/^mock-/, ""));
}

function base64url(value: unknown) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/** 서명 없는 모양만 JWT. 화면은 sub로 session_id를 읽는다. */
function jwt(role: string, id: string) {
  return `${base64url({ alg: "none" })}.${base64url({ role, sub: id })}.mock`;
}

const iso = (ms: number | null) => (ms == null ? null : new Date(ms).toISOString());
const endsAt = (s: MockSession) =>
  s.startedAt == null ? null : s.startedAt + SESSION_MINUTES * MINUTE;

export function tMin(s: MockSession) {
  if (s.startedAt == null) return 0;
  return Math.round(((Date.now() - s.startedAt) / MINUTE) * 100) / 100;
}

function snapshot(s: MockSession): StateSnapshot {
  const ends = endsAt(s);
  return {
    session: {
      id: s.id,
      alias: s.alias,
      status: s.status,
      started_at: iso(s.startedAt),
      ends_at: iso(ends),
      remaining_seconds: ends == null ? null : Math.max(0, Math.floor((ends - Date.now()) / 1000)),
      deadline_at: iso(s.deadlineAt),
      completed_at: null,
    },
    division: s.division,
    messages: s.messages,
    my_documents: s.myDocs,
    received: s.received,
    final: { sections: s.final, template: stateFixture.final.template },
    tasks: s.tasks,
    documents: s.documents,
    assistant: s.assistant,
    active_runs: s.activeRuns,
    connection_gaps: s.gaps,
    channels: stateFixture.channels as StateSnapshot["channels"],
    persona: stateFixture.persona,
  };
}

/** 서버 상태에 반영된 뒤 붙어 있는 소켓으로 보낸다(끊겨 있으면 상태에만 남는다). */
function emit(s: MockSession, frame: ServerFrame) {
  if (frame.type === "message.new" && !s.messages.some((m) => m.id === frame.payload.id)) {
    s.messages.push(frame.payload);
  }
  if (frame.type === "agent.progress") {
    const { run_id, actor, node, status } = frame.payload;
    s.activeRuns = s.activeRuns.filter((r) => r.run_id !== run_id);
    if (status !== "finished" && status !== "failed") s.activeRuns.push({ run_id, actor, node });
  }
  s.socket?.deliver(frame);
}

function later(s: MockSession, ms: number, job: () => void) {
  s.timers.push(setTimeout(job, ms));
}

function poolMessage(s: MockSession, id: string): Message {
  const m = structuredClone(MESSAGE_POOL.get(id)!);
  return m;
}

function nextId(s: MockSession, prefix: string) {
  s.seq += 1;
  return `${prefix}${s.seq}`;
}

function message(
  s: MockSession,
  channel: Channel,
  sender: Message["sender"],
  content: string,
  extra: Partial<Message> = {},
): Message {
  return {
    id: nextId(s, "m-x"),
    channel,
    sender,
    content,
    event_id: null,
    run_id: null,
    t_min: tMin(s),
    created_at: new Date().toISOString(),
    reply_to_doc: null,
    shared_doc: null,
    ...extra,
  };
}

/** 동료(또는 팀장)가 입력 중 → 답장. agent.progress 다섯 상태 중 started·finished만 흉내 낸다. */
function personaReply(
  s: MockSession,
  actor: "colleague" | "manager",
  channel: Channel,
  content: string,
  then?: () => void,
) {
  const runId = nextId(s, "r-x");
  emit(s, {
    type: "agent.progress",
    payload: { run_id: runId, actor, node: "respond", status: "started" },
  });
  if (actor === "colleague") {
    later(s, 500, () =>
      emit(s, {
        type: "agent.progress",
        payload: {
          run_id: runId,
          actor,
          node: "respond",
          status: "tool_start",
          tool: "search_documents",
        },
      }),
    );
  }
  later(s, 1400, () => {
    emit(s, {
      type: "message.new",
      payload: message(s, channel, actor, content, { run_id: runId }),
    });
    emit(s, {
      type: "agent.progress",
      payload: { run_id: runId, actor, node: "respond", status: "finished" },
    });
    then?.();
  });
}

const replyIndex = new Map<string, number>();
function cannedReply(s: MockSession, channel: "team" | "dm" | "manager_dm") {
  const list = script.replies[channel];
  const key = `${s.id}:${channel}`;
  const i = replyIndex.get(key) ?? 0;
  replyIndex.set(key, i + 1);
  return list[i % list.length];
}

function complete(s: MockSession) {
  if (s.status !== "reporting") return;
  s.status = "completed";
  s.timers.forEach(clearTimeout);
  s.timers = [];
  emit(s, {
    type: "session.ended",
    payload: { reason: s.autoSubmitted ? "timeout" : "submitted" },
  });
}

function scheduleDeadline(s: MockSession) {
  if (s.deadlineAt == null) return;
  later(s, Math.max(0, s.deadlineAt - Date.now()), () => complete(s));
}

function onCandidateMessage(s: MockSession, payload: SendFrame["payload"]) {
  const known = s.sent.get(payload.client_msg_id);
  if (known) {
    const [message_id, run_id] = known;
    emit(s, {
      type: "message.ack",
      payload: { client_msg_id: payload.client_msg_id, message_id, run_id },
    });
    return;
  }
  const mine = message(s, payload.channel, "candidate", payload.content, {
    reply_to_doc: payload.reply_to_doc ?? null,
  });
  const runId = nextId(s, "r-c");
  s.sent.set(payload.client_msg_id, [mine.id, runId]);
  emit(s, {
    type: "message.ack",
    payload: { client_msg_id: payload.client_msg_id, message_id: mine.id, run_id: runId },
  });
  emit(s, { type: "message.new", payload: mine });

  // 보고 요청 뒤 팀 채널·팀장 DM의 메시지는 보고로 센다(contracts: kind=report)
  const isReport = s.reportRequested && payload.channel !== "dm";
  if (isReport) {
    s.reported = true;
    if (s.status === "reporting") {
      personaReply(s, "manager", payload.channel, script.replies.report, () => complete(s));
    }
    return;
  }
  if (payload.channel === "manager_dm") {
    personaReply(s, "manager", "manager_dm", cannedReply(s, "manager_dm"));
  } else if (payload.reply_to_doc) {
    personaReply(s, "colleague", payload.channel, script.replies.doc_reply);
  } else {
    personaReply(s, "colleague", payload.channel, cannedReply(s, payload.channel));
  }
}

// ── 장면(카드) ──────────────────────────────────────────────

function colleagueParts(s: MockSession) {
  return s.tasks
    .filter((t) => t.assignee === "colleague" || t.assignee === "both")
    .map((t) => t.part_no)
    .sort();
}

function sendColleagueDoc(s: MockSession, part: number, version: 1 | 2) {
  const docId = `doc-k${part}`;
  const title = PART_TITLES[part];
  const text =
    COLLEAGUE_TEXT[docId]?.[version] ??
    script.colleague_fallback.replace("{title}", title).replace("{version}", String(version));
  s.colleagueText[docId] = { ...s.colleagueText[docId], [version]: text };
  const card = message(
    s,
    "team",
    "colleague",
    script.send_texts[String(version) as "1" | "2"]
      .replace("{part}", String(part))
      .replace("{version}", String(version)),
    { shared_doc: { doc_id: docId, version } },
  );
  let doc = s.received.find((d) => d.doc_id === docId);
  if (!doc) {
    doc = { doc_id: docId, owner: "colleague", part_no: part, title, versions: [] };
    s.received.push(doc);
  }
  if (!doc.versions.some((v) => v.version === version)) {
    doc.versions.push({
      version,
      channel: "team",
      message_id: card.id,
      t_min: card.t_min,
      opened: false,
    });
  }
  emit(s, { type: "message.new", payload: card });
  emit(s, {
    type: "document.shared",
    payload: {
      doc_id: docId,
      version,
      part_no: part,
      by: "colleague",
      channel: "team",
      message_id: card.id,
    },
  });
}

function confirmDivision(s: MockSession, decidedBy: "candidate" | "colleague_default") {
  const parts = Object.fromEntries(s.tasks.map((t) => [String(t.part_no), t.assignee!]));
  s.division = { parts, decided_by: decidedBy, decided_at: new Date().toISOString() };
  emit(s, {
    type: "division.confirmed",
    payload: { parts, decided_by: decidedBy, t_min: tMin(s) },
  });
  // 동료는 자기 파트를 진행 중으로 옮긴다(task.updated by colleague)
  later(s, 800, () => {
    for (const t of s.tasks) {
      if ((t.assignee === "colleague" || t.assignee === "both") && t.status === "todo") {
        t.status = "doing";
        emit(s, { type: "task.updated", payload: { ...t, by: "colleague" } });
      }
    }
  });
  if (decidedBy === "candidate") personaReply(s, "colleague", "team", script.replies.division);
}

function fireScene(s: MockSession, scene: Scene) {
  if (s.firedScenes.has(scene.id)) return;
  s.firedScenes.add(scene.id);
  if ("default_division" in scene && scene.default_division && !s.division) {
    for (const t of s.tasks) {
      t.assignee = DEFAULT_DIVISION[String(t.part_no)];
      emit(s, { type: "task.updated", payload: { ...t, by: "colleague" } });
    }
    confirmDivision(s, "colleague_default");
  }
  if ("send_version" in scene && scene.send_version) {
    for (const part of colleagueParts(s)) sendColleagueDoc(s, part, scene.send_version as 1 | 2);
  }
  if ("release" in scene && scene.release) {
    const doc = s.documents.find((d) => d.doc_id === scene.release);
    if (doc && !doc.released) {
      doc.released = true;
      doc.release_at_min = null;
      emit(s, { type: "document.released", payload: { doc_id: doc.doc_id, title: doc.title } });
    }
  }
  for (const id of scene.messages ?? []) {
    const m = poolMessage(s, id);
    m.t_min = Math.max(scene.at_min, tMin(s));
    if (id === "m-61" || id === "m-60") s.reportRequested = true;
    if (id === "m-32" || m.channel === "notice") m.t_min = scene.at_min;
    emit(s, { type: "message.new", payload: m });
  }
  if (scene.id === "release") emit(s, { type: "message.new", payload: poolMessage(s, "m-32") });
}

function submit(s: MockSession, auto: boolean) {
  if (s.status !== "in_progress") return;
  s.submittedAt = Date.now();
  s.autoSubmitted = auto;
  // 보고 요청 전에 이미 보고했으면 제출 즉시 종료(contracts: 요청 뒤 제출 전 보고)
  if (s.reportRequested && s.reported) {
    s.status = "reporting";
    complete(s);
    return;
  }
  s.status = "reporting";
  s.deadlineAt = s.submittedAt + REPORT_MINUTES * MINUTE;
  emit(s, { type: "session.reporting", payload: { deadline_at: iso(s.deadlineAt)! } });
  if (!s.reportRequested) {
    s.firedScenes.add("honesty_report");
    s.reportRequested = true;
    // 제출이 먼저 오면(or_on_submit) 그 자리에서 보고를 요청한다. 만료 자동 제출은 "한 줄이면 됩니다"
    const request = message(
      s,
      "team",
      "manager",
      auto ? script.auto_submit_request : script.submit_request,
    );
    request.t_min = tMin(s);
    emit(s, { type: "message.new", payload: request });
    const line = poolMessage(s, "m-61");
    line.t_min = tMin(s);
    emit(s, { type: "message.new", payload: line });
  }
  scheduleDeadline(s);
}

// ── 소켓 ───────────────────────────────────────────────────

class MockSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  private closed = false;

  constructor(private readonly s: MockSession) {
    setTimeout(() => !this.closed && this.onopen?.(), 50);
  }

  deliver(frame: unknown) {
    if (!this.closed) this.onmessage?.({ data: JSON.stringify(frame) });
  }

  send(data: string) {
    const frame = JSON.parse(data) as SendFrame;
    if (frame.type !== "message.send") return;
    if (this.s.status !== "in_progress" && this.s.status !== "reporting") {
      this.deliver({
        type: "error",
        payload: { code: "session_ending", message: "session ended" },
      });
      return;
    }
    onCandidateMessage(this.s, frame.payload);
  }

  /** 서버 쪽에서 닫는다(끊김·교체 흉내) */
  drop(code: number) {
    if (this.closed) return;
    this.closed = true;
    if (this.s.socket === this) {
      this.s.socket = null;
      this.s.dropAt = tMin(this.s);
    }
    this.onclose?.({ code });
  }

  close() {
    this.closed = true;
    if (this.s.socket === this) this.s.socket = null;
  }
}

export function createMockSocket(url: string) {
  const id = decodeURIComponent(url.split("/ws/sessions/")[1]?.split("?")[0] ?? "");
  const s = byId(id);
  const previous = s.socket;
  const socket = new MockSocket(s);
  s.socket = socket;
  if (previous) {
    previous.deliver({ type: "session.replaced", payload: {} });
    previous.drop(4000);
  }
  if (s.dropAt != null) {
    // 끊긴 구간은 서버가 기록한다(contracts connection_gaps)
    s.gaps.push({ from_t_min: s.dropAt, to_t_min: tMin(s) });
    s.dropAt = null;
  }
  return socket;
}

// ── mock 조작 패널이 부르는 함수 ─────────────────────────────

export type MockControls = {
  now: () => number;
  status: () => SessionStatus;
  scenes: () => { id: string; at_min: number; label: string; fired: boolean }[];
  /** 다음 장면 시각으로 시계를 옮기고 그 장면을 실행한다 */
  nextScene: () => void;
  /** 세션 시계를 at 분으로 옮긴다(그 사이 장면은 순서대로 실행) */
  jumpTo: (at: number) => void;
  /** 소켓을 끊는다. 화면은 3초 뒤 다시 붙고 끊긴 구간이 기록된다 */
  drop: (code?: number) => void;
  /** 보고 대기 5분을 지나게 한다 */
  passDeadline: () => void;
};

export function mockControls(sessionId: string): MockControls {
  const s = byId(sessionId);
  const jumpTo = (at: number) => {
    if (s.status !== "in_progress" && s.status !== "reporting") return;
    const shift = Date.now() - at * MINUTE - (s.startedAt ?? 0);
    s.startedAt = Date.now() - at * MINUTE;
    // 시계를 옮기면 이미 기록된 절대 시각도 같이 옮겨 세션 분이 그대로 유지되게 한다
    if (s.division) {
      s.division.decided_at = new Date(Date.parse(s.division.decided_at) + shift).toISOString();
    }
    for (const scene of script.scenes) if (scene.at_min <= at) fireScene(s, scene);
    if (at >= SESSION_MINUTES) submit(s, true);
  };
  return {
    now: () => tMin(s),
    status: () => s.status,
    scenes: () =>
      script.scenes.map((scene) => ({
        id: scene.id,
        at_min: scene.at_min,
        label: scene.label,
        fired: s.firedScenes.has(scene.id),
      })),
    nextScene: () => {
      const next = script.scenes.find((scene) => !s.firedScenes.has(scene.id));
      if (next) jumpTo(Math.max(next.at_min, tMin(s)));
    },
    jumpTo,
    drop: (code = 1006) => s.socket?.drop(code),
    passDeadline: () => complete(s),
  };
}

// ── REST ───────────────────────────────────────────────────

function entry(s: MockSession): Entry {
  const body: Entry = { ...(entryFixture as Entry), status: s.status };
  if (!["invited", "in_progress", "reporting"].includes(s.status)) {
    body.debrief_token = jwt("debrief", s.id);
  }
  if (s.failedStage) body.failed_stage = s.failedStage;
  return body;
}

/** 제출 뒤 문서·보드·어시스턴트는 409 session_ending(contracts 지원자 REST) */
function writable(s: MockSession) {
  if (s.submittedAt != null || s.status === "reporting") {
    throw new MockApiError(409, "session_ending");
  }
  if (s.status !== "in_progress") throw new MockApiError(409, "conflict");
}

function validDivision(tasks: Task[]) {
  const a = (n: number) => tasks.find((t) => t.part_no === n)?.assignee;
  return (
    a(2) === "candidate" &&
    (a(3) === "colleague" || a(3) === "both") &&
    (a(4) === "colleague" || a(5) === "colleague")
  );
}

function myDoc(s: MockSession, part: string) {
  const doc = s.myDocs.find((d) => d.part_no === Number(part));
  if (!doc) throw new MockApiError(404, "not_found");
  return doc;
}

/** 문서 카드 본문은 지원자가 쓴 한마디(note)뿐이다. 시스템이 지원자 말을 대신 쓰지 않는다(contracts share) */
function share(s: MockSession, part: string, channel: "team" | "dm", note?: string) {
  writable(s);
  const doc = myDoc(s, part);
  const version = doc.versions.length + 1;
  const card = message(s, channel, "candidate", note?.trim() ?? "", {
    shared_doc: { doc_id: doc.doc_id, version },
  });
  doc.versions.push({
    version,
    revision: doc.revision,
    channel,
    message_id: card.id,
    t_min: card.t_min,
  });
  emit(s, { type: "message.new", payload: card });
  emit(s, {
    type: "document.shared",
    payload: {
      doc_id: doc.doc_id,
      version,
      part_no: doc.part_no,
      by: "candidate",
      channel,
      message_id: card.id,
    },
  });
  // 리뷰 장면 뒤에 보내면 동료가 의견을 남긴다
  if (s.firedScenes.has("review")) {
    personaReply(s, "colleague", channel, "받았어요, 읽어 보고 의견 드릴게요.");
  }
  return { version, message_id: card.id };
}

function updateTask(s: MockSession, part: string, body: Partial<Task>) {
  writable(s);
  const task = s.tasks.find((t) => t.part_no === Number(part));
  if (!task) throw new MockApiError(404, "not_found");
  const next = { ...task };
  if (body.assignee !== undefined) next.assignee = body.assignee;
  if (body.status !== undefined) next.status = body.status;
  if (body.order !== undefined) next.order = body.order;
  if (body.due_min !== undefined) next.due_min = body.due_min;
  const tasks = s.tasks.map((t) => (t.part_no === task.part_no ? next : t));
  const full = tasks.every((t) => t.assignee != null);
  if (full && body.assignee !== undefined && !validDivision(tasks)) {
    throw new MockApiError(422, "invalid_division", DIVISION_RULE);
  }
  s.tasks = tasks;
  emit(s, { type: "task.updated", payload: { ...next, by: "candidate" } });
  if (full && !s.division) confirmDivision(s, "candidate");
  else if (s.division && body.assignee !== undefined) {
    s.division = {
      ...s.division,
      parts: { ...s.division.parts, [String(next.part_no)]: next.assignee! },
    };
  }
  return next;
}

function importSection(
  s: MockSession,
  part: string,
  body: { source_doc_id: string; version: number | null },
) {
  writable(s);
  const section = s.final.find((x) => x.part_no === Number(part));
  if (!section) throw new MockApiError(404, "not_found");
  let content: string | undefined;
  // 내 문서는 version null이면 보내지 않은 현재 저장본(contracts import)
  const mine = s.myDocs.find((d) => d.doc_id === body.source_doc_id);
  if (mine) content = mine.content;
  else {
    const doc = s.received.find((d) => d.doc_id === body.source_doc_id);
    if (body.version == null || !doc?.versions.some((v) => v.version === body.version)) {
      throw new MockApiError(404, "not_found");
    }
    content = s.colleagueText[body.source_doc_id]?.[body.version] ?? "";
  }
  Object.assign(section, {
    content,
    source_doc_id: body.source_doc_id,
    source_version: body.version,
    edited: false,
  });
  return section;
}

function openDoc(s: MockSession, docId: string, version: number) {
  writable(s);
  const doc = s.received.find((d) => d.doc_id === docId);
  const v = doc?.versions.find((x) => x.version === version);
  if (!doc || !v) throw new MockApiError(404, "not_found");
  v.opened = true;
  s.opens.push({ doc_id: docId, version, t_min: tMin(s) });
  return {
    doc_id: docId,
    owner: "colleague",
    part_no: doc.part_no,
    title: doc.title,
    version,
    content: s.colleagueText[docId]?.[version] ?? "",
    t_min: tMin(s),
  };
}

function ask(s: MockSession, prompt: string) {
  writable(s);
  const first = s.assistant.length === 0;
  const call: AssistantCall = {
    call_id: nextId(s, "ac-x"),
    request: prompt,
    response: first ? assistantFixture.content : script.assistant_reply,
    cited_docs: first ? assistantFixture.cited_docs : ["metrics", "meeting_notes"],
    t_min: tMin(s),
  };
  s.assistant.push(call);
  return {
    call_id: call.call_id,
    message_id: nextId(s, "m-a"),
    content: call.response,
    cited_docs: call.cited_docs,
  };
}

export const ROUTES: MockRoute[] = [
  ["GET", "/s/:token", ({ token }) => entry(session(token))],
  [
    "POST",
    "/s/:token/consent",
    ({ token }) => {
      const s = session(token);
      if (s.status !== "invited") throw new MockApiError(409, "conflict");
      return { session_token: jwt("candidate", s.id) };
    },
  ],
  [
    "POST",
    "/s/:token/resume",
    ({ token }) => {
      const s = session(token);
      if (s.status !== "in_progress" && s.status !== "reporting") {
        throw new MockApiError(409, "conflict");
      }
      return { session_token: jwt("candidate", s.id) };
    },
  ],
  [
    "POST",
    "/s/:token/start",
    ({ token }) => {
      const s = session(token);
      if (s.status === "invited") {
        s.status = "in_progress";
        s.startedAt = Date.now();
      }
      return { session_id: s.id, started_at: iso(s.startedAt), ends_at: iso(endsAt(s)) };
    },
  ],
  ["GET", "/sessions/:id/state", ({ id }) => snapshot(byId(id))],
  [
    "PUT",
    "/sessions/:id/my-documents/:part",
    ({ id, part }, body) => {
      const s = byId(id);
      writable(s);
      if (part === "final") {
        for (const edit of (body as { sections: { part_no: number; content: string }[] })
          .sections) {
          const section = s.final.find((x) => x.part_no === edit.part_no);
          if (section && section.content !== edit.content) {
            section.content = edit.content;
            section.edited = true;
          }
        }
        return { updated_at: new Date().toISOString(), revision: 0 };
      }
      const doc = myDoc(s, part);
      const content = (body as { content: string }).content;
      if (doc.content !== content) {
        doc.content = content;
        doc.revision += 1;
        doc.updated_at = new Date().toISOString();
      }
      return { updated_at: doc.updated_at, revision: doc.revision };
    },
  ],
  [
    "POST",
    "/sessions/:id/my-documents/:part/share",
    ({ id, part }, body) => {
      const { channel, note } = body as { channel: "team" | "dm"; note?: string };
      return share(byId(id), part, channel, note);
    },
  ],
  [
    "POST",
    "/sessions/:id/documents/:doc/open",
    ({ id, doc }, body) => openDoc(byId(id), doc, (body as DocRef).version),
  ],
  [
    "PUT",
    "/sessions/:id/final/sections/:part/import",
    ({ id, part }, body) =>
      importSection(byId(id), part, body as { source_doc_id: string; version: number | null }),
  ],
  [
    "PUT",
    "/sessions/:id/tasks/:part",
    ({ id, part }, body) => updateTask(byId(id), part, body as Partial<Task>),
  ],
  ["GET", "/sessions/:id/documents", ({ id }) => byId(id).documents],
  [
    "GET",
    "/sessions/:id/documents/:doc",
    ({ id, doc }) => {
      const s = byId(id);
      const found = s.documents.find((d) => d.doc_id === doc);
      if (!found) throw new MockApiError(404, "not_found");
      if (!found.released) throw new MockApiError(423, "not_released");
      return {
        doc_id: doc,
        title: found.title,
        content: script.company_docs[doc as keyof typeof script.company_docs] ?? "",
      };
    },
  ],
  [
    "POST",
    "/sessions/:id/assistant",
    ({ id }, body) => ask(byId(id), (body as { prompt: string }).prompt),
  ],
  [
    "POST",
    "/sessions/:id/submit",
    ({ id }) => {
      const s = byId(id);
      submit(s, false);
      return { status: s.status, deadline_at: iso(s.deadlineAt) };
    },
  ],
  [
    "GET",
    "/sessions/:id/debrief",
    ({ id }) => {
      const s = byId(id);
      if (["invited", "in_progress", "reporting"].includes(s.status)) {
        throw new MockApiError(409, "conflict");
      }
      if (s.failedStage === "session") return debriefFailed;
      const debrief = structuredClone(debriefFixture);
      debrief.survey.submitted = s.survey;
      // demo는 실제로 쓴 최종본을 보여 준다
      if (s.token === "demo") {
        debrief.final = {
          sections: s.final.map(({ part_no, title, content }) => ({ part_no, title, content })),
        };
        debrief.connection_gaps = s.gaps;
      }
      return debrief;
    },
  ],
  [
    "POST",
    "/sessions/:id/debrief/survey",
    ({ id }) => {
      byId(id).survey = true;
      return { submitted: true };
    },
  ],
];

/** 테스트에서 mock 서버를 처음 상태로 돌린다. */
export function resetMockOffice() {
  sessions.forEach((s) => {
    s.socket?.close();
    s.timers.forEach(clearTimeout);
  });
  sessions.clear();
  replyIndex.clear();
}
