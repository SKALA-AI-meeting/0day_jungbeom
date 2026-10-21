import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "./cn";

const button = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap transition-[background-color,border-color,color,scale] duration-150 ease-[var(--ease-out)] active:not-disabled:scale-[0.98] disabled:cursor-not-allowed motion-reduce:active:not-disabled:scale-100",
  {
    variants: {
      variant: {
        primary: "bg-accent-fill text-on-accent not-disabled:hover:bg-accent-fill-hover",
        secondary:
          "border border-line bg-surface text-ink hover:bg-surface-sunken disabled:opacity-50",
        ghost: "text-ink hover:bg-surface-sunken disabled:opacity-50",
        danger: "bg-danger-fill text-on-accent hover:opacity-90 disabled:opacity-50",
      },
      size: {
        xs: "h-7 px-2 text-xs",
        sm: "h-8 px-3.5 text-sm",
        md: "h-10 px-4 text-base",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof button> & {
    /** 요청 중 표시. true면 비활성화된다. */
    loading?: boolean;
  };

export function Button({
  variant,
  size,
  loading,
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  // primary는 비활성이면 회색 면(못 누름), 로딩이면 파란 면 + 회전 표시(제출 중)로 둘을 구분한다
  const primaryDisabled =
    (variant ?? "primary") === "primary" &&
    !loading &&
    "disabled:bg-surface-sunken disabled:text-muted";
  return (
    <button
      className={cn(button({ variant, size }), primaryDisabled, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && (
        <Loader2 size={14} className="animate-spin motion-reduce:animate-none" aria-hidden />
      )}
      {children}
    </button>
  );
}
