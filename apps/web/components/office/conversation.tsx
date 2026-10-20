"use client";

// 가운데 "대화" 상태: 채널 머리(누가 보는가), 메시지 줄, 시스템 줄, 문서 카드, 입력창.
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";

import { Avatar, AvatarGroup, Button, Chip, cn, initial, partTone } from "@/components/ui";

import { clock, givenName, partLabel, personName, type SysLine } from "./lines";
import type { Pending, TimelineItem } from "./reducer";
import type { Channel, DocRef, Message, Sender, StateSnapshot } from "./types";

export const CHANNEL_NAMES: Record<Channel, string> = {
  team: "# 재참여-기획",
  dm: "이도현",
  manager_dm: "한서윤 팀장",
  notice: "알림",
};

export function channelName(channel: Channel, persona: StateSnapshot["persona"]) {
  if (channel === "dm") return persona.colleague;
  if (channel === "manager_dm") return persona.manager;
  return CHANNEL_NAMES[channel];
}

const TONE: Record<Sender, "manager" | "colleague" | "candidate" | "system"> = {
  manager: "manager",
  colleague: "colleague",
  candidate: "candidate",
  system: "system",
};

export function senderAvatar(sender: Sender, persona: StateSnapshot["persona"], alias: string) {
  const name = personName(sender, persona, alias);
  const label =
    sender === "candidate" ? initial(alias) : sender === "system" ? "R" : initial(givenName(name));
  return { label, tone: TONE[sender], name };
}

export function ChannelHeader({
  channel,
  snap,
  alias,
  onHelp,
}: {
  channel: Channel;
  snap: StateSnapshot;
  alias: string;
  onHelp: () => void;
}) {
  const members = snap.channels[channel]?.members ?? [];
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-5">
      <h2 className="min-w-0 truncate text-lg font-semibold">
        {channelName(channel, snap.persona)}
      </h2>
      {channel === "notice" ? (
        <span className="shrink-0 text-sm text-muted">나만 받는 알림</span>
      ) : (
        <span className="shrink-0 text-sm text-muted">{members.length}명</span>
      )}
      <AvatarGroup
        className="shrink-0"
        people={members.map((m) => ({ ...senderAvatar(m, snap.persona, alias), online: true }))}
      />
      <button
        type="button"
        onClick={onHelp}
        aria-label="화면 설명 다시 보기"
        className="press ml-auto flex size-8 shrink-0 items-center justify-center rounded-full border border-line text-sm font-semibold text-muted hover:bg-surface-sunken"
      >
        ?
      </button>
    </header>
  );
}

export function SystemLineRow({ line, fresh }: { line: SysLine; fresh?: boolean }) {
  const tone = line.kind === "deadline" ? "text-warning" : "text-muted";
  return (
    <div className={cn("flex items-center gap-2 py-1 pl-12 text-sm", fresh && "arrive", tone)}>
      <span aria-hidden className="h-px w-3 shrink-0 bg-line" />
      <span className="min-w-0">{line.text}</span>
    </div>
  );
}

export type DocCardInfo = {
  part_no: number;
  title: string;
  owner: string;
  version: number;
  latest: boolean;
  opened?: boolean;
};

export function DocCard({
  info,
  onOpen,
  small,
}: {
  info: DocCardInfo;
  onOpen: () => void;
  /** 묶음(2열) 안의 작은 카드: 아이콘을 줄이고 "열기" 글자를 뺀다(카드 전체가 누르는 곳) */
  small?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={small ? `${info.part_no}. ${info.title} v${info.version} 열기` : undefined}
      className={cn(
        "press flex w-full items-center rounded-md border border-line bg-surface text-left transition-colors hover:border-accent/40 hover:bg-accent-soft/40",
        small ? "gap-2 px-2.5 py-2" : "gap-3 px-3 py-2.5",
      )}
    >
      <span
        className={cn(
          "flex shrink-0 items-center justify-center rounded-md bg-surface-sunken text-muted",
          small ? "size-6" : "size-8",
        )}
      >
        <svg viewBox="0 0 16 16" className="size-4" aria-hidden>
          <path
            d="M4 1.5h5l3 3V14a.5.5 0 0 1-.5.5h-7.5A.5.5 0 0 1 3.5 14V2a.5.5 0 0 1 .5-.5z"
            fill="none"
            stroke="currentColor"
          />
          <path d="M9 1.5V5h3" fill="none" stroke="currentColor" />
        </svg>
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="flex min-w-0 items-center gap-1.5">
          <Chip tone={partTone(info.part_no)}>{info.part_no}</Chip>
          <span className="min-w-0 truncate font-medium">{info.title}</span>
        </span>
        <span className="text-xs text-subtle">
          {info.owner} · v{info.version}
          {!info.latest && " · 이전 버전"}
          {info.opened && " · 열어 봄"}
        </span>
      </span>
      {!small && <span className="shrink-0 text-sm font-medium text-accent">열기</span>}
    </button>
  );
}

