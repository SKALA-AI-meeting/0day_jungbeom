"use client";

// 가상 오피스 화면: 레일(채널·남은 시간) / 메인 탭(대화·내 문서·보드·자료·어시스턴트, CX-08).
// 대화 탭 안에서 받은 문서를 대화 위로 열고 닫는다. 작은 화면에서는 레일이 위쪽 가로 줄이 된다.
// 상태는 reducer(OfficeState)가 들고, 서버 호출은 candidate-flow의 OfficeContainer가 한다. 여기는 화면 상태만 가진다.
import { Dialog } from "@base-ui/react/dialog";
import { useEffect, useImperativeHandle, useState, type ReactNode, type Ref } from "react";

import { Button, ConfirmDialog, cn } from "@/components/ui";

import { AssistantPanel } from "./assistant-panel";
import { Board, type MovePatch } from "./board";
import {
  ChannelHeader,
  channelName,
  Composer,
  HelpButton,
  Timeline,
  type DocCardInfo,
} from "./conversation";
import { DocViewer, type OpenDoc } from "./doc-viewer";
import { HelpContent } from "./link-screens";
import { countdown, givenName, partLabel, remainText } from "./lines";
import { DocEditor, DocList, FinalDoc, type DocTarget, type SaveState } from "./my-docs";
import { Library } from "./library";
import { MainTabBar, TabPanel, type MainTab } from "./main-tabs";
import {
  locked as isLocked,
  nowMin,
  partTitles,
  progressLabels,
  timeline,
  type OfficeState,
} from "./reducer";
import { chatBadge, othersCount, showChannel } from "./screen";
import type { Channel, DocRef, Task } from "./types";

export const SESSION_MINUTES = 120;

export type OfficeHandlers = {
  onView: (channel: Channel) => void;
  onSend: (channel: "team" | "dm" | "manager_dm", content: string, reply?: DocRef) => void;
  /** 받은 문서 버전을 연다(열람 기록). 본문을 돌려준다 */
  onOpenDoc: (ref: DocRef) => Promise<string>;
  /** version null = 보내지 않은 내 문서의 현재 저장본 */
  onImport: (
    partNo: number,
    source: { source_doc_id: string; version: number | null },
  ) => Promise<void>;
  onEditDoc: (partNo: number, content: string) => void;
  onShare: (partNo: number, channel: "team" | "dm", note: string) => void;
  onEditFinal: (partNo: number, content: string) => void;
  onSubmit: () => void;
  onTask: (partNo: number, patch: Partial<Task>) => void;
  onMove: (patches: MovePatch[]) => void;
  onReadCompany: (docId: string) => Promise<string>;
  onAsk: (prompt: string) => void;
  /** 대화 밖 작업 탭을 보는 중인지·대화 위에 문서가 열렸는지(새 메시지 토스트 판정) */
  onEditingChange: (value: { editing: boolean; docOpen: boolean }) => void;
};

/** 화면 밖(토스트 "보기")에서 채널 대화로 옮길 때 쓰는 손잡이 */
export type OfficeHandle = { showChannel: (channel: Channel) => void };

export type OfficeViewProps = OfficeHandlers & {
  ref?: Ref<OfficeHandle>;
  state: OfficeState;
  alias: string;
  now: number;
  connection: "open" | "connecting" | "reconnecting" | "replaced" | "forbidden" | "closed";
  saves: Record<string, SaveState>;
  taskErrors: Record<number, string>;
  assistantPending: string | null;
  assistantError: string | null;
  submitting: boolean;
  /** mock 조작 패널 자리(개발용) */
  devSlot?: ReactNode;
};

