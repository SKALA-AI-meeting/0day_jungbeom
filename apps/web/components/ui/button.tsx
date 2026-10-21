import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "./cn";

const button = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap transition-[background-color,border-color,color,scale] duration-150 ease-[var(--ease-out)] active:not-disabled:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:active:not-disabled:scale-100",
  {
    variants: {
      variant: {
        primary: "bg-accent-fill text-on-accent hover:bg-accent-fill-hover",
        secondary: "border border-line bg-surface text-ink hover:bg-surface-sunken",
        ghost: "text-ink hover:bg-surface-sunken",
        danger: "bg-danger-fill text-on-accent hover:opacity-90",
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
  return (
    <button
      className={cn(button({ variant, size }), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {children}
    </button>
  );
}
