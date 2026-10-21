// 가상 오피스 상태. /state 스냅샷이 전체이고 WS 프레임은 증분이다(contracts "재접속 복구 범위").
// 순수 함수라 테스트가 프레임을 그대로 흘려 넣어 확인한다.
import {
  AUTO_SUBMITTED_LINE,
  boardLine,
  divisionLine,
  GAP_LINE_MIN,
  gapLine,
  PRESENCE_LINE,
  SUBMITTED_LINE,
  WAITING_LINE,
  type SysLine,
} from "./lines";
import type {
  AssistantCall,
  Channel,
  DocRef,
  FinalSection,
  Message,
  ServerFrame,
  StateSnapshot,
  Task,
} from "./types";

export type Pending = {
  client_msg_id: string;
  channel: "team" | "dm" | "manager_dm";
  content: string;
  reply_to_doc?: DocRef;
  t_min: number;
};

export type OfficeState = {
  snap: StateSnapshot;
  /** 스냅샷에 없는 라이브 줄(보드 변경·마감 경고) */
  lines: SysLine[];
  pending: Pending[];
  channel: Channel;
  unread: Record<Channel, number>;
  submittedByMe: boolean;
  autoSubmitted: boolean;
  ended: null | "submitted" | "timeout" | "failed" | "cancelled";
  replaced: boolean;
  /** 도구를 쓰는 중인 실행(run_id). "자료 찾는 중…" 표시 */
  searching: string[];
  /** 이 창이 열려 있는 동안 공개된 회사 문서(document.released 프레임 또는 재동기화 스냅샷으로 안다) */
  releasedLater: string[];
  /**
   * 아직 서버에 저장되지 않은 편집(파트 번호·최종본 섹션 → 본문). 재연결 스냅샷이 서버 값으로 덮어도
   * 이 값을 다시 얹어 입력을 잃지 않는다. 저장이 성공하면 같은 본문인 것만 지운다.
   */
  dirty: { parts: Record<number, string>; final: Record<number, string> };
  /** 저장 성공 세대. 저장할 때마다 1씩 늘고, 재동기화는 조회 시작 시점의 값을 since로 넘긴다 */
  saveSeq: number;
  /** 마지막으로 저장에 성공한 본문과 그 세대. 조회 뒤에 저장된 것은 옛 스냅샷보다 최신이다 */
  confirmed: {
    parts: Record<number, { content: string; seq: number }>;
    final: Record<number, { content: string; seq: number }>;
  };
  /** 가져오기에 성공한 최종본 섹션(본문·출처)과 그 세대. 가져오기 전에 만든 스냅샷이 되돌리지 못하게 한다 */
  imported: Record<number, { section: FinalSection; seq: number }>;
};

export type OfficeAction =
  /** frames: 조회하는 동안 도착해 이미 반영한 프레임. 스냅샷 위에 다시 얹어 잃지 않게 한다 */
  /** since: 조회를 시작할 때의 saveSeq. 없으면 지금 받은 최신 스냅샷으로 본다 */
  | { type: "snapshot"; state: StateSnapshot; frames?: ServerFrame[]; since?: number }
  | { type: "frame"; frame: ServerFrame }
  | { type: "view"; channel: Channel }
  | { type: "sending"; pending: Pending }
  | { type: "doc_edit"; part_no: number; content: string }
  | { type: "doc_saved"; part_no: number; content: string; revision: number; updated_at: string }
  | { type: "final_saved"; sections: { part_no: number; content: string }[] }
  /** 다른 창으로 옮겨 갔거나(4000) 접속이 거절됨(4403): 이 창의 쓰기를 잠근다 */
  | { type: "stopped" }
  | {
      type: "shared";
      part_no: number;
      version: number;
      message_id: string;
      channel: "team" | "dm";
      t_min: number;
    }
  | { type: "final_edit"; part_no: number; content: string }
  | { type: "final_section"; section: FinalSection }
  | { type: "task_local"; task: Task }
  | { type: "opened"; doc_id: string; version: number }
  | { type: "assistant"; call: AssistantCall }
  | { type: "line"; line: SysLine }
  /** 제출 요청 직전. 응답보다 먼저 올 수 있는 session.reporting을 자동 제출로 오해하지 않게 한다 */
  | { type: "submitting"; on: boolean }
  | { type: "submitted"; deadline_at: string | null; status: string };

