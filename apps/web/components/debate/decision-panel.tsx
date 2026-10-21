"use client";

// 결정 사항(ConsensusPanel): 정한 결과 줄만 쌓이고 현재 정할 항목에만 입력과 [이걸로 정하기].
// 후보안·지지 현황·오피스 시각은 보이지 않는다(D14·R7). 정하기는 늘 확인 창 하나(UX 결정 1·2).
import { CircleCheck, Clock3 } from "lucide-react";
import { useState } from "react";

import { Button, ConfirmDialog, cn } from "@/components/ui";

import { SLOT_LABEL, nameOf } from "./state";
import { SLOT_PHASES, type Slot, type SlotPhase, type StateSnapshot } from "./types";

export type KeywordOption = { key: string; label: string };

function Result({ slot, snap, flash }: { slot: Slot; snap: StateSnapshot; flash: boolean }) {
  const { filled_by: filledBy, resolution } = slot;
  const timeout = resolution === "timeout";
  return (
    <li className={cn("flex flex-col gap-1 px-6 py-4", flash && "settle")} data-slot={slot.phase}>
      <div className="flex items-baseline gap-2">
        <span className="text-footnote text-muted">{SLOT_LABEL[slot.phase]}</span>
        <span
          className={cn(
            "ml-auto inline-flex items-center gap-1 text-footnote",
            timeout ? "text-muted" : "text-success",
          )}
        >
          {timeout ? <Clock3 size={14} aria-hidden /> : <CircleCheck size={14} aria-hidden />}
          {timeout ? "시간 초과" : "합의"}
        </span>
      </div>
      <p className="text-callout font-semibold break-words">{slot.value}</p>
      {filledBy && (
        <p className="text-caption text-muted">
          정한 사람 · {filledBy === "candidate" ? "나" : nameOf(snap, filledBy)}
        </p>
      )}
    </li>
  );
}

function SlotInput({
  phase,
  keywordOptions,
  locked,
  onConfirm,
}: {
  phase: SlotPhase;
  keywordOptions: KeywordOption[];
  locked: boolean;
  onConfirm: (phase: SlotPhase, value: string, optionKey?: string) => Promise<string | null>;
}) {
  const [value, setValue] = useState("");
  const [keyword, setKeyword] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isKeyword = phase === "keyword";
  const chosen = keywordOptions.find((k) => k.key === keyword);
  const ready = isKeyword ? !!chosen : value.trim().length > 0;

  const confirm = async () => {
    setPending(true);
    const result = await onConfirm(
      phase,
      isKeyword ? (chosen?.label ?? "") : value.trim(),
      isKeyword ? (chosen?.key ?? undefined) : undefined,
    );
    setPending(false);
    setOpen(false);
    setError(result);
  };

  return (
    <li className="flex flex-col gap-3 px-6 py-5" data-slot-input={phase}>
      <div className="flex items-baseline gap-2">
        <span className="text-footnote font-semibold text-accent">{SLOT_LABEL[phase]}</span>
        <span className="text-caption text-muted">지금 정할 항목</span>
      </div>
      {isKeyword ? (
        <div
          role="radiogroup"
          aria-label="키워드 후보"
          className="flex rounded-md bg-surface-sunken p-0.5"
        >
          {keywordOptions.map((option) => (
            <button
              key={option.key}
              type="button"
              role="radio"
              aria-checked={keyword === option.key}
              disabled={locked}
              onClick={() => setKeyword(option.key)}
              className={cn(
                "flex-1 rounded-[calc(var(--radius-md)-2px)] px-3 py-1.5 text-body transition-colors duration-150",
                keyword === option.key
                  ? "border border-line bg-surface font-semibold text-ink"
                  : "border border-transparent text-muted",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : (
        <textarea
          rows={2}
          value={value}
          disabled={locked}
          maxLength={200}
          aria-label={`${SLOT_LABEL[phase]} 입력`}
          onChange={(event) => setValue(event.target.value)}
          className="resize-none rounded-md border border-line bg-surface px-3 py-2 text-body outline-none focus-visible:border-accent disabled:bg-surface-sunken"
        />
      )}
      {error && (
        <p role="alert" className="text-footnote text-danger">
          {error}
        </p>
      )}
      <div className="flex justify-end">
        <Button size="sm" disabled={!ready || locked} onClick={() => setOpen(true)}>
          이걸로 정하기
        </Button>
      </div>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="이걸로 정하면 다음 단계로 넘어가요"
        description={`${SLOT_LABEL[phase]}: ${isKeyword ? (chosen?.label ?? "") : value.trim()}`}
        confirmLabel="이걸로 정하기"
        pending={pending}
        onConfirm={confirm}
      />
    </li>
  );
}

export function DecisionPanel({
  snap,
  flash,
  locked,
  keywordOptions,
  onConfirm,
}: {
  snap: StateSnapshot;
  flash: SlotPhase | null;
  locked: boolean;
  keywordOptions: KeywordOption[];
  onConfirm: (phase: SlotPhase, value: string, optionKey?: string) => Promise<string | null>;
}) {
  const current = snap.session.phase;
  return (
    <ul className="flex flex-col divide-y divide-line" aria-label="결정 사항">
      {SLOT_PHASES.map((phase) => {
        const slot = snap.slots.find((s) => s.phase === phase);
        if (slot?.status === "confirmed")
          return <Result key={phase} slot={slot} snap={snap} flash={flash === phase} />;
        if (phase === current)
          return (
            <SlotInput
              key={phase}
              phase={phase}
              keywordOptions={keywordOptions}
              locked={locked}
              onConfirm={onConfirm}
            />
          );
        return (
          <li key={phase} className="flex items-baseline gap-2 px-6 py-4">
            <span className="text-footnote text-muted">{SLOT_LABEL[phase]}</span>
            <span className="ml-auto text-caption text-muted">다음에 정할 항목</span>
          </li>
        );
      })}
    </ul>
  );
}
