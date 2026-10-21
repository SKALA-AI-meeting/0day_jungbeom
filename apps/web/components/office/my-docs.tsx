"use client";

// 메인 "내 문서" 탭: 파트별 내 문서 목록 → 편집(DocEditor) → 보내기, 그리고 최종본(FinalDoc) 가져오기·편집·제출.
import { Popover } from "@base-ui/react/popover";
import { useState } from "react";

import { Button, Chip, cn, DropMenu, partTone, type MenuEntry } from "@/components/ui";

import { givenName, remainText } from "./lines";
import type { FinalSection, MyDocument, ReceivedDocument, StateSnapshot } from "./types";

export type SaveState = "saving" | "saved" | "failed";

export type DocTarget = number | "final" | null;

/** 최종본 섹션의 출처 칩 문구: "도현 v2에서" / "도현 v2 + 편집" / "직접 작성" / "비어 있음" */
export function sourceLabel(section: FinalSection, snap: StateSnapshot) {
  if (!section.source_doc_id) return section.content.trim() ? "직접 작성" : "비어 있음";
  const mine = snap.my_documents.some((d) => d.doc_id === section.source_doc_id);
  const who = mine ? "내 문서" : givenName(snap.persona.colleague);
  // version null = 보내지 않은 내 문서의 현재 저장본
  const base =
    section.source_version == null ? `${who} 현재 저장본` : `${who} v${section.source_version}`;
  return section.edited ? `${base} + 편집` : `${base}에서`;
}

/** 저장 표시는 상대 시각("방금 저장", "3분 전 저장"). 벽시계는 세션 시각(00:45)과 섞여 헷갈린다 */
export function savedText(state: SaveState | undefined, updatedAt: string, now = Date.now()) {
  if (state === "saving") return "저장 중…";
  if (state === "failed") return "저장 실패 · 다음 편집 때 다시 저장";
  const minutes = Math.floor((now - Date.parse(updatedAt)) / 60_000);
  return minutes < 1 ? "방금 저장" : `${minutes}분 전 저장`;
}

function docStatus(doc: MyDocument) {
  const last = doc.versions.at(-1);
  if (last) {
    const draftAfter = doc.revision > last.revision;
    return `v${last.version} 보냄${draftAfter ? " · 다음 버전 작성 중" : ""}`;
  }
  return doc.content.trim() ? "작성 중 · 안 보냄" : "비어 있음";
}

/** 동료 단독 파트는 내 목록에 두지 않는다(받은 문서로만 본다). */
export function myParts(snap: StateSnapshot) {
  return snap.my_documents.filter(
    (d) => snap.tasks.find((t) => t.part_no === d.part_no)?.assignee !== "colleague",
  );
}

