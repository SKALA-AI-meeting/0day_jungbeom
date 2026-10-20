import { cn } from "./cn";

export type PillStatus = "todo" | "doing" | "done";

export const PILL_LABELS: Record<PillStatus, string> = {
  todo: "할 일",
  doing: "진행 중",
  done: "완료",
};

const TONE: Record<PillStatus, string> = {
  todo: "bg-surface-sunken text-muted",
  doing: "bg-warning-soft text-warning",
  done: "bg-success-soft text-success",
};

/** 점선 원 / 반원 / 체크 원 */
export function StatusIcon({ status, className }: { status: PillStatus; className?: string }) {
  return (
    <svg viewBox="0 0 14 14" aria-hidden className={cn("size-3.5 shrink-0", className)}>
      {status === "todo" && (
        <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" strokeDasharray="2 2" />
      )}
      {status === "doing" && (
        <>
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" />
          <path d="M7 1.5a5.5 5.5 0 0 1 0 11z" fill="currentColor" />
        </>
      )}
      {status === "done" && (
        <>
          <circle cx="7" cy="7" r="6" fill="currentColor" />
          <path
            d="M4.3 7.2l1.8 1.8 3.6-3.8"
            fill="none"
            stroke="white"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </>
      )}
    </svg>
  );
}

export type StatusPillProps = { status: PillStatus; className?: string };

/** 할 일·진행 중·완료. 보드 칸 머리와 카드에 공용 */
export function StatusPill({ status, className }: StatusPillProps) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-sm px-1.5 py-px text-xs font-medium whitespace-nowrap",
        TONE[status],
        className,
      )}
    >
      <StatusIcon status={status} />
      {PILL_LABELS[status]}
    </span>
  );
}
