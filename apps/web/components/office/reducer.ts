// 가상 오피스 상태. /state 스냅샷이 전체 상태이고 WS 프레임은 증분이다(contracts.md "재접속 복구 범위").
// 화면 밖에서도 검사할 수 있게 순수 함수로 둔다.
import type {
  ActiveRun,
  Actor,
  AssistantCall,
  Channel,
  Message,
  Part,
  ProgressStatus,
  ServerFrame,
  StateSnapshot,
} from "./types";

export type ChatChannel = "team" | "dm";

/** 보낸 뒤 ack를 기다리는 메시지. ack가 오면 message_id로 확정된다. */
export type Outgoing = {
  client_msg_id: string;
  channel: ChatChannel;
  content: string;
  message_id?: string;
  failed?: string;
};

export type RunView = {
  actor: Actor;
  status: ProgressStatus;
  tool?: string;
  channel?: ChatChannel;
};

/** dirty: 서버에 아직 저장 안 됨(성공해야 풀린다). failed: 마지막 저장 시도가 실패함 */
export type LocalPart = Part & { dirty: boolean; failed?: boolean };

export type OfficeState = {
  sessionId: string;
  status: StateSnapshot["session"]["status"];
  /** 종료 시각(ms). ends_at 기준, 없을 때만 remaining_seconds로 계산 */
  deadline: number | null;
  messages: Message[];
  outgoing: Outgoing[];
  document: Record<number, LocalPart>;
  /** 동료 담당이라 저장이 거부된 파트(안내 표시) */
  rejected: number[];
  tasks: StateSnapshot["tasks"];
  documents: StateSnapshot["documents"];
  /** 방금 열린 회사 문서(잠금 해제 표시) */
  fresh: string[];
  assistant: (AssistantCall & { pending?: boolean })[];
  runs: Record<string, RunView>;
  /** run_id → 그 실행을 시작한 지원자 메시지의 채널 */
  runChannel: Record<string, ChatChannel>;
  persona: StateSnapshot["persona"];
  channel: ChatChannel;
  unread: Record<ChatChannel, number>;
  /** 상단 알림 띠에 띄울 notice 메시지 id(닫으면 빠진다) */
  notices: string[];
  ended: "submitted" | "timeout" | "failed" | null;
  replaced: boolean;
  error: string | null;
};

export type OfficeAction =
  /** frames: /state를 조회하는 동안 도착한 프레임. 스냅샷 위에 순서대로 다시 적용한다 */
  | { type: "snapshot"; state: StateSnapshot; now: number; frames?: ServerFrame[] }
  | { type: "frame"; frame: ServerFrame }
  | { type: "send"; outgoing: Outgoing }
  | { type: "view"; channel: ChatChannel }
  | { type: "edit"; part_no: number; content: string }
  | { type: "saved"; part_no: number; content: string; revision: number }
  | { type: "save_failed"; part_no: number }
  | { type: "rejected"; part_no: number }
  | { type: "task"; part_no: number; status: StateSnapshot["tasks"][number]["status"] }
  | { type: "ask"; call_id: string; request: string }
  | { type: "answer"; call_id: string; response: string | null; cited_docs: string[] }
  | { type: "dismiss_notice"; id: string }
  | { type: "opened"; doc_id: string }
  | { type: "replaced" }
  | { type: "error"; message: string | null };

const ENDED_STATUSES = new Set(["completed", "report_ready", "approving", "reviewed", "failed"]);

function deadlineOf(state: StateSnapshot, now: number) {
  if (state.session.ends_at) return Date.parse(state.session.ends_at);
  const seconds = state.session.remaining_seconds;
  return seconds == null ? null : now + seconds * 1000;
}

/** 스냅샷의 active_runs(status=started)로 진행 표시를 복원한다. 이미 보던 단계는 이어 간다. */
function runsFrom(
  active: ActiveRun[],
  previous: Record<string, RunView>,
  runChannel: Record<string, ChatChannel>,
) {
  const runs: Record<string, RunView> = {};
  for (const run of active) {
    runs[run.run_id] = {
      ...previous[run.run_id],
      status: previous[run.run_id]?.status ?? "started",
      actor: run.actor,
      channel: runChannel[run.run_id],
    };
  }
  return runs;
}

export function initialState(snapshot: StateSnapshot, now: number): OfficeState {
  return reduce(
    {
      sessionId: snapshot.session.id,
      status: snapshot.session.status,
      deadline: null,
      messages: [],
      outgoing: [],
      document: {},
      rejected: [],
      tasks: [],
      documents: [],
      fresh: [],
      assistant: [],
      runs: {},
      runChannel: {},
      persona: snapshot.persona,
      channel: "team",
      unread: { team: 0, dm: 0 },
      notices: [],
      ended: null,
      replaced: false,
      error: null,
    },
    { type: "snapshot", state: snapshot, now },
  );
}