const ZERO: Record<Channel, number> = { team: 0, dm: 0, manager_dm: 0, notice: 0 };

export function initialState(snap: StateSnapshot): OfficeState {
  return {
    snap,
    lines: [],
    pending: [],
    channel: "team",
    unread: { ...ZERO },
    submittedByMe: false,
    autoSubmitted: false,
    ended: null,
    replaced: false,
    searching: [],
    releasedLater: [],
    dirty: { parts: {}, final: {} },
    saveSeq: 0,
    confirmed: { parts: {}, final: {} },
    imported: {},
  };
}

function without(record: Record<number, string>, key: number, content?: string) {
  if (!(key in record) || (content !== undefined && record[key] !== content)) return record;
  const next = { ...record };
  delete next[key];
  return next;
}

/**
 * 스냅샷 위에 이 창이 더 최신으로 아는 본문을 다시 얹는다: 조회 뒤에 성공한 가져오기(본문·출처), 조회 뒤에
 * 저장에 성공한 본문(since보다 큰 세대), 그다음 아직 저장 전인 편집. 제출 뒤에는 서버 값이 맞으므로 얹지 않는다.
 */
function withLocal(given: StateSnapshot, state: OfficeState, since: number): StateSnapshot {
  if (given.session.status !== "in_progress") return given;
  const imports = Object.values(state.imported).filter((v) => v.seq > since);
  const snap = imports.length
    ? {
        ...given,
        final: {
          ...given.final,
          sections: given.final.sections.map((sec) => {
            const hit = imports.find((v) => v.section.part_no === sec.part_no);
            return hit ? { ...sec, ...hit.section } : sec;
          }),
        },
      }
    : given;
  const parts: Record<number, string> = {};
  const final: Record<number, string> = {};
  for (const [k, v] of Object.entries(state.confirmed.parts))
    if (v.seq > since) parts[+k] = v.content;
  for (const [k, v] of Object.entries(state.confirmed.final))
    if (v.seq > since) final[+k] = v.content;
  return withDirty(snap, {
    parts: { ...parts, ...state.dirty.parts },
    final: { ...final, ...state.dirty.final },
  });
}

function withDirty(snap: StateSnapshot, dirty: OfficeState["dirty"]): StateSnapshot {
  return {
    ...snap,
    my_documents: snap.my_documents.map((d) =>
      d.part_no in dirty.parts ? { ...d, content: dirty.parts[d.part_no] } : d,
    ),
    final: {
      ...snap.final,
      sections: snap.final.sections.map((sec) =>
        sec.part_no in dirty.final && sec.content !== dirty.final[sec.part_no]
          ? { ...sec, content: dirty.final[sec.part_no], edited: true }
          : sec,
      ),
    },
  };
}

export function partTitles(snap: StateSnapshot): Record<number, string> {
  const titles: Record<number, string> = {};
  for (const s of snap.final.sections) titles[s.part_no] = s.title;
  for (const d of snap.my_documents) titles[d.part_no] ??= d.title;
  return titles;
}

/**
 * 내가 바꾼 보드 카드의 줄. 담당·언제까지만 남긴다(상태·순서는 끌 때마다 생겨 대화를 덮는다).
 * 분업 확정 전의 담당 지정은 "분업이 정해졌어요" 한 줄로 모이므로 남기지 않는다.
 */
export function boardLineFor(state: OfficeState, before: Task, after: Task): SysLine | null {
  const assigneeChanged = before.assignee !== after.assignee;
  if (!assigneeChanged && before.due_min === after.due_min) return null;
  if (assigneeChanged && !state.snap.division) return null;
  const text = boardLine(before, after, "candidate", state.snap.persona);
  if (!text) return null;
  return {
    id: `board-me-${after.part_no}-${state.lines.length}`,
    channel: "team",
    t_min: nowMin(state.snap),
    kind: "board",
    text,
  };
}

/** 시작 시각 기준 지금 분(스냅샷이 없으면 0) */
export function nowMin(snap: StateSnapshot, now = Date.now()) {
  const started = snap.session.started_at ? Date.parse(snap.session.started_at) : now;
  return Math.max(0, Math.round(((now - started) / 60_000) * 100) / 100);
}

