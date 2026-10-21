import type { ReactNode } from "react";

export type EmptyStateProps = { title: ReactNode; description?: ReactNode; action?: ReactNode };

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <p className="text-callout font-semibold">{title}</p>
      {description && <p className="text-sm text-muted">{description}</p>}
      {action}
    </div>
  );
}