function isChat(channel: Channel): channel is ChatChannel {
  return channel === "team" || channel === "dm";
}

/** 새로 알게 된 메시지를 채널별 안 읽음·알림 띠에 반영한다. */
function arrive(state: OfficeState, incoming: Message[]): Pick<OfficeState, "unread" | "notices"> {
  const unread = { ...state.unread };
  const notices = [...state.notices];
  for (const message of incoming) {
    if (message.channel === "notice") notices.push(message.id);
    else if (isChat(message.channel) && message.sender !== "candidate") {
      if (message.channel !== state.channel) unread[message.channel] += 1;
    }
  }
  return { unread, notices };
}

function snapshot(
  state: OfficeState,
  snap: StateSnapshot,
  now: number,
  frames: ServerFrame[] = [],
): OfficeState {
  const known = new Set(state.messages.map((m) => m.id));
  const first = state.messages.length === 0 && state.deadline === null;
  // 첫 스냅샷은 지난 대화라 채널 안 읽음으로 세지 않는다(notice 알림 띠는 복원한다).
  // 재접속이면 그사이 온 것만 센다
  const incoming = first
    ? snap.messages.filter((m) => m.channel === "notice")
    : snap.messages.filter((m) => !known.has(m.id));
  const document: Record<number, LocalPart> = {};
  for (const [key, part] of Object.entries(snap.document)) {
    const local = state.document[Number(key)];
    // 아직 저장되지 않은 내 수정은 서버 값으로 덮지 않는다
    document[Number(key)] = local?.dirty ? local : { ...part, dirty: false };
  }
  const delivered = new Set(snap.messages.map((m) => m.id));
  const pendingAsks = state.assistant.filter(
    (a) => a.pending && !snap.assistant.some((s) => s.call_id === a.call_id),
  );
  const base: OfficeState = {
    ...state,
    ...arrive(state, incoming),
    sessionId: snap.session.id,
    status: snap.session.status,
    deadline: deadlineOf(snap, now),
    messages: snap.messages,
    outgoing: state.outgoing.filter((o) => !(o.message_id && delivered.has(o.message_id))),
    document,
    tasks: snap.tasks,
    documents: snap.documents,
    assistant: [...snap.assistant, ...pendingAsks],
    runs: runsFrom(snap.active_runs, state.runs, state.runChannel),
    persona: snap.persona,
    ended: ENDED_STATUSES.has(snap.session.status) ? (state.ended ?? "submitted") : null,
  };
  // 조회 중 도착한 증분을 다시 얹는다. 이미 화면에서 센 메시지는 안 읽음을 다시 세지 않는다
  return frames.reduce((acc, f) => {
    if (f.type === "message.new" && known.has(f.payload.id)) {
      if (acc.messages.some((m) => m.id === f.payload.id)) return acc;
      return { ...acc, messages: [...acc.messages, f.payload] };
    }
    return frame(acc, f);
  }, base);
}

function frame(state: OfficeState, f: ServerFrame): OfficeState {
  switch (f.type) {
    case "message.ack": {
      const { client_msg_id, message_id, run_id } = f.payload;
      const out = state.outgoing.find((o) => o.client_msg_id === client_msg_id);
      const runChannel = out ? { ...state.runChannel, [run_id]: out.channel } : state.runChannel;
      const delivered = state.messages.some((m) => m.id === message_id);
      return {
        ...state,
        runChannel,
        outgoing: delivered
          ? state.outgoing.filter((o) => o.client_msg_id !== client_msg_id)
          : state.outgoing.map((o) =>
              o.client_msg_id === client_msg_id ? { ...o, message_id } : o,
            ),
      };
    }
    case "message.new": {
      const message = f.payload;
      if (state.messages.some((m) => m.id === message.id)) return state;
      return {
        ...state,
        ...arrive(state, [message]),
        messages: [...state.messages, message],
        outgoing: state.outgoing.filter((o) => o.message_id !== message.id),
      };
    }
    case "agent.progress": {
      const { run_id, actor, status, tool } = f.payload;
      const runs = { ...state.runs };
      if (status === "finished" || status === "failed") delete runs[run_id];
      else runs[run_id] = { actor, status, tool, channel: state.runChannel[run_id] };
      return { ...state, runs };
    }
    case "document.released": {
      const { doc_id, title } = f.payload;
      const exists = state.documents.some((d) => d.doc_id === doc_id);
      return {
        ...state,
        documents: exists
          ? state.documents.map((d) => (d.doc_id === doc_id ? { ...d, released: true } : d))
          : [...state.documents, { doc_id, title, released: true }],
        fresh: state.fresh.includes(doc_id) ? state.fresh : [...state.fresh, doc_id],
      };
    }
    case "document.part_updated": {
      const { part_no, content, revision, by } = f.payload;
      const current = state.document[part_no];
      if (current && current.revision >= revision) return state;
      return {
        ...state,
        document: {
          ...state.document,
          [part_no]: { content, revision, updated_by: by, dirty: false },
        },
      };
    }
    case "task.updated": {
      const task = f.payload;
      const exists = state.tasks.some((t) => t.part_no === task.part_no);
      const tasks = exists
        ? state.tasks.map((t) => (t.part_no === task.part_no ? task : t))
        : [...state.tasks, task].sort((a, b) => a.part_no - b.part_no);
      return { ...state, tasks };
    }
    case "session.ended":
      return { ...state, ended: f.payload.reason, runs: {} };
    case "session.replaced":
      return { ...state, replaced: true };
    case "error":
      return {
        ...state,
        error:
          f.payload.code === "session_ending" ? "세션이 마무리되는 중이에요." : f.payload.message,
      };
  }
}