function minAt(snap: StateSnapshot, iso: string | null | undefined) {
  if (!iso || !snap.session.started_at) return 0;
  return (Date.parse(iso) - Date.parse(snap.session.started_at)) / 60_000;
}

function upsertMessage(messages: Message[], message: Message) {
  return messages.some((m) => m.id === message.id) ? messages : [...messages, message];
}

function applyFrame(state: OfficeState, frame: ServerFrame): OfficeState {
  const snap = state.snap;
  switch (frame.type) {
    case "message.ack":
      return {
        ...state,
        pending: state.pending.filter((p) => p.client_msg_id !== frame.payload.client_msg_id),
      };
    case "message.new": {
      const m = frame.payload;
      const fresh = !snap.messages.some((x) => x.id === m.id);
      const pending =
        m.sender === "candidate"
          ? state.pending.filter((p) => !(p.channel === m.channel && p.content === m.content))
          : state.pending;
      const unread =
        fresh && m.sender !== "candidate" && m.channel !== state.channel
          ? { ...state.unread, [m.channel]: state.unread[m.channel] + 1 }
          : state.unread;
      return {
        ...state,
        pending,
        unread,
        snap: { ...snap, messages: upsertMessage(snap.messages, m) },
      };
    }
    case "agent.progress": {
      const { run_id, actor, node, status } = frame.payload;
      const runs = snap.active_runs.filter((r) => r.run_id !== run_id);
      if (status !== "finished" && status !== "failed") runs.push({ run_id, actor, node });
      const searching = state.searching.filter((id) => id !== run_id);
      if (status === "tool_start") searching.push(run_id);
      return { ...state, searching, snap: { ...snap, active_runs: runs } };
    }
    case "document.released":
      return {
        ...state,
        releasedLater: state.releasedLater.includes(frame.payload.doc_id)
          ? state.releasedLater
          : [...state.releasedLater, frame.payload.doc_id],
        snap: {
          ...snap,
          documents: snap.documents.map((d) =>
            d.doc_id === frame.payload.doc_id ? { ...d, released: true, release_at_min: null } : d,
          ),
        },
      };
    case "document.shared": {
      const p = frame.payload;
      const t = snap.messages.find((m) => m.id === p.message_id)?.t_min ?? nowMin(snap);
      if (p.by === "candidate") {
        return reduce(state, {
          type: "shared",
          part_no: p.part_no,
          version: p.version,
          message_id: p.message_id,
          channel: p.channel,
          t_min: t,
        });
      }
      const titles = partTitles(snap);
      const exists = snap.received.find((d) => d.doc_id === p.doc_id);
      const version = {
        version: p.version,
        channel: p.channel,
        message_id: p.message_id,
        t_min: t,
        opened: false,
      };
      const received = exists
        ? snap.received.map((d) =>
            d.doc_id === p.doc_id && !d.versions.some((v) => v.version === p.version)
              ? { ...d, versions: [...d.versions, version] }
              : d,
          )
        : [
            ...snap.received,
            {
              doc_id: p.doc_id,
              owner: "colleague" as const,
              part_no: p.part_no,
              title: titles[p.part_no] ?? "",
              versions: [version],
            },
          ];
      return { ...state, snap: { ...snap, received } };
    }
    case "task.updated": {
      const { by, ...rest } = frame.payload;
      const before = snap.tasks.find((t) => t.part_no === rest.part_no);
      const after: Task = { ...rest, depends_on: rest.depends_on ?? before?.depends_on ?? [] };
      // 내 변경의 줄은 낙관적 반영 때 화면이 직접 남긴다(boardLineFor). 여기서는 동료 변경만
      const text = by === "colleague" ? boardLine(before, after, by, snap.persona) : null;
      const lines = text
        ? [
            ...state.lines,
            {
              id: `board-${after.part_no}-${state.lines.length}`,
              channel: "team" as const,
              t_min: nowMin(snap),
              kind: "board" as const,
              text,
            },
          ]
        : state.lines;
      return {
        ...state,
        lines,
        snap: { ...snap, tasks: snap.tasks.map((t) => (t.part_no === after.part_no ? after : t)) },
      };
    }
    case "division.confirmed": {
      const { parts, decided_by, t_min } = frame.payload;
      const started = snap.session.started_at ? Date.parse(snap.session.started_at) : Date.now();
      return {
        ...state,
        snap: {
          ...snap,
          division: {
            parts,
            decided_by,
            decided_at: new Date(started + t_min * 60_000).toISOString(),
          },
          tasks: snap.tasks.map((t) => ({
            ...t,
            assignee: parts[String(t.part_no)] ?? t.assignee,
          })),
        },
      };
    }
    case "session.reporting":
      return {
        ...state,
        autoSubmitted: !state.submittedByMe,
        snap: {
          ...snap,
          session: { ...snap.session, status: "reporting", deadline_at: frame.payload.deadline_at },
        },
      };
    case "session.ended":
      return {
        ...state,
        ended: frame.payload.reason,
        snap: { ...snap, session: { ...snap.session, status: "completed" } },
      };
    case "session.replaced":
      return { ...state, replaced: true };
    case "error":
      return state;
  }
}