export function DocList({
  snap,
  onPick,
  onBoard,
}: {
  snap: StateSnapshot;
  onPick: (target: DocTarget) => void;
  /** 분업 전 안내의 "보드로" */
  onBoard: () => void;
}) {
  const filled = snap.final.sections.filter((s) => s.content.trim()).length;
  const docs = myParts(snap);
  return (
    <div className="flex flex-col gap-4 p-5">
      {!snap.division && (
        <div className="flex items-center gap-2 rounded-md bg-accent-soft px-3 py-2.5 text-sm">
          <span className="min-w-0 flex-1">먼저 보드에서 카드 5장의 담당 정하기</span>
          <Button size="xs" onClick={onBoard}>
            보드로 →
          </Button>
        </div>
      )}
      <ul className="flex flex-col gap-1">
        {docs.map((doc) => (
          <li key={doc.doc_id}>
            <button
              type="button"
              onClick={() => onPick(doc.part_no)}
              className="press flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left hover:bg-surface-sunken"
            >
              <Chip tone={partTone(doc.part_no)}>{doc.part_no}</Chip>
              <span className="min-w-0 flex-1 truncate">{doc.title}</span>
              <span className="shrink-0 text-xs text-subtle">{docStatus(doc)}</span>
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => onPick("final")}
        className="press flex items-center gap-2.5 rounded-md border border-line bg-surface px-3 py-3 text-left hover:border-accent/40"
      >
        <span aria-hidden className="text-warning">
          ★
        </span>
        <span className="flex-1 font-semibold">최종본</span>
        <span className="text-xs text-subtle">
          섹션 {snap.final.sections.length} · {filled} 채움
        </span>
      </button>
      <p className="text-xs text-subtle">
        내 문서는 보내야 공유 · 받은 문서는 대화의 문서 카드에서 열기
      </p>
    </div>
  );
}

/** 편집 화면 맨 위 줄: 목록으로 돌아가기와 자료 탭으로 건너가기(CX-06, 편집 내용·자리는 그대로) */
function Back({ onBack, onToLibrary }: { onBack: () => void; onToLibrary?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <button type="button" onClick={onBack} className="text-sm text-muted hover:text-ink">
        ← 내 문서
      </button>
      {onToLibrary && (
        <button type="button" onClick={onToLibrary} className="text-sm text-muted hover:text-ink">
          자료 보기 →
        </button>
      )}
    </div>
  );
}

/** 보내기: 채널과 한마디(선택). 카드 본문은 한마디뿐이고 비우면 카드만 올라간다 */
function SharePopover({
  next,
  disabled,
  reason,
  onShare,
}: {
  next: number;
  disabled: boolean;
  reason: string | null;
  onShare: (channel: "team" | "dm", note: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState<"team" | "dm">("team");
  const [note, setNote] = useState("");
  const option = (value: "team" | "dm", label: string, hint: string) => (
    <button
      type="button"
      aria-pressed={channel === value}
      onClick={() => setChannel(value)}
      className={cn(
        "press flex flex-1 flex-col items-start rounded-md border px-2.5 py-1.5 text-left text-sm",
        channel === value ? "border-accent bg-accent-soft" : "border-line hover:bg-surface-sunken",
      )}
    >
      {label}
      <span className="text-xs text-subtle">{hint}</span>
    </button>
  );
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger
        render={
          <Button size="sm" disabled={disabled} title={reason ?? undefined}>
            v{next} 보내기
          </Button>
        }
      />
      <Popover.Portal>
        <Popover.Positioner sideOffset={6} align="end" className="z-50">
          <Popover.Popup className="flex w-72 origin-[var(--transform-origin)] flex-col gap-3 rounded-lg border border-line bg-surface p-3 shadow-[var(--shadow-float)] transition-[transform,opacity] duration-150 ease-[var(--ease-out)] data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0">
            <div className="flex gap-2">
              {option("team", "# 재참여-기획", "팀장·도현")}
              {option("dm", "이도현 DM", "도현만")}
            </div>
            <textarea
              value={note}
              rows={2}
              onChange={(event) => setNote(event.target.value)}
              placeholder="한마디(선택)"
              aria-label="문서와 함께 보낼 한마디"
              className="resize-none rounded-md border border-line px-2.5 py-1.5 text-sm outline-none focus:border-accent/60"
            />
            <Button
              size="sm"
              onClick={() => {
                onShare(channel, note);
                setNote("");
                setOpen(false);
              }}
            >
              v{next} 보내기
            </Button>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function DocEditor({
  doc,
  save,
  locked,
  onBack,
  onEdit,
  onShare,
  onToLibrary,
}: {
  doc: MyDocument;
  save: SaveState | undefined;
  locked: boolean;
  onBack: () => void;
  onEdit: (content: string) => void;
  onShare: (channel: "team" | "dm", note: string) => void;
  onToLibrary?: () => void;
}) {
  const last = doc.versions.at(-1);
  const next = (last?.version ?? 0) + 1;
  // 마지막으로 보낸 뒤 저장된 편집이 없으면 같은 내용을 새 버전으로 보내지 않게 막는다
  const unchanged = !!last && doc.revision <= last.revision && save !== "saving";
  const reason = !doc.content.trim() ? "내용 없음" : unchanged ? "바뀐 내용 없음" : null;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-col gap-3 border-b border-line px-5 py-3">
        <Back onBack={onBack} onToLibrary={onToLibrary} />
        <div className="flex items-center gap-2">
          <Chip tone={partTone(doc.part_no)}>{doc.part_no}</Chip>
          <h3 className="min-w-0 flex-1 truncate font-semibold">{doc.title}</h3>
          {last && <Chip tone="outline">v{last.version} 보냄</Chip>}
          {unchanged && <span className="text-xs text-subtle">바뀐 내용 없음</span>}
          <SharePopover
            next={next}
            disabled={locked || !!reason}
            reason={reason}
            onShare={onShare}
          />
        </div>
      </div>
      <textarea
        aria-label={`${doc.part_no}. ${doc.title} 본문`}
        value={doc.content}
        readOnly={locked}
        onChange={(event) => onEdit(event.target.value)}
        placeholder="파트 내용 작성 · 보내기 전에는 나만 봄"
        className="min-h-0 flex-1 resize-none bg-surface px-5 py-4 text-base leading-7 outline-none placeholder:text-subtle read-only:bg-surface-sunken"
      />
      <p className="shrink-0 border-t border-line px-5 py-2 text-xs text-subtle">
        {savedText(save, doc.updated_at)}
        {last && " · 보낸 뒤 편집은 다음 버전 초안"}
      </p>
    </div>
  );
}

/**
 * 섹션에 넣을 수 있는 출처: 받은 동료 문서의 보낸 버전(최신 먼저)과 내 문서 현재 저장본(version null).
 * 같은 파트 문서를 맨 위에 "같은 파트"로 둔다.
 */
export function importChoices(
  section: FinalSection,
  received: ReceivedDocument[],
  mine: MyDocument[],
  colleague: string,
  onImport: (source: { source_doc_id: string; version: number | null }) => void,
): MenuEntry[] {
  const samePartFirst = <T extends { part_no: number }>(list: T[]) =>
    [...list].sort(
      (a, b) => Number(b.part_no === section.part_no) - Number(a.part_no === section.part_no),
    );
  const tag = (part: number) => (part === section.part_no ? " · 같은 파트" : "");
  const theirs = samePartFirst(received).flatMap((doc) =>
    [...doc.versions].reverse().map((v, i) => ({
      label: `${doc.part_no}. ${doc.title} v${v.version}`,
      hint: `${colleague}${i === 0 ? " · 최신" : ""}${tag(doc.part_no)}`,
      onSelect: () => onImport({ source_doc_id: doc.doc_id, version: v.version }),
    })),
  );
  const own = samePartFirst(mine.filter((d) => d.content.trim())).map((d) => ({
    label: `${d.part_no}. ${d.title}`,
    hint: `현재 저장본${tag(d.part_no)}`,
    onSelect: () => onImport({ source_doc_id: d.doc_id, version: null }),
  }));
  const items: MenuEntry[] = [];
  if (theirs.length) items.push({ group: "받은 문서" }, ...theirs);
  if (own.length) items.push({ group: "내 문서" }, ...own);
  if (!items.length) items.push({ label: "가져올 문서 없음", disabled: true, onSelect: () => {} });
  return items;
}

export function FinalDoc({
  snap,
  save,
  locked,
  remainingSeconds,
  onBack,
  onEdit,
  onImport,
  onSubmit,
  onToLibrary,
}: {
  snap: StateSnapshot;
  save: SaveState | undefined;
  locked: boolean;
  remainingSeconds: number | null;
  onBack: () => void;
  onEdit: (partNo: number, content: string) => void;
  onImport: (partNo: number, source: { source_doc_id: string; version: number | null }) => void;
  onSubmit: () => void;
  onToLibrary?: () => void;
}) {
  const colleague = givenName(snap.persona.colleague);
  const empty = snap.final.sections.filter((s) => !s.content.trim()).length;
  const [focus, setFocus] = useState<number | null>(null);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-col gap-1 border-b border-line px-5 py-3">
        <Back onBack={onBack} onToLibrary={onToLibrary} />
        <div className="flex items-baseline gap-2">
          <h3 className="font-semibold">★ 최종본</h3>
          <span className="text-xs text-subtle">킥오프 템플릿 · {snap.final.template.length}</span>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {snap.final.sections.map((section) => (
          <section key={section.part_no} className="border-b border-line px-5 py-4">
            <div className="mb-2 flex items-center gap-2">
              <Chip tone={partTone(section.part_no)}>{section.part_no}</Chip>
              <h4 className="min-w-0 flex-1 truncate text-sm font-semibold">{section.title}</h4>
              <Chip tone={section.source_doc_id ? "accent" : "neutral"}>
                {sourceLabel(section, snap)}
              </Chip>
              <DropMenu
                align="end"
                trigger={
                  <Button size="xs" variant="ghost" disabled={locked}>
                    가져오기
                  </Button>
                }
                items={importChoices(
                  section,
                  snap.received,
                  snap.my_documents,
                  colleague,
                  (source) => onImport(section.part_no, source),
                )}
              />
            </div>
            <textarea
              aria-label={`최종본 ${section.part_no}. ${section.title}`}
              value={section.content}
              readOnly={locked}
              rows={focus === section.part_no ? 8 : 3}
              onFocus={() => setFocus(section.part_no)}
              onChange={(event) => onEdit(section.part_no, event.target.value)}
              placeholder="받은 문서 가져오기 또는 직접 작성"
              className="w-full resize-y rounded-md border border-line bg-surface px-3 py-2 text-sm leading-6 outline-none placeholder:text-subtle focus:border-accent/60 read-only:bg-surface-sunken"
            />
          </section>
        ))}
      </div>
      <div className="flex shrink-0 items-center gap-3 border-t border-line bg-surface px-5 py-3">
        {/* 저장 실패는 다음 저장이 성공할 때까지 바닥에 남긴다(제출은 저장 확인이 막는다) */}
        <span
          className={cn(
            "min-w-0 flex-1 text-xs",
            !locked && save === "failed" ? "text-danger" : "text-subtle",
          )}
        >
          {locked
            ? "제출 완료 · 수정 불가"
            : save === "failed"
              ? "저장 실패 · 다음 편집 때 다시 저장"
              : remainingSeconds != null && remainingSeconds <= 120
                ? `마감 ${remainText(remainingSeconds)} 전 · 시간이 끝나면 자동 제출`
                : save === "saving"
                  ? "저장 중…"
                  : empty > 0
                    ? `빈 섹션 ${empty}개 · 제출 뒤 팀장 보고로 종료`
                    : "제출 뒤 팀장 보고로 종료"}
        </span>
        {/* 빈 섹션이 있으면 제출을 보조 버튼으로 낮춘다 */}
        <Button variant={empty > 0 ? "secondary" : "primary"} disabled={locked} onClick={onSubmit}>
          제출
        </Button>
      </div>
    </div>
  );
}