export function reduce(state: OfficeState, action: OfficeAction): OfficeState {
  switch (action.type) {
    case "snapshot":
      return snapshot(state, action.state, action.now, action.frames);
    case "frame":
      return frame(state, action.frame);
    case "send":
      return { ...state, outgoing: [...state.outgoing, action.outgoing], error: null };
    case "view":
      return {
        ...state,
        channel: action.channel,
        unread: { ...state.unread, [action.channel]: 0 },
      };
    case "edit": {
      const part = state.document[action.part_no] ?? { revision: 0, updated_by: null };
      return {
        ...state,
        document: {
          ...state.document,
          [action.part_no]: { ...part, content: action.content, dirty: true },
        },
      };
    }
    case "saved": {
      const part = state.document[action.part_no];
      if (!part) return state;
      // 저장하는 사이 더 고쳤으면 dirty를 유지한다
      const dirty = part.content !== action.content;
      return {
        ...state,
        document: {
          ...state.document,
          [action.part_no]: {
            ...part,
            revision: action.revision,
            updated_by: "candidate",
            dirty,
            failed: false,
          },
        },
      };
    }
    case "save_failed": {
      const part = state.document[action.part_no];
      if (!part) return state;
      return {
        ...state,
        document: { ...state.document, [action.part_no]: { ...part, failed: true } },
      };
    }
    case "rejected": {
      // 서버 본문은 이어지는 스냅샷이 채운다. 저장된 것처럼 보이지 않게 dirty만 푼다
      const part = state.document[action.part_no];
      return {
        ...state,
        document: part
          ? { ...state.document, [action.part_no]: { ...part, dirty: false, failed: false } }
          : state.document,
        rejected: state.rejected.includes(action.part_no)
          ? state.rejected
          : [...state.rejected, action.part_no],
      };
    }
    case "task":
      return {
        ...state,
        tasks: state.tasks.map((t) =>
          t.part_no === action.part_no ? { ...t, status: action.status } : t,
        ),
      };
    case "ask":
      return {
        ...state,
        assistant: [
          ...state.assistant,
          {
            call_id: action.call_id,
            request: action.request,
            response: null,
            cited_docs: [],
            t_min: null,
            pending: true,
          },
        ],
      };
    case "answer":
      return {
        ...state,
        assistant: state.assistant.map((a) =>
          a.call_id === action.call_id
            ? { ...a, response: action.response, cited_docs: action.cited_docs, pending: false }
            : a,
        ),
      };
    case "dismiss_notice":
      return { ...state, notices: state.notices.filter((id) => id !== action.id) };
    case "opened":
      return { ...state, fresh: state.fresh.filter((id) => id !== action.doc_id) };
    case "replaced":
      return { ...state, replaced: true };
    case "error":
      return { ...state, error: action.message };
  }
}

/** "이도현이 입력 중…"처럼 진행 중인 실행을 문장으로. channel을 주면 그 채널에 해당하는 것만. */
export function progressLabels(state: OfficeState, channel?: ChatChannel): string[] {
  const labels: string[] = [];
  for (const run of Object.values(state.runs)) {
    if (run.actor === "assistant") continue;
    if (channel && run.channel && run.channel !== channel) continue;
    const name = run.actor === "manager" ? state.persona.manager : state.persona.colleague;
    const label = `${name}${josa(name)} ${run.status === "tool_start" ? "자료 찾는 중…" : "입력 중…"}`;
    if (!labels.includes(label)) labels.push(label);
  }
  return labels;
}

/** 받침이 있으면 "이", 없으면 "가" */
export function josa(name: string) {
  const code = name.charCodeAt(name.length - 1) - 0xac00;
  if (code < 0 || code > 11171) return "이";
  return code % 28 === 0 ? "가" : "이";
}

export function assistantBusy(state: OfficeState) {
  return (
    state.assistant.some((a) => a.pending) ||
    Object.values(state.runs).some((r) => r.actor === "assistant")
  );
}

/** mm:ss. 60분을 넘으면 분이 두 자리를 넘는다(120:00). */
export function formatRemaining(ms: number) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