export function reduce(state: OfficeState, action: OfficeAction): OfficeState {
  const snap = state.snap;
  switch (action.type) {
    case "snapshot": {
      const ended =
        state.ended ??
        (["in_progress", "reporting"].includes(action.state.session.status) ? null : "submitted");
      const live = action.state.session.status === "in_progress";
      // 끊긴 사이 공개된 문서: 이전 스냅샷에서 미공개였다가 새 스냅샷에서 공개된 것
      const releasedNow = action.state.documents
        .filter(
          (d) =>
            d.released &&
            !state.releasedLater.includes(d.doc_id) &&
            snap.documents.some((old) => old.doc_id === d.doc_id && !old.released),
        )
        .map((d) => d.doc_id);
      const base = {
        ...state,
        releasedLater: [...state.releasedLater, ...releasedNow],
        snap: withLocal(action.state, state, action.since ?? state.saveSeq),
        dirty: live ? state.dirty : { parts: {}, final: {} },
        ended,
      };
      return (action.frames ?? []).reduce((acc, frame) => {
        // 안 읽음 수와 보드 줄은 처음 받았을 때 이미 반영했으므로 다시 더하지 않는다
        const next = applyFrame(acc, frame);
        return { ...next, unread: acc.unread, lines: acc.lines };
      }, base);
    }
    case "frame":
      return applyFrame(state, action.frame);
    case "view":
      return {
        ...state,
        channel: action.channel,
        unread: { ...state.unread, [action.channel]: 0 },
      };
    case "sending":
      return { ...state, pending: [...state.pending, action.pending] };
    case "doc_edit":
      return {
        ...state,
        dirty: {
          ...state.dirty,
          parts: { ...state.dirty.parts, [action.part_no]: action.content },
        },
        snap: {
          ...snap,
          my_documents: snap.my_documents.map((d) =>
            d.part_no === action.part_no ? { ...d, content: action.content } : d,
          ),
        },
      };
    case "doc_saved":
      return {
        ...state,
        // 저장하는 사이 더 고쳤으면 그 편집은 남겨 둔다
        dirty: {
          ...state.dirty,
          parts: without(state.dirty.parts, action.part_no, action.content),
        },
        saveSeq: state.saveSeq + 1,
        confirmed: {
          ...state.confirmed,
          parts: {
            ...state.confirmed.parts,
            [action.part_no]: { content: action.content, seq: state.saveSeq + 1 },
          },
        },
        snap: {
          ...snap,
          my_documents: snap.my_documents.map((d) =>
            d.part_no === action.part_no
              ? { ...d, revision: action.revision, updated_at: action.updated_at }
              : d,
          ),
        },
      };
    case "shared":
      return {
        ...state,
        snap: {
          ...snap,
          my_documents: snap.my_documents.map((d) =>
            d.part_no !== action.part_no || d.versions.some((v) => v.version === action.version)
              ? d
              : {
                  ...d,
                  versions: [
                    ...d.versions,
                    {
                      version: action.version,
                      revision: d.revision,
                      channel: action.channel,
                      message_id: action.message_id,
                      t_min: action.t_min,
                    },
                  ],
                },
          ),
        },
      };
    case "final_saved": {
      let final = state.dirty.final;
      const seq = state.saveSeq + 1;
      const confirmed = { ...state.confirmed.final };
      for (const sec of action.sections) {
        final = without(final, sec.part_no, sec.content);
        confirmed[sec.part_no] = { content: sec.content, seq };
      }
      return {
        ...state,
        dirty: { ...state.dirty, final },
        saveSeq: seq,
        confirmed: { ...state.confirmed, final: confirmed },
      };
    }
    case "stopped":
      return { ...state, replaced: true };
    case "final_edit":
      return {
        ...state,
        dirty: {
          ...state.dirty,
          final: { ...state.dirty.final, [action.part_no]: action.content },
        },
        snap: {
          ...snap,
          final: {
            ...snap.final,
            sections: snap.final.sections.map((s) =>
              s.part_no === action.part_no && s.content !== action.content
                ? { ...s, content: action.content, edited: true }
                : s,
            ),
          },
        },
      };
    case "final_section":
      return {
        ...state,
        // 가져오기도 성공한 변경이라 세대를 올린다. 이 세대보다 앞서 조회한 스냅샷은 이 섹션을 되돌리지 못한다
        saveSeq: state.saveSeq + 1,
        imported: {
          ...state.imported,
          [action.section.part_no]: { section: action.section, seq: state.saveSeq + 1 },
        },
        // 가져오기는 서버가 섹션을 덮어쓴 값이 정본이다(그 섹션의 미저장·확정 본문은 버린다)
        dirty: { ...state.dirty, final: without(state.dirty.final, action.section.part_no) },
        confirmed: {
          ...state.confirmed,
          final: Object.fromEntries(
            Object.entries(state.confirmed.final).filter(([k]) => +k !== action.section.part_no),
          ),
        },
        snap: {
          ...snap,
          final: {
            ...snap.final,
            sections: snap.final.sections.map((s) =>
              s.part_no === action.section.part_no ? { ...s, ...action.section } : s,
            ),
          },
        },
      };
    case "task_local":
      return {
        ...state,
        snap: {
          ...snap,
          tasks: snap.tasks.map((t) => (t.part_no === action.task.part_no ? action.task : t)),
        },
      };
    case "opened":
      return {
        ...state,
        snap: {
          ...snap,
          received: snap.received.map((d) =>
            d.doc_id === action.doc_id
              ? {
                  ...d,
                  versions: d.versions.map((v) =>
                    v.version === action.version ? { ...v, opened: true } : v,
                  ),
                }
              : d,
          ),
        },
      };
    case "assistant":
      return { ...state, snap: { ...snap, assistant: [...snap.assistant, action.call] } };
    case "line":
      return state.lines.some((l) => l.id === action.line.id)
        ? state
        : { ...state, lines: [...state.lines, action.line] };
    case "submitting":
      return {
        ...state,
        submittedByMe: action.on,
        autoSubmitted: action.on ? false : state.autoSubmitted,
      };
    case "submitted":
      return {
        ...state,
        submittedByMe: true,
        snap: {
          ...snap,
          session: {
            ...snap.session,
            status: action.status === "completed" ? "completed" : "reporting",
            deadline_at: action.deadline_at,
          },
        },
        ended: action.status === "completed" ? "submitted" : state.ended,
      };
  }
}