function ReplyRef({ target, label }: { target: DocRef; label: string }) {
  return (
    <span className="mb-0.5 inline-flex items-center gap-1 text-xs text-muted">
      <span aria-hidden>↩</span>
      {label} v{target.version}에 대한 답
    </span>
  );
}

export function MessageRow({
  message,
  snap,
  alias,
  compact,
  fresh,
  docInfo,
  docLabel,
  onOpenDoc,
}: {
  message: Message;
  /** 화면을 연 뒤 도착한 메시지만 페이드 */
  fresh?: boolean;
  snap: StateSnapshot;
  alias: string;
  /** 같은 사람이 이어 보내면 아바타·이름 생략 */
  compact: boolean;
  docInfo?: DocCardInfo | null;
  docLabel: (ref: DocRef) => string;
  onOpenDoc: (ref: DocRef) => void;
}) {
  const notice = message.channel === "notice";
  const avatar = notice
    ? { label: "R", tone: "system" as const, name: "리서치 담당" }
    : senderAvatar(message.sender, snap.persona, alias);
  return (
    <div className={cn("flex gap-3 px-5", fresh && "arrive", compact ? "pt-0.5" : "pt-3")}>
      <div className="w-9 shrink-0">{!compact && <Avatar {...avatar} size={36} />}</div>
      <div className="min-w-0 flex-1">
        {!compact && (
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-semibold">{avatar.name}</span>
            {notice && <span className="text-xs text-muted">→ 나에게만</span>}
            <span className="text-xs text-subtle tabular-nums">{clock(message.t_min)}</span>
          </div>
        )}
        {message.reply_to_doc && (
          <ReplyRef target={message.reply_to_doc} label={docLabel(message.reply_to_doc)} />
        )}
        <p className="text-base break-words whitespace-pre-wrap">{message.content}</p>
        {message.shared_doc && docInfo && (
          <div className="mt-1.5 max-w-md">
            <DocCard info={docInfo} onOpen={() => onOpenDoc(message.shared_doc!)} />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * 문서 카드 메시지 행. 같은 사람이 같은 분에 보낸 카드가 이어지면 머리 한 번, 한마디는 줄마다, 카드는 작게 2열(UI/UX R3).
 * 카드 한 장일 때부터 이 행으로 그려, 두 번째 카드가 와도 첫 카드 DOM·포커스가 그대로 남는다(key = 첫 메시지 id).
 */
function DocGroupRow({
  messages,
  seen,
  snap,
  alias,
  docInfo,
  docLabel,
  onOpenDoc,
}: {
  messages: Message[];
  seen: Set<string>;
  snap: StateSnapshot;
  alias: string;
  docInfo: (ref: DocRef) => DocCardInfo | null;
  docLabel: (ref: DocRef) => string;
  onOpenDoc: (ref: DocRef) => void;
}) {
  const first = messages[0];
  const avatar = senderAvatar(first.sender, snap.persona, alias);
  const many = messages.length > 1;
  // 화면을 연 뒤 온 행은 통째로, 묶음에 뒤늦게 붙은 줄·카드는 그것만 페이드(클래스가 그대로라 다시 재생되지 않는다)
  const fresh = (m: Message) => m !== first && !seen.has(m.id) && "arrive";
  return (
    <div className={cn("flex gap-3 px-5 pt-3", !seen.has(first.id) && "arrive")}>
      <div className="w-9 shrink-0">
        <Avatar {...avatar} size={36} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-semibold">{avatar.name}</span>
          <span className="text-xs text-subtle tabular-nums">{clock(first.t_min)}</span>
        </div>
        {messages.map((m) => (
          <div key={m.id} className={cn(fresh(m))}>
            {m.reply_to_doc && (
              <ReplyRef target={m.reply_to_doc} label={docLabel(m.reply_to_doc)} />
            )}
            {m.content && <p className="text-base break-words whitespace-pre-wrap">{m.content}</p>}
          </div>
        ))}
        <div className={cn("mt-1.5 grid gap-2", many ? "max-w-2xl grid-cols-2" : "max-w-md")}>
          {messages.map((m) => {
            const info = docInfo(m.shared_doc!);
            return (
              info && (
                <div key={m.id} className={cn("min-w-0", fresh(m))}>
                  <DocCard small={many} info={info} onOpen={() => onOpenDoc(m.shared_doc!)} />
                </div>
              )
            );
          })}
        </div>
      </div>
    </div>
  );
}

function PendingRow({
  pending,
  offline,
  docLabel,
}: {
  pending: Pending;
  offline?: boolean;
  docLabel: (ref: DocRef) => string;
}) {
  return (
    <div className="flex gap-3 px-5 pt-0.5 opacity-60">
      <div className="w-9 shrink-0" />
      <div className="min-w-0 flex-1">
        {pending.reply_to_doc && (
          <ReplyRef target={pending.reply_to_doc} label={docLabel(pending.reply_to_doc)} />
        )}
        <p className="text-base break-words whitespace-pre-wrap">{pending.content}</p>
        <span className="text-xs text-subtle">{offline ? "연결되면 전송" : "보내는 중…"}</span>
      </div>
    </div>
  );
}

function itemKey(item: TimelineItem) {
  if (item.kind === "line") return `l-${item.line.id}`;
  if (item.kind === "pending") return `p-${item.pending.client_msg_id}`;
  return item.message.id;
}

export function Timeline({
  items,
  snap,
  alias,
  docInfo,
  docLabel,
  onOpenDoc,
  offline,
}: {
  items: TimelineItem[];
  offline?: boolean;
  snap: StateSnapshot;
  alias: string;
  docInfo: (ref: DocRef) => DocCardInfo | null;
  docLabel: (ref: DocRef) => string;
  onOpenDoc: (ref: DocRef) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  // 마운트 때 이미 있던 줄은 애니메이션 없이 그린다(Timeline은 채널마다 새로 마운트된다)
  const [seen] = useState(() => new Set(items.map(itemKey)));
  // 사용자가 맨 아래에 있을 때만 새 메시지로 따라 내려간다. 마감·제출 줄은 놓치면 안 되므로 항상 내려간다
  const last = items.at(-1);
  const urgent =
    last?.kind === "line" && (last.line.kind === "deadline" || last.line.kind === "submitted");
  // 문서 카드 메시지는 한 장이어도 묶음 행으로 그리고, 같은 사람·같은 분(시계 표시 기준)이 이어지면 그 행에 붙인다. 표시만 바꾸고 메시지는 그대로다
  const groups = new Map<number, Message[]>();
  const grouped = new Set<number>();
  items.forEach((item, i) => {
    // 알림 채널은 "나에게만" 머리가 따로라 MessageRow로 둔다
    if (
      grouped.has(i) ||
      item.kind !== "message" ||
      !item.message.shared_doc ||
      item.message.channel === "notice"
    )
      return;
    const run = [item.message];
    for (let j = i + 1; j < items.length; j++) {
      const next = items[j];
      if (
        next.kind !== "message" ||
        !next.message.shared_doc ||
        next.message.sender !== item.message.sender ||
        clock(next.message.t_min) !== clock(item.message.t_min)
      )
        break;
      run.push(next.message);
      grouped.add(j);
    }
    groups.set(i, run);
  });
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && (atBottom.current || urgent)) el.scrollTop = el.scrollHeight;
  }, [items.length, urgent]);
  return (
    <div
      ref={scroller}
      onScroll={(event) => {
        const el = event.currentTarget;
        atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
      }}
      className="min-h-0 flex-1 overflow-y-auto pb-4"
    >
      {items.length === 0 && (
        <p className="px-5 py-10 text-center text-sm text-muted">아직 대화 없음</p>
      )}
      {items.map((item, i) => {
        if (grouped.has(i)) return null;
        const group = groups.get(i);
        if (group) {
          return (
            <DocGroupRow
              key={group[0].id}
              messages={group}
              seen={seen}
              snap={snap}
              alias={alias}
              docInfo={docInfo}
              docLabel={docLabel}
              onOpenDoc={onOpenDoc}
            />
          );
        }
        if (item.kind === "line") {
          return (
            <SystemLineRow key={itemKey(item)} line={item.line} fresh={!seen.has(itemKey(item))} />
          );
        }
        if (item.kind === "pending") {
          return (
            <PendingRow
              key={item.pending.client_msg_id}
              pending={item.pending}
              offline={offline}
              docLabel={docLabel}
            />
          );
        }
        const prev = items[i - 1];
        const compact =
          prev?.kind === "message" &&
          prev.message.sender === item.message.sender &&
          !item.message.shared_doc &&
          item.message.t_min - prev.message.t_min < 3;
        return (
          <MessageRow
            key={item.message.id}
            message={item.message}
            snap={snap}
            alias={alias}
            compact={compact}
            fresh={!seen.has(itemKey(item))}
            docInfo={item.message.shared_doc ? docInfo(item.message.shared_doc) : null}
            docLabel={docLabel}
            onOpenDoc={onOpenDoc}
          />
        );
      })}
    </div>
  );
}

export function Composer({
  channel,
  placeholder,
  replyTo,
  replyLabel,
  disabled,
  offline,
  onClearReply,
  onSend,
  focusKey,
}: {
  channel: Channel;
  placeholder: string;
  replyTo: DocRef | null;
  replyLabel: string;
  disabled?: boolean;
  /** 연결이 끊긴 동안: 입력은 받고 연결되면 보낸다 */
  offline?: boolean;
  onClearReply: () => void;
  onSend: (text: string) => void;
  /** 바뀌면 입력창에 포커스(답글 쓰기) */
  focusKey?: number;
}) {
  const [drafts, setDrafts] = useState<Partial<Record<Channel, string>>>({});
  const area = useRef<HTMLTextAreaElement>(null);
  const text = drafts[channel] ?? "";
  useEffect(() => {
    if (focusKey) area.current?.focus();
  }, [focusKey]);

  const send = () => {
    const value = text.trim();
    if (!value || disabled) return;
    onSend(value);
    setDrafts((d) => ({ ...d, [channel]: "" }));
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  };
  return (
    <div className="shrink-0 px-5 pb-4">
      <div className="rounded-lg border border-line bg-surface focus-within:border-accent/60">
        {replyTo && (
          <div className="flex items-center gap-2 border-b border-line px-3 py-1.5">
            <Chip tone="accent">
              ↩ {replyLabel} v{replyTo.version}에 답
            </Chip>
            <button
              type="button"
              onClick={onClearReply}
              aria-label="답글 참조 지우기"
              className="ml-auto text-sm text-subtle hover:text-ink"
            >
              ✕
            </button>
          </div>
        )}
        <div className="flex items-end gap-2 p-2">
          <textarea
            ref={area}
            rows={1}
            value={text}
            disabled={disabled}
            placeholder={placeholder}
            onChange={(event) => setDrafts((d) => ({ ...d, [channel]: event.target.value }))}
            onKeyDown={onKeyDown}
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-1.5 py-1.5 text-base outline-none placeholder:text-subtle field-sizing-content"
          />
          <Button size="sm" disabled={disabled || !text.trim()} onClick={send}>
            보내기
          </Button>
        </div>
      </div>
      <p className="mt-1 px-1 text-xs text-subtle">
        {offline ? "연결 끊김 · 연결되면 전송" : "Enter 보내기 · Shift+Enter 줄바꿈"}
      </p>
    </div>
  );
}

export { partLabel };
