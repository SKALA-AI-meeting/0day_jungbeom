// 지원자 화면 mock 경로(web-office 트랙 소유). fixture는 fixtures/office/에 둔다.
// 메모리 안의 작은 "서버"가 세션 상태를 들고 있고, WS는 replay()로 프레임을 흘린다.
// 끊긴 동안의 프레임도 서버 상태에는 반영되므로 재연결 뒤 /state로 복원되는 모습을 볼 수 있다.
//
// 링크 토큰(/s/<토큰>): demo(처음부터), live(진행 중 재입장), done(완료), failed(세션 중단),
// expired·cancelled(410), 그 밖은 404. 개발 중 연결 끊김은 브라우저 콘솔에서
// window.__officeMock.drop()(3초 뒤 재연결), drop(4401)(재발급 후 재연결), drop(4000)(다른 창 접속).
import type {
  AssistantCall,
  Entry,
  ServerFrame,
  StateSnapshot,
  Task,
} from "@/components/office/types";

import debrief from "./fixtures/office/debrief.json";
import scripted from "./fixtures/office/frames.json";
import seed from "./fixtures/office/session.json";
import replyTemplate from "./fixtures/ws_events.json";
import type { MockRoute } from "./types";
import { replay, type ReplayFrame } from "./ws-replay";

const SESSION_MINUTES = 120;

export class MockApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

type MockSession = {
  token: string;
  id: string;
  status: StateSnapshot["session"]["status"];
  failed_stage?: "session" | "report";
  started_at: number | null;
  submitted: boolean;
  state: Omit<StateSnapshot, "session" | "active_runs"> & {
    active_runs: StateSnapshot["active_runs"];
    contents: Record<string, string>;
  };
  socket: MockSocket | null;
  scripted: boolean;
  seq: number;
  /** client_msg_id → [message_id, run_id] (재전송은 기존 메시지로 ack) */
  sent: Map<string, [string, string]>;
};

const INITIAL: Record<string, Pick<MockSession, "status" | "failed_stage">> = {
  demo: { status: "invited" },
  live: { status: "in_progress" },
  done: { status: "completed" },
  failed: { status: "failed", failed_stage: "session" },
};

const sessions = new Map<string, MockSession>();