// ── 화면이 읽는 값 ─────────────────────────────────────────

export type TimelineItem =
  | { kind: "message"; t_min: number; message: Message }
  | { kind: "pending"; t_min: number; pending: Pending }
  | { kind: "line"; t_min: number; line: SysLine };

/** 스냅샷에서 다시 만들 수 있는 시스템 줄(재접속해도 같은 줄이 나온다) */
export function derivedLines(state: OfficeState): SysLine[] {
  const { snap } = state;
  const lines: SysLine[] = [
    {
      id: "presence",
      channel: "team",
      t_min: -1,
      kind: "presence",
      text: PRESENCE_LINE(snap.persona),
    },
  ];
  if (snap.division) {
    lines.push({
      id: "division",
      channel: "team",
      t_min: minAt(snap, snap.division.decided_at),
      kind: "division",
      text: divisionLine(snap.division.parts, snap.division.decided_by, snap.persona),
    });
  }
  for (const [i, gap] of snap.connection_gaps.entries()) {
    // 짧은 끊김은 재연결 토스트로만 알린다
    if (gap.to_t_min - gap.from_t_min < GAP_LINE_MIN) continue;
    lines.push({
      id: `gap-${i}`,
      channel: "all",
      t_min: gap.from_t_min,
      kind: "gap",
      text: gapLine(gap.from_t_min, gap.to_t_min),
    });
  }
  if (snap.session.status === "reporting") {
    const at = snap.session.deadline_at ? minAt(snap, snap.session.deadline_at) - 5 : nowMin(snap);
    const first = state.autoSubmitted ? AUTO_SUBMITTED_LINE : SUBMITTED_LINE;
    lines.push({
      id: "submitted",
      channel: "all",
      t_min: at + 0.001,
      kind: "submitted",
      text: first,
    });
    lines.push({
      id: "waiting",
      channel: "all",
      t_min: at + 0.002,
      kind: "submitted",
      text: WAITING_LINE,
    });
  }
  return lines;
}

