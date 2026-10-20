"use client";

// 왼쪽 채널 목록(안 읽음 배지)과 가운데 대화·입력. 보낸 메시지는 ack 전까지 "보내는 중"으로 둔다.
import { useState } from "react";

import { Button, cn } from "@/components/ui";

import { progressLabels, type ChatChannel, type OfficeState } from "./reducer";
import type { Message } from "./types";

export function channelLabel(state: OfficeState, channel: ChatChannel) {
  return channel === "team" ? "팀 채널" : state.persona.colleague;
}

export function ChannelList({
  state,
  onView,
}: {
  state: OfficeState;
  onView: (channel: ChatChannel) => void;
}) {
  return (
    <nav aria-label="채널" className="flex flex-col gap-1 p-3">
      <p className="px-2 pb-1 text-xs font-medium text-subtle">채널</p>
      {(["team", "dm"] as const).map((channel) => (
        <button
          key={channel}
          type="button"
          aria-current={state.channel === channel || undefined}
          onClick={() => onView(channel)}
          className={cn(
            "flex items-center justify-between rounded-md px-2 py-1.5 text-left text-sm",
            state.channel === channel
              ? "bg-accent-soft text-accent-strong"
              : "hover:bg-surface-sunken",
          )}
        >
          <span>
            {channel === "team" ? "# " : "@ "}
            {channelLabel(state, channel)}
          </span>
          {state.unread[channel] > 0 && (
            <span
              aria-label={`안 읽은 메시지 ${state.unread[channel]}개`}
              className="rounded-sm bg-accent px-1.5 text-xs text-white"
            >
              {state.unread[channel]}
            </span>
          )}
        </button>
      ))}
    </nav>
  );
}

function senderName(state: OfficeState, message: Pick<Message, "sender">) {
  if (message.sender === "candidate") return "나";
  if (message.sender === "manager") return state.persona.manager;
  if (message.sender === "colleague") return state.persona.colleague;
  return "알림";
}

export function ChatPane({
  state,
  disabled,
  onSend,
}: {
  state: OfficeState;
  disabled?: boolean;
  onSend: (channel: ChatChannel, content: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const channel = state.channel;
  const messages = state.messages.filter((m) => m.channel === channel);
  const outgoing = state.outgoing.filter((o) => o.channel === channel);
  const typing = progressLabels(state, channel);

  const send = () => {
    const content = draft.trim();
    if (!content || disabled) return;
    onSend(channel, content);
    setDraft("");
  };

  return (
    <section aria-label={channelLabel(state, channel)} className="flex min-h-0 flex-1 flex-col">
      <header className="border-b border-line px-5 py-3 font-medium">
        {channel === "team" ? "# " : "@ "}
        {channelLabel(state, channel)}
      </header>
      <ol className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
        {messages.map((message) => (
          <li key={message.id} className="flex flex-col gap-0.5">
            <span className="text-xs font-medium text-muted">{senderName(state, message)}</span>
            <p className="whitespace-pre-wrap">{message.content}</p>
          </li>
        ))}
        {outgoing.map((out) => (
          <li key={out.client_msg_id} className="flex flex-col gap-0.5">
            <span className="text-xs font-medium text-muted">
              나 · {out.failed ? "보내지 못함" : out.message_id ? "전송됨" : "보내는 중…"}
            </span>
            <p className={cn("whitespace-pre-wrap", !out.message_id && "text-subtle")}>
              {out.content}
            </p>
          </li>
        ))}
      </ol>
      <p aria-live="polite" className="h-5 px-5 text-xs text-muted">
        {typing.join(" · ")}
      </p>
      <form
        className="flex gap-2 border-t border-line p-3"
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
      >
        <textarea
          aria-label="메시지 입력"
          value={draft}
          rows={2}
          disabled={disabled}
          placeholder={`${channelLabel(state, channel)}에 메시지 보내기`}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              send();
            }
          }}
          className="min-h-0 flex-1 resize-none rounded-md border border-line bg-surface px-3 py-2"
        />
        <Button type="submit" disabled={disabled || !draft.trim()}>
          보내기
        </Button>
      </form>
    </section>
  );
}
