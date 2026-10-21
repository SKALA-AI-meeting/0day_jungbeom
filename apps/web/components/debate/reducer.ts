// 토론 화면 상태. /state 스냅샷이 전체이고 WS 프레임은 증분이다(contracts.md WebSocket).
// seq가 마지막 + 1이 아니면 적용을 멈추고 needsResync를 세워 화면이 /state를 다시 읽게 한다.
import { applyFrame } from "./state";
import type { EndReason, Seat, ServerFrame, SlotPhase, StateSnapshot } from "./types";

export type PanelTab = "decisions" | "materials" | "assistant" | "proposal";

/** ack 전(sent=false)·ack 뒤 message.new 전(messageId 있음) 내 메시지 */
export type Pending = { clientMsgId: string; content: string; tMin: number; messageId?: string };

export type View = {
  snap: StateSnapshot;
  pending: Pending[];
  /** 자리별 typing start를 받은 시각(ms). 30초 안에 stop이 없으면 끈다 */
  typingSince: Partial<Record<Seat, number>>;
  /** phase_remaining_seconds를 받은 시각(ms). 로컬 카운트다운 기준 */
  receivedAt: number;
  tab: PanelTab;
  badges: { decisions: number; materials: number };
  /** 방금 확정된 항목(결과 줄 짧은 강조) */
  flash: SlotPhase | null;
  ended: EndReason | null;
  replaced: boolean;
  needsResync: boolean;
};

export type Action =
  | { type: "snapshot"; snap: StateSnapshot; now: number }
  | { type: "frame"; frame: ServerFrame; now: number }
  | { type: "send"; pending: Pending }
  | { type: "tick"; now: number }
  | { type: "tab"; tab: PanelTab }
  | { type: "ended"; reason: EndReason };

export const TYPING_TIMEOUT_MS = 30_000;

function endedFrom(snap: StateSnapshot): EndReason | null {
  const status = snap.session.status;
  if (status === "failed" || status === "cancelled") return status;
  if (status === "invited" || status === "in_progress") return null;
  return "submitted";
}

export function initialView(snap: StateSnapshot, now = 0): View {
  return {
    snap,
    pending: [],
    typingSince: Object.fromEntries(snap.typing.map((seat) => [seat, now])),
    receivedAt: now,
    tab: snap.session.phase === "proposal" ? "proposal" : "decisions",
    badges: { decisions: 0, materials: 0 },
    flash: null,
    ended: endedFrom(snap),
    replaced: false,
    needsResync: false,
  };
}

function onFrame(view: View, frame: ServerFrame, now: number): View {
  if (view.replaced) return view;
  if (frame.type === "session.replaced") return { ...view, replaced: true };
  if (view.needsResync) return view;
  // 이미 반영한 프레임(스냅샷 ws_seq 이하)은 버린다. 앞 번호가 빠졌으면 /state로 다시 맞춘다
  if (frame.seq <= view.snap.ws_seq) return view;
  if (frame.seq !== view.snap.ws_seq + 1) return { ...view, needsResync: true };

  const snap = applyFrame(view.snap, frame);
  const next: View = { ...view, snap };
  switch (frame.type) {
    case "message.ack":
      next.pending = view.pending.map((p) =>
        p.clientMsgId === frame.payload.client_msg_id
          ? { ...p, messageId: frame.payload.message_id }
          : p,
      );
      break;
    case "message.new": {
      next.pending = view.pending.filter((p) => p.messageId !== frame.payload.id);
      const sender = frame.payload.sender;
      if (sender !== "candidate" && sender !== "system") {
        const typing = { ...view.typingSince };
        delete typing[sender];
        next.typingSince = typing;
      }
      break;
    }
    case "typing": {
      const typing = { ...view.typingSince };
      if (frame.payload.state === "start") typing[frame.payload.participant] = now;
      else delete typing[frame.payload.participant];
      next.typingSince = typing;
      break;
    }
    case "slot.confirmed":
      next.flash = frame.payload.phase;
      if (view.tab !== "decisions")
        next.badges = { ...view.badges, decisions: view.badges.decisions + 1 };
      break;
    case "phase.changed":
      // 기획안 단계가 되면 우측 탭을 기획안으로(UX 결정 5)
      if (frame.payload.phase === "proposal") next.tab = "proposal";
      break;
    case "timer":
      next.receivedAt = now;
      break;
    case "materials.opened":
      if (view.tab !== "materials")
        next.badges = { ...view.badges, materials: view.badges.materials + 1 };
      break;
    case "session.ended":
      next.ended = frame.payload.reason;
      next.typingSince = {};
      break;
  }
  return next;
}

export function reduce(view: View, action: Action): View {
  switch (action.type) {
    case "snapshot": {
      const ids = new Set(action.snap.messages.map((m) => m.id));
      return {
        ...view,
        snap: action.snap,
        pending: view.pending.filter((p) => !p.messageId || !ids.has(p.messageId)),
        typingSince: Object.fromEntries(
          action.snap.typing.map((seat) => [seat, view.typingSince[seat] ?? action.now]),
        ),
        receivedAt: action.now,
        tab:
          action.snap.session.phase === "proposal" && view.snap.session.phase !== "proposal"
            ? "proposal"
            : view.tab,
        ended: view.ended ?? endedFrom(action.snap),
        needsResync: false,
      };
    }
    case "frame":
      return onFrame(view, action.frame, action.now);
    case "send":
      return { ...view, pending: [...view.pending, action.pending] };
    case "tick": {
      const stale = (Object.entries(view.typingSince) as [Seat, number][]).filter(
        ([, since]) => action.now - since >= TYPING_TIMEOUT_MS,
      );
      if (stale.length === 0) return view;
      const typingSince = { ...view.typingSince };
      const off = new Set(stale.map(([seat]) => seat));
      for (const seat of off) delete typingSince[seat];
      return {
        ...view,
        typingSince,
        snap: { ...view.snap, typing: view.snap.typing.filter((s) => !off.has(s)) },
      };
    }
    case "tab":
      return {
        ...view,
        tab: action.tab,
        badges: {
          decisions: action.tab === "decisions" ? 0 : view.badges.decisions,
          materials: action.tab === "materials" ? 0 : view.badges.materials,
        },
      };
    case "ended":
      return { ...view, ended: view.ended ?? action.reason };
  }
}

/** 지금 입력 중으로 보일 AI 자리(30초 안전장치 반영) */
export function typingSeats(view: View): Seat[] {
  return (Object.keys(view.typingSince) as Seat[]).sort();
}

/** 지금 이 단계에 남은 초(로컬 카운트다운) */
export function phaseRemaining(view: View, now: number) {
  const base = view.snap.session.phase_remaining_seconds;
  if (base === null) return null;
  return Math.max(0, base - (now - view.receivedAt) / 1000);
}