function session(token: string): MockSession {
  if (token === "expired" || token === "cancelled") throw new MockApiError(410, token);
  const initial = INITIAL[token];
  if (!initial) throw new MockApiError(404, "not_found");
  let found = sessions.get(token);
  if (!found) {
    found = {
      token,
      id: `mock-${token}`,
      ...initial,
      started_at: initial.status === "in_progress" ? Date.now() - 30 * 60_000 : null,
      submitted: false,
      state: { ...structuredClone(seed), active_runs: [] } as MockSession["state"],
      socket: null,
      scripted: false,
      seq: 0,
      sent: new Map(),
    };
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

function iso(ms: number | null) {
  return ms == null ? null : new Date(ms).toISOString();
}

function endsAt(s: MockSession) {
  return s.started_at == null ? null : s.started_at + SESSION_MINUTES * 60_000;
}

function snapshot(s: MockSession): StateSnapshot {
  const { contents: _contents, ...state } = s.state;
  void _contents;
  const ends = endsAt(s);
  return {
    session: {
      id: s.id,
      status: s.status,
      started_at: iso(s.started_at),
      ends_at: iso(ends),
      remaining_seconds: ends == null ? null : Math.max(0, Math.floor((ends - Date.now()) / 1000)),
    },
    ...state,
  };
}

function tMin(s: MockSession) {
  return s.started_at == null ? 0 : Math.round(((Date.now() - s.started_at) / 60_000) * 100) / 100;
}

/** 서버 상태에 프레임을 반영하고, 붙어 있는 소켓이 있으면 보낸다. */
function emit(s: MockSession, frame: { type: string; payload: Record<string, unknown> }) {
  const f = frame as ServerFrame;
  const state = s.state;
  if (f.type === "message.new" && !state.messages.some((m) => m.id === f.payload.id)) {
    state.messages.push(f.payload);
  } else if (f.type === "document.part_updated") {
    const { part_no, content, revision, by } = f.payload;
    state.document[String(part_no)] = { content, revision, updated_by: by };
  } else if (f.type === "document.released") {
    state.documents = state.documents.map((d) =>
      d.doc_id === f.payload.doc_id ? { ...d, released: true } : d,
    );
  } else if (f.type === "task.updated") {
    state.tasks = state.tasks.map((t) => (t.part_no === f.payload.part_no ? f.payload : t));
  } else if (f.type === "agent.progress") {
    const { run_id, actor, node, status } = f.payload;
    state.active_runs = state.active_runs.filter((r) => r.run_id !== run_id);
    if (status !== "finished" && status !== "failed")
      state.active_runs.push({ run_id, actor, node });
  }
  s.socket?.deliver(frame);
}

/** 지원자 메시지 하나에 대한 서버 응답: ack → 내 메시지 → 동료 진행 표시 → 답장(ws_events.json 순서). */
function answer(
  s: MockSession,
  payload: { client_msg_id: string; channel: string; content: string },
) {
  const known = s.sent.get(payload.client_msg_id);
  if (known) {
    const [message_id, run_id] = known;
    emit(s, {
      type: "message.ack",
      payload: { client_msg_id: payload.client_msg_id, message_id, run_id },
    });
    return;
  }
  s.seq += 1;
  const messageId = `m-c${s.seq}`;
  const runId = `r-c${s.seq}`;
  s.sent.set(payload.client_msg_id, [messageId, runId]);
  const frames = (replyTemplate as ReplayFrame[]).map((frame) => {
    const p = { ...frame.payload };
    if (frame.type === "message.ack")
      Object.assign(p, {
        client_msg_id: payload.client_msg_id,
        message_id: messageId,
        run_id: runId,
      });
    if (frame.type === "agent.progress") p.run_id = runId;
    if (frame.type === "message.new") {
      const mine = p.sender === "candidate";
      Object.assign(p, {
        id: mine ? messageId : `m-r${s.seq}`,
        channel: payload.channel,
        run_id: mine ? null : runId,
        t_min: tMin(s),
        created_at: new Date().toISOString(),
        ...(mine ? { content: payload.content } : {}),
      });
    }
    return { ...frame, payload: p };
  });
  // 문서 공개 프레임은 세션 대본(frames.json)이 보낸다
  replay(
    (frame) => emit(s, frame),
    frames.filter((f) => f.type !== "document.released"),
  );
}

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
    const frame = JSON.parse(data);
    if (frame.type !== "message.send") return;
    if (this.s.submitted) {
      this.deliver({ type: "error", payload: { code: "session_ending", message: "submitted" } });
      return;
    }
    answer(this.s, frame.payload);
  }

  /** 서버 쪽에서 닫는다(끊김·교체 흉내) */
  drop(code: number) {
    if (this.closed) return;
    this.closed = true;
    if (this.s.socket === this) this.s.socket = null;
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
  if (!s.scripted) {
    // 세션 대본은 서버 시계로 한 번만 돈다. 끊긴 동안의 프레임도 상태에는 남는다
    s.scripted = true;
    replay((frame) => emit(s, frame), scripted as ReplayFrame[]);
  }
  if (typeof window !== "undefined") {
    (window as unknown as { __officeMock: unknown }).__officeMock = {
      drop: (code = 1006) => s.socket?.drop(code),
    };
  }
  return socket;
}

function entry(s: MockSession): Entry {
  const body: Entry = {
    company_name: "루프랩",
    duration_minutes: SESSION_MINUTES,
    status: s.status,
    elements_names: ["협력 태도", "책임감"],
    entry_notice:
      "한 번에 2시간 연속으로 진행하며 중간 휴식은 없습니다. PC 환경을 권장합니다. 업무는 가상 회사 루프랩에서 하며, 지원자는 이번 과제의 리드를 맡습니다.",
  };
  if (s.status !== "invited" && s.status !== "in_progress")
    body.debrief_token = jwt("debrief", s.id);
  if (s.failed_stage) body.failed_stage = s.failed_stage;
  return body;
}

function writable(s: MockSession) {
  if (s.submitted) throw new MockApiError(409, "session_ending");
  if (s.status !== "in_progress") throw new MockApiError(409, "conflict");
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
      if (s.status !== "in_progress") throw new MockApiError(409, "conflict");
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
        s.started_at = Date.now();
      }
      return { session_id: s.id, started_at: iso(s.started_at), ends_at: iso(endsAt(s)) };
    },
  ],
  ["GET", "/sessions/:id/state", ({ id }) => snapshot(byId(id))],
  [
    "PUT",
    "/sessions/:id/document/:part",
    ({ id, part }, body) => {
      const s = byId(id);
      writable(s);
      // 분업 확정 뒤 동료 단독 파트는 403(contracts.md "지원자 문서 PUT 권한")
      const task = s.state.tasks.find((t) => t.part_no === Number(part));
      if (task?.assignee === "colleague") throw new MockApiError(403, "forbidden");
      const current = s.state.document[part];
      const content = (body as { content: string }).content;
      if (current.content !== content) {
        s.state.document[part] = {
          content,
          revision: current.revision + 1,
          updated_by: "candidate",
        };
      }
      return { updated_at: new Date().toISOString(), revision: s.state.document[part].revision };
    },
  ],
  [
    "PUT",
    "/sessions/:id/tasks/:part",
    ({ id, part }, body) => {
      const s = byId(id);
      writable(s);
      const task = s.state.tasks.find((t) => t.part_no === Number(part));
      if (!task) throw new MockApiError(404, "not_found");
      if (task.assignee === "colleague") throw new MockApiError(403, "forbidden");
      task.status = (body as { status: Task["status"] }).status;
      return task;
    },
  ],
  ["GET", "/sessions/:id/documents", ({ id }) => byId(id).state.documents],
  [
    "GET",
    "/sessions/:id/documents/:doc",
    ({ id, doc }) => {
      const s = byId(id);
      const found = s.state.documents.find((d) => d.doc_id === doc);
      if (!found) throw new MockApiError(404, "not_found");
      if (!found.released) throw new MockApiError(423, "not_released");
      return { doc_id: doc, title: found.title, content: s.state.contents[doc] };
    },
  ],
  [
    "POST",
    "/sessions/:id/assistant",
    ({ id }, body) => {
      const s = byId(id);
      writable(s);
      s.seq += 1;
      const call: AssistantCall = {
        call_id: `a-${s.seq}`,
        request: (body as { prompt: string }).prompt,
        response:
          "지표 현황 문서 기준으로 휴면 사용자 재참여율은 22%예요. 재참여 목표를 잡을 때 이 값을 기준선으로 두면 좋겠어요.\n\n출처: 지표 현황",
        cited_docs: ["metrics"],
        t_min: tMin(s),
      };
      s.state.assistant.push(call);
      return {
        call_id: call.call_id,
        message_id: `m-a${s.seq}`,
        content: call.response,
        cited_docs: call.cited_docs,
      };
    },
  ],
  [
    "POST",
    "/sessions/:id/submit",
    ({ id }) => {
      const s = byId(id);
      if (!s.submitted && s.status === "in_progress") {
        s.submitted = true;
        s.status = "completed";
        emit(s, { type: "session.ended", payload: { reason: "submitted" } });
      }
      return { status: "completed" };
    },
  ],
  [
    "GET",
    "/sessions/:id/debrief",
    ({ id }) => {
      const s = byId(id);
      if (s.status === "invited" || s.status === "in_progress") {
        throw new MockApiError(409, "conflict");
      }
      if (s.failed_stage === "session") {
        return {
          events: [],
          persona_note: null,
          scoring_notice:
            "세션이 중간에 중단되어 평가가 진행되지 않았습니다. 채용 담당자가 다시 응시할 수 있도록 새 링크를 보내 드릴 수 있습니다.",
          failed_stage: "session",
        };
      }
      return debrief;
    },
  ],
];

/** 테스트에서 mock 서버를 처음 상태로 돌린다. */
export function resetMockOffice() {
  sessions.forEach((s) => s.socket?.close());
  sessions.clear();
}