function RailItem({
  active,
  label,
  count,
  online,
  onClick,
}: {
  active: boolean;
  label: ReactNode;
  count?: number;
  online?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex shrink-0 items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-base whitespace-nowrap transition-colors md:w-full md:shrink",
        active
          ? "bg-surface font-semibold text-ink"
          : "text-muted hover:bg-surface/60 hover:text-ink",
      )}
    >
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {online && (
        <span className="size-2 shrink-0 rounded-full bg-success">
          <span className="sr-only">온라인</span>
        </span>
      )}
      {!!count && (
        <span className="shrink-0 rounded-sm bg-accent px-1.5 text-xs font-semibold text-white tabular-nums">
          <span aria-hidden>{count}</span>
          <span className="sr-only">새 메시지 {count}개</span>
        </span>
      )}
    </button>
  );
}

function Timer({ seconds }: { seconds: number | null }) {
  if (seconds == null) return null;
  const warn = seconds <= 600;
  return (
    <div
      className={cn(
        "flex shrink-0 items-baseline gap-2 rounded-md px-2.5 py-1.5 transition-colors duration-300 md:block md:py-2",
        warn ? "bg-warning-soft text-warning" : "text-muted",
      )}
    >
      <p className="text-xs">마감까지</p>
      <p className="font-semibold tabular-nums md:text-xl">{countdown(seconds)}</p>
    </div>
  );
}

