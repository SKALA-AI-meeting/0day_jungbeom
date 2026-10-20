"use client";

// 가상 오피스 화면. 상단(회사명·남은 시간·제출) · 좌 채널 · 중 대화 · 우 탭 4개.
// 상태는 reducer.ts의 OfficeState, 서버 호출은 candidate-flow.tsx가 넘긴 콜백만 쓴다.
import { useState } from "react";

import { Button, ConfirmDialog, Tabs } from "@/components/ui";
import type { ConnectionStatus } from "@/lib/ws";

import { AssistantPanel } from "./assistant-panel";
import { ChannelList, ChatPane } from "./chat";
import { CompanyDocs, type OpenDoc } from "./company-docs";
import { PlanDoc } from "./plan-doc";
import { formatRemaining, type ChatChannel, type OfficeState } from "./reducer";
import { TaskBoard } from "./task-board";
import type { TaskStatus } from "./types";

const WARN_MS = 10 * 60_000;

export type OfficeViewProps = {
  state: OfficeState;
  companyName: string;
  now: number;
  connection: ConnectionStatus;
  submitting?: boolean;
  /** 제출(저장 포함) 실패 안내. 확인 창 안에 보이고 다시 제출할 수 있다 */
  submitError?: string | null;
  assistantError?: string | null;
  onView: (channel: ChatChannel) => void;
  onSend: (channel: ChatChannel, content: string) => void;
  onEdit: (partNo: number, content: string) => void;
  onRetrySave: (partNo: number) => void;
  onTask: (partNo: number, status: TaskStatus) => void;
  onOpenDoc: OpenDoc;
  onAsk: (prompt: string) => void;
  onSubmit: () => void;
  onDismissNotice: (id: string) => void;
};

export function Timer({ deadline, now }: { deadline: number | null; now: number }) {
  if (deadline === null) return null;
  const left = deadline - now;
  return (
    <span
      role="timer"
      aria-label="남은 시간"
      className={left <= WARN_MS ? "font-mono text-warning" : "font-mono text-muted"}
    >
      {formatRemaining(left)}
    </span>
  );
}

function ConnectionBar({ connection }: { connection: ConnectionStatus }) {
  if (connection === "reconnecting") {
    return (
      <p role="status" className="bg-warning-soft px-4 py-1.5 text-center text-sm text-warning">
        연결이 끊겼어요. 다시 연결하는 중…
      </p>
    );
  }
  return null;
}

function Blocker({ title, description }: { title: string; description: string }) {
  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/30 p-6">
      <div role="alertdialog" className="max-w-sm rounded-lg bg-surface p-6 shadow-lg">
        <p className="text-lg font-semibold">{title}</p>
        <p className="mt-2 text-muted">{description}</p>
      </div>
    </div>
  );
}

export function OfficeView(props: OfficeViewProps) {
  const { state, companyName, now, connection } = props;
  const [confirming, setConfirming] = useState(false);
  const ended = state.ended !== null;
  const notices = state.notices
    .map((id) => state.messages.find((m) => m.id === id))
    .filter((m) => m !== undefined);

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-line bg-surface px-5 py-2.5">
        <span className="font-semibold">{companyName}</span>
        <div className="flex items-center gap-4">
          <Timer deadline={state.deadline} now={now} />
          <Button size="sm" disabled={ended} onClick={() => setConfirming(true)}>
            제출
          </Button>
        </div>
      </header>
      {notices.map((notice) => (
        <div
          key={notice.id}
          role="alert"
          className="flex items-center justify-between gap-3 border-b border-line bg-accent-soft px-5 py-2 text-sm"
        >
          <span>{notice.content}</span>
          <button
            type="button"
            className="text-muted hover:text-ink"
            aria-label="알림 닫기"
            onClick={() => props.onDismissNotice(notice.id)}
          >
            닫기
          </button>
        </div>
      ))}
      <ConnectionBar connection={connection} />
      <div className="grid min-h-0 flex-1 grid-cols-[13rem_minmax(0,1fr)_minmax(22rem,30rem)]">
        <aside className="border-r border-line bg-surface">
          <ChannelList state={state} onView={props.onView} />
        </aside>
        <main className="flex min-h-0 flex-col bg-canvas">
          <ChatPane state={state} disabled={ended} onSend={props.onSend} />
        </main>
        <aside className="flex min-h-0 flex-col border-l border-line bg-surface">
          <Tabs
            className="min-h-0 flex-1"
            items={[
              {
                value: "doc",
                label: "기획안 문서",
                content: (
                  <PlanDoc
                    state={state}
                    disabled={ended}
                    onEdit={props.onEdit}
                    onRetry={props.onRetrySave}
                  />
                ),
              },
              {
                value: "board",
                label: "태스크 보드",
                content: <TaskBoard state={state} disabled={ended} onTask={props.onTask} />,
              },
              {
                value: "docs",
                label: "회사 문서",
                count: state.fresh.length,
                content: <CompanyDocs state={state} onOpen={props.onOpenDoc} />,
              },
              {
                value: "assistant",
                label: "AI 어시스턴트",
                content: (
                  <AssistantPanel
                    state={state}
                    disabled={ended}
                    error={props.assistantError}
                    onAsk={props.onAsk}
                  />
                ),
              },
            ]}
          />
        </aside>
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="제출할까요?"
        description={
          <>
            제출하면 세션이 끝납니다. 작성 중인 문서는 저장한 뒤 제출해요.
            {props.submitError && (
              <span role="alert" className="mt-2 block text-danger">
                {props.submitError}
              </span>
            )}
          </>
        }
        confirmLabel="제출"
        tone="danger"
        pending={props.submitting}
        onConfirm={props.onSubmit}
      />
      {(state.replaced || connection === "replaced") && (
        <Blocker
          title="다른 창에서 접속했어요"
          description="이 창은 멈췄어요. 새로 연 창에서 이어서 진행해 주세요."
        />
      )}
      {connection === "forbidden" && (
        <Blocker
          title="이 링크로는 접속할 수 없어요"
          description="받은 주소를 다시 확인해 주세요."
        />
      )}
    </div>
  );
}
