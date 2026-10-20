import { cva, type VariantProps } from "class-variance-authority";
import type { ReactNode } from "react";

import { cn } from "./cn";

const chip = cva(
  "inline-flex max-w-full shrink-0 items-center gap-1 rounded-sm px-1.5 py-px text-xs font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "bg-surface-sunken text-muted",
        accent: "bg-accent-soft text-accent-strong",
        success: "bg-success-soft text-success",
        warning: "bg-warning-soft text-warning",
        danger: "bg-danger-soft text-danger",
        outline: "border border-line bg-surface text-muted",
        part1: "bg-part1 text-part1-ink",
        part2: "bg-part2 text-part2-ink",
        part3: "bg-part3 text-part3-ink",
        part4: "bg-part4 text-part4-ink",
        part5: "bg-part5 text-part5-ink",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export type ChipTone = NonNullable<VariantProps<typeof chip>["tone"]>;

export type ChipProps = {
  tone?: ChipTone;
  className?: string;
  title?: string;
  children: ReactNode;
};

/** 파트 태그·버전·"2번 필요" 의존 배지·값 칩 */
export function Chip({ tone, className, title, children }: ChipProps) {
  return (
    <span title={title} className={cn(chip({ tone }), className)}>
      {children}
    </span>
  );
}

/** 파트 번호 → 파스텔 칩 색 */
export function partTone(partNo: number | "final" | null | undefined): ChipTone {
  if (typeof partNo !== "number" || partNo < 1 || partNo > 5) return "neutral";
  return `part${partNo}` as ChipTone;
}
