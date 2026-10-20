import type { ReactNode } from "react";

import { cn } from "./cn";

export type CardProps = {
  title?: ReactNode;
  /** 제목 오른쪽(배지·버튼 자리) */
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
};

export function Card({ title, actions, className, children }: CardProps) {
  return (
    <section className={cn("rounded-lg border border-line bg-surface p-5", className)}>
      {(title || actions) && (
        <header className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="text-lg font-semibold">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
