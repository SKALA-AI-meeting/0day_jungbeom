"use client";

// 분절 컨트롤(라디오 묶음). 세션 길이(60·15분)와 차원 수준(1~5·기록 없음) 선택에 쓴다.
import { cn } from "@/components/ui";

export type SegmentedProps<T extends string | number> = {
  label: string;
  value: T | null;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
  className?: string;
};

export function Segmented<T extends string | number>({
  label,
  value,
  options,
  onChange,
  disabled,
  className,
}: SegmentedProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn("inline-flex rounded-md bg-surface-sunken p-0.5", className)}
    >
      {options.map((option) => {
        const on = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-[calc(var(--radius-md)-2px)] border px-3 py-1 text-sm whitespace-nowrap tabular-nums transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50",
              on
                ? "border-line bg-surface font-semibold text-ink"
                : "border-transparent text-muted hover:text-ink",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