/** system이 보낸 메시지는 줄로 그린다. notice 채널의 카드 알림(event_id 있음)만 메시지로 그린다. */
export function isSystemLine(m: Message) {
  return m.sender === "system" && !(m.channel === "notice" && m.event_id);
}

export function timeline(state: OfficeState, channel: Channel): TimelineItem[] {
  const items: TimelineItem[] = [];
  for (const message of state.snap.messages) {
    if (message.channel !== channel) continue;
    if (isSystemLine(message)) {
      items.push({
        kind: "line",
        t_min: message.t_min,
        line: {
          id: message.id,
          channel,
          t_min: message.t_min,
          kind: message.channel === "notice" ? "release" : "report_guide",
          text: message.content,
        },
      });
    } else {
      // 문서 카드의 "보냈어요"는 카드 메타(주인·버전)와 겹쳐 대화에는 두지 않는다(전체 기록에만 남는다)
      items.push({ kind: "message", t_min: message.t_min, message });
    }
  }
  for (const line of [...derivedLines(state), ...state.lines]) {
    if (line.channel === channel || line.channel === "all")
      items.push({ kind: "line", t_min: line.t_min, line });
  }
  const sorted = items.sort((a, b) => a.t_min - b.t_min);
  // 보내는 중인 메시지는 항상 맨 아래
  for (const pending of state.pending) {
    if (pending.channel === channel)
      sorted.push({ kind: "pending", t_min: pending.t_min, pending });
  }
  return sorted;
}

/** 입력 중 표시: 진행 중인 실행의 actor → 문구 */
export function progressLabels(state: OfficeState) {
  const { persona } = state.snap;
  return state.snap.active_runs
    .filter((r) => r.actor !== "assistant")
    .map((r) => {
      const who = r.actor === "manager" ? persona.manager.split(" ")[0] : persona.colleague;
      return state.searching.includes(r.run_id)
        ? `${who}님이 자료 찾는 중…`
        : `${who}님이 입력 중…`;
    });
}

/**
 * 새 메시지 토스트(보낸 사람·첫 줄). 내 메시지·시스템 줄과 대화 탭에 지금 보이는 채널은 띄우지 않는다.
 * 개인 알림은 놓치면 안 되므로 탭과 상관없이, 그 밖은 대화가 아닌 탭(editing)을 보는 중일 때만 띄운다.
 */
export function shouldToast(
  message: Message,
  ctx: { editing: boolean; channel: Channel; docOpen: boolean },
) {
  if (message.sender === "candidate" || isSystemLine(message)) return false;
  if (message.channel === ctx.channel && !ctx.docOpen && !ctx.editing) return false;
  return message.channel === "notice" || ctx.editing;
}

export function firstLine(text: string, max = 60) {
  const line = text.split("\n")[0];
  return line.length > max ? `${line.slice(0, max)}…` : line;
}

/**
 * 제출 뒤에는 문서·보드·가져오기·어시스턴트를 막는다(서버 409 session_ending). 메시지는 계속 열려 있다.
 * 다른 창으로 옮겨 간 창(replaced)은 모든 쓰기를 막는다.
 */
export function locked(state: OfficeState) {
  return state.snap.session.status !== "in_progress" || state.submittedByMe || state.replaced;
}