export function OfficeView({ ref, ...props }: OfficeViewProps) {
  const { state, alias, now } = props;
  const { snap } = state;
  const [tab, setTab] = useState<MainTab>("chat");
  const [target, setTarget] = useState<DocTarget>(null);
  const [open, setOpen] = useState<OpenDoc | null>(null);
  const [replyTo, setReplyTo] = useState<DocRef | null>(null);
  const [focusKey, setFocusKey] = useState(0);
  const [help, setHelp] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [overwrite, setOverwrite] = useState<{
    part: number;
    source: { source_doc_id: string; version: number | null };
  } | null>(null);

  const titles = partTitles(snap);
  const locked = isLocked(state);
  const reporting = snap.session.status === "reporting";
  const ended = state.ended != null;
  const endsAt = snap.session.ends_at ? Date.parse(snap.session.ends_at) : null;
  const remaining = endsAt == null ? null : Math.max(0, Math.floor((endsAt - now) / 1000));
  const deadline = snap.session.deadline_at
    ? Math.max(0, Math.floor((Date.parse(snap.session.deadline_at) - now) / 1000))
    : null;
  const colleague = givenName(snap.persona.colleague);

  const channel = state.channel;
  // 채널이 바뀌면(레일·토스트의 "보기"·답글) 대화 탭으로 돌아온다
  const [shownChannel, setShownChannel] = useState(channel);
  if (channel !== shownChannel) {
    setShownChannel(channel);
    setTab("chat");
    setOpen(null);
  }
  // 작업 탭에 있는 동안 지금 채널에 온 메시지는 reducer의 안 읽음에 잡히지 않으므로 여기서 센다
  const others = othersCount(snap.messages, channel);
  const [seen, setSeen] = useState({ channel, count: others });
  if (tab === "chat" && (seen.channel !== channel || seen.count !== others)) {
    setSeen({ channel, count: others });
  }
  const hiddenNew =
    tab === "chat" || seen.channel !== channel ? 0 : Math.max(0, others - seen.count);
  const unreadOf = (ch: Channel) => state.unread[ch] + (ch === channel ? hiddenNew : 0);

  // [대화] 탭 배지: 작업 탭에 있는 동안 도착한 새 메시지(채널 구분 없음). 대화 탭으로 돌아오면 0
  const total = othersCount(snap.messages);
  const [seenTotal, setSeenTotal] = useState(total);
  if (tab === "chat" && seenTotal !== total) setSeenTotal(total);
  const chatCount = chatBadge(total, seenTotal, tab);

  // 대화가 안 보이는 동안(작업 탭) 새 메시지는 토스트로도 알린다
  const editing = tab !== "chat";
  const docOpen = open != null;
  const { onEditingChange } = props;
  useEffect(() => onEditingChange({ editing, docOpen }), [editing, docOpen, onEditingChange]);

  const view = (next: Channel) => {
    const screen = showChannel({ tab, open });
    setTab(screen.tab);
    setOpen(screen.open);
    props.onView(next);
  };
  useImperativeHandle(ref, () => ({ showChannel: view }));

  const docLabel = (ref: DocRef) => {
    const part =
      snap.received.find((d) => d.doc_id === ref.doc_id)?.part_no ??
      snap.my_documents.find((d) => d.doc_id === ref.doc_id)?.part_no;
    return part ? partLabel(part, titles) : "문서";
  };

  const docInfo = (ref: DocRef): DocCardInfo | null => {
    const theirs = snap.received.find((d) => d.doc_id === ref.doc_id);
    if (theirs) {
      return {
        part_no: theirs.part_no,
        title: theirs.title,
        owner: colleague,
        version: ref.version,
        latest: theirs.versions.at(-1)?.version === ref.version,
        opened: theirs.versions.find((v) => v.version === ref.version)?.opened,
      };
    }
    const mine = snap.my_documents.find((d) => d.doc_id === ref.doc_id);
    if (!mine) return null;
    return {
      part_no: mine.part_no,
      title: mine.title,
      owner: "나",
      version: ref.version,
      latest: mine.versions.at(-1)?.version === ref.version,
    };
  };

  const openDoc = async (ref: DocRef) => {
    const mine = snap.my_documents.find((d) => d.doc_id === ref.doc_id);
    if (mine) {
      // 내 문서 카드는 오른쪽 편집으로 연다
      setTab("docs");
      setTarget(mine.part_no);
      return;
    }
    const doc = snap.received.find((d) => d.doc_id === ref.doc_id);
    if (!doc) return;
    setOpen({ doc, version: ref.version, content: null });
    try {
      const content = await props.onOpenDoc(ref);
      setOpen((cur) =>
        cur?.doc.doc_id === doc.doc_id && cur.version === ref.version ? { ...cur, content } : cur,
      );
    } catch {
      setOpen((cur) =>
        cur ? { ...cur, error: "문서를 열지 못했어요. 잠시 후 다시 시도해 주세요." } : cur,
      );
    }
  };

  const reply = () => {
    if (!open) return;
    const version = open.doc.versions.find((v) => v.version === open.version);
    setReplyTo({ doc_id: open.doc.doc_id, version: open.version });
    view(version?.channel ?? "team");
    setFocusKey((k) => k + 1);
  };

  const importInto = (part: number, source: { source_doc_id: string; version: number | null }) => {
    const section = snap.final.sections.find((s) => s.part_no === part);
    // 덮어쓰기만 있으므로 내용이 있으면 먼저 확인받는다
    if (section?.content.trim()) setOverwrite({ part, source });
    else void props.onImport(part, source);
  };

  const items = timeline(state, channel);
  const progress = progressLabels(state);
  const stopped =
    state.replaced || props.connection === "replaced" || props.connection === "forbidden";
  const offline = !stopped && props.connection !== "open";
  const canWrite = channel !== "notice" && !ended && !stopped;
  const emptySections = snap.final.sections.filter((s) => !s.content.trim()).map((s) => s.part_no);
  // 마감 10분 전부터 가운데 위에 마감 배너(레일 타이머는 문서 편집 중 시선 밖이다)
  const closing = snap.session.status === "in_progress" && remaining != null && remaining <= 600;
  const writeChannel = channel === "notice" ? "team" : channel;

  const myDoc =
    typeof target === "number" ? snap.my_documents.find((d) => d.part_no === target) : null;

  return (
    // md 이상: 레일 232px + 메인. 그보다 좁으면 레일이 위쪽 가로 줄(가로 스크롤)이 되고 메인이 나머지를 쓴다
    <div className="grid h-dvh grid-rows-[auto_minmax(0,1fr)] overflow-hidden md:grid-cols-[232px_minmax(0,1fr)] md:grid-rows-1">
      <nav
        aria-label="채널"
        className="flex min-h-0 items-center gap-1 overflow-x-auto border-b border-line bg-surface-sunken px-2 py-2 md:flex-col md:items-stretch md:gap-4 md:overflow-x-visible md:border-b-0 md:px-3 md:py-4"
      >
        <div className="hidden px-2.5 md:block">
          <p className="text-lg font-semibold">루프랩</p>
          <p className="text-xs text-subtle">모아런 재참여 기획 · {alias}</p>
        </div>
        <div className="flex shrink-0 gap-0.5 md:flex-col">
          <p className="hidden px-2.5 pb-1 text-xs text-subtle md:block">채널</p>
          <RailItem
            active={tab === "chat" && channel === "team"}
            label="# 재참여-기획"
            count={unreadOf("team")}
            onClick={() => view("team")}
          />
        </div>
        <div className="flex shrink-0 gap-0.5 md:flex-col">
          <p className="hidden px-2.5 pb-1 text-xs text-subtle md:block">다이렉트 메시지</p>
          <RailItem
            active={tab === "chat" && channel === "dm"}
            label={snap.persona.colleague}
            online
            count={unreadOf("dm")}
            onClick={() => view("dm")}
          />
          <RailItem
            active={tab === "chat" && channel === "manager_dm"}
            label={snap.persona.manager}
            online
            count={unreadOf("manager_dm")}
            onClick={() => view("manager_dm")}
          />
        </div>
        <div className="flex shrink-0 gap-0.5 md:flex-col">
          <p className="hidden px-2.5 pb-1 text-xs text-subtle md:block">나에게만</p>
          <RailItem
            active={tab === "chat" && channel === "notice"}
            label="알림"
            count={unreadOf("notice")}
            onClick={() => view("notice")}
          />
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2 md:mt-auto md:ml-0 md:flex-col md:items-stretch">
          {props.devSlot}
        </div>
        {/* 좁은 화면에서는 가로 레일 맨 앞에 고정해 스크롤해도 남은 시간이 보이게 한다 */}
        <div className="sticky left-0 z-[1] order-first shrink-0 bg-surface-sunken md:static md:order-none">
          <Timer seconds={snap.session.status === "in_progress" ? remaining : null} />
        </div>
      </nav>

      <main className="flex min-h-0 min-w-0 flex-col bg-canvas">
        {offline && (
          <div
            role="status"
            className="flex shrink-0 items-center gap-2 border-b border-line bg-surface-sunken px-5 py-2.5 text-sm"
          >
            <b className="font-semibold">연결 끊김</b>
            <span className="text-muted">다시 연결 중 · 보낸 메시지는 연결되면 전송</span>
          </div>
        )}
        {closing && !reporting && (
          <div
            role="status"
            className="flex shrink-0 items-center gap-3 border-b border-warning/30 bg-warning-soft px-5 py-2.5 text-sm"
          >
            <b className="font-semibold">마감 {remainText(remaining!)} 전</b>
            <span className="text-muted">시간이 끝나면 지금 상태로 자동 제출</span>
          </div>
        )}
        {reporting && !ended && (
          <div
            role="status"
            className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-warning/30 bg-warning-soft px-5 py-2.5 text-sm"
          >
            <b className="font-semibold">보고 대기</b>
            <span className="tabular-nums">
              {deadline != null ? `${remainText(deadline)} 남음` : ""}
            </span>
            <span className="text-muted">팀 채널·팀장 DM에 짧게 보고 · 보고 없이도 제출 유효</span>
          </div>
        )}
        {ended && (
          <div
            role="status"
            className="shrink-0 border-b border-line bg-success-soft px-5 py-2.5 text-sm"
          >
            보고 완료 · 곧 마무리 안내로 이동
          </div>
        )}
        <MainTabBar
          value={tab}
          counts={{ chat: chatCount }}
          onChange={setTab}
          end={<HelpButton onClick={() => setHelp(true)} />}
        />
        <div className="relative min-h-0 flex-1">
          <TabPanel value="chat" active={tab === "chat"}>
            {/* 받은 문서가 대화를 덮는 동안 뒤의 대화·입력창은 포커스·입력을 막는다 */}
            <div inert={docOpen} className="flex min-h-0 flex-1 flex-col">
              <ChannelHeader channel={channel} snap={snap} alias={alias} />
              <Timeline
                key={channel}
                items={items}
                snap={snap}
                alias={alias}
                docInfo={docInfo}
                docLabel={docLabel}
                onOpenDoc={(ref) => void openDoc(ref)}
                offline={offline}
              />
              <p aria-live="polite" className="h-5 shrink-0 px-5 text-xs text-muted">
                {progress[0] ?? ""}
              </p>
              {canWrite ? (
                <Composer
                  channel={writeChannel}
                  placeholder={`${channelName(writeChannel, snap.persona)}에 메시지 보내기`}
                  offline={offline}
                  replyTo={replyTo}
                  replyLabel={replyTo ? docLabel(replyTo) : ""}
                  onClearReply={() => setReplyTo(null)}
                  focusKey={focusKey}
                  onSend={(text) => {
                    props.onSend(writeChannel, text, replyTo ?? undefined);
                    setReplyTo(null);
                  }}
                />
              ) : (
                <p className="shrink-0 px-5 pb-5 text-sm text-subtle">
                  {channel === "notice" ? "받기 전용 채널" : "세션 종료 · 메시지 전송 불가"}
                </p>
              )}
            </div>
            <DocViewer
              open={open}
              owner={colleague}
              sections={snap.final.sections}
              locked={locked}
              onVersion={(version) => open && void openDoc({ doc_id: open.doc.doc_id, version })}
              onReply={reply}
              onImport={(part) =>
                open && importInto(part, { source_doc_id: open.doc.doc_id, version: open.version })
              }
              onClose={() => setOpen(null)}
            />
          </TabPanel>

          {/* 문서 편집은 읽기 좋은 폭의 가운데 열로 둔다. 넓은 메인에서 줄이 지나치게 길어지지 않게 */}
          <TabPanel value="docs" active={tab === "docs"}>
            <div className="mx-auto flex h-full min-h-0 w-full max-w-[56rem] flex-col bg-surface md:border-x md:border-line">
              {target === "final" ? (
                <FinalDoc
                  snap={snap}
                  save={props.saves.final}
                  locked={locked}
                  remainingSeconds={remaining}
                  onBack={() => setTarget(null)}
                  onEdit={props.onEditFinal}
                  onImport={importInto}
                  onSubmit={() => setConfirm(true)}
                  onToLibrary={() => setTab("library")}
                />
              ) : myDoc ? (
                <DocEditor
                  doc={myDoc}
                  save={props.saves[String(myDoc.part_no)]}
                  locked={locked}
                  onBack={() => setTarget(null)}
                  onEdit={(content) => props.onEditDoc(myDoc.part_no, content)}
                  onShare={(ch, note) => props.onShare(myDoc.part_no, ch, note)}
                  onToLibrary={() => setTab("library")}
                />
              ) : (
                <div className="min-h-0 flex-1 overflow-y-auto">
                  <DocList snap={snap} onPick={setTarget} onBoard={() => setTab("board")} />
                </div>
              )}
            </div>
          </TabPanel>

          <TabPanel value="board" active={tab === "board"} className="overflow-y-auto">
            <Board
              snap={snap}
              titles={titles}
              nowMin={nowMin(snap, now)}
              sessionMinutes={SESSION_MINUTES}
              locked={locked}
              errors={props.taskErrors}
              onPatch={props.onTask}
              onMove={props.onMove}
            />
          </TabPanel>

          <TabPanel value="library" active={tab === "library"} className="overflow-y-auto">
            <Library
              documents={snap.documents}
              releasedLater={state.releasedLater}
              onRead={props.onReadCompany}
              onToDocs={() => setTab("docs")}
            />
          </TabPanel>

          <TabPanel value="assistant" active={tab === "assistant"}>
            <div className="mx-auto flex h-full min-h-0 w-full max-w-[56rem] flex-col bg-surface md:border-x md:border-line">
              <AssistantPanel
                calls={snap.assistant}
                documents={snap.documents}
                locked={locked}
                pending={props.assistantPending}
                error={props.assistantError}
                onAsk={props.onAsk}
              />
            </div>
          </TabPanel>
        </div>
      </main>

      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="최종본을 제출할까요?"
        description="제출 후 수정 불가. 팀장 보고 뒤 남은 시간과 상관없이 세션 종료."
        confirmLabel="제출"
        tone="danger"
        pending={props.submitting}
        onConfirm={() => {
          setConfirm(false);
          props.onSubmit();
        }}
      >
        {emptySections.length > 0 && (
          <p className="mt-2 text-sm">비어 있는 섹션: {emptySections.join("·")}번</p>
        )}
        {remaining != null && remaining <= 120 && (
          <p className="mt-2 text-sm text-warning">
            마감 {remainText(remaining)} 전 · 지금 상태 그대로 제출
          </p>
        )}
      </ConfirmDialog>

      <ConfirmDialog
        open={overwrite != null}
        onOpenChange={(value) => !value && setOverwrite(null)}
        title="섹션 내용을 덮어쓸까요?"
        description="기존 내용은 가져온 문서로 바뀝니다. 이전 내용은 저장 이력에만 남음."
        confirmLabel="덮어쓰기"
        onConfirm={() => {
          if (overwrite) void props.onImport(overwrite.part, overwrite.source);
          setOverwrite(null);
        }}
      />

      {/* 다른 창으로 옮겨 간 세션(PRD 7.4): 모달 대화 상자라 포커스가 갇히고 배경 입력이 막힌다. 닫을 수 없다 */}
      <Dialog.Root open={stopped} onOpenChange={() => {}}>
        <Dialog.Portal>
          <Dialog.Backdrop className="fixed inset-0 z-[70] bg-canvas/90 backdrop-blur-[2px]" />
          <Dialog.Popup
            role="alertdialog"
            className="fixed top-1/2 left-1/2 z-[71] flex w-[min(24rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 rounded-lg border border-line bg-surface p-6 shadow-[var(--shadow-float)]"
          >
            <Dialog.Title className="text-lg font-semibold">
              {state.replaced && props.connection !== "forbidden"
                ? "다른 창에서 열림"
                : "접속 불가"}
            </Dialog.Title>
            <Dialog.Description className="text-sm text-muted">
              {state.replaced && props.connection !== "forbidden"
                ? "이 창은 멈췄습니다. 작업은 마지막으로 연 창에서 이어집니다."
                : "이 세션에 접속할 수 없습니다. 받은 링크를 다시 열어 주세요."}
            </Dialog.Description>
            <div>
              <Button onClick={() => window.location.reload()}>이 창에서 다시 열기</Button>
            </div>
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={help} onOpenChange={setHelp}>
        <Dialog.Portal>
          <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/30 transition-opacity duration-150 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0" />
          <Dialog.Popup className="fixed top-1/2 left-1/2 z-50 max-h-[85dvh] w-[min(40rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg bg-surface p-6 shadow-[var(--shadow-float)] transition-[transform,opacity] duration-200 ease-[var(--ease-out)] data-[ending-style]:scale-[0.97] data-[ending-style]:opacity-0 data-[starting-style]:scale-[0.97] data-[starting-style]:opacity-0">
            <Dialog.Title className="mb-4 text-xl font-semibold">화면 설명</Dialog.Title>
            <HelpContent />
            <div className="mt-6 flex justify-end">
              <Dialog.Close render={<Button variant="secondary" />}>닫기</Dialog.Close>
            </div>
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
