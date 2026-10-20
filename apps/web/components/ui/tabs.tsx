"use client";

import { Tabs as BaseTabs } from "@base-ui/react/tabs";
import type { ReactNode } from "react";

import { cn } from "./cn";

export type TabItem = {
  value: string;
  label: ReactNode;
  /** 안 읽음 수 등. 0이나 undefined면 숨김 */
  count?: number;
  content: ReactNode;
};

export type TabsProps = {
  items: TabItem[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  className?: string;
};

export function Tabs({ items, value, defaultValue, onValueChange, className }: TabsProps) {
  return (
    <BaseTabs.Root
      value={value}
      defaultValue={defaultValue ?? items[0]?.value}
      onValueChange={(next) => onValueChange?.(String(next))}
      className={cn("flex min-h-0 flex-col", className)}
    >
      <BaseTabs.List className="flex shrink-0 gap-1 border-b border-line px-3">
        {items.map((item) => (
          <BaseTabs.Tab
            key={item.value}
            value={item.value}
            className="-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-muted aria-selected:border-accent aria-selected:font-medium aria-selected:text-ink"
          >
            {item.label}
            {!!item.count && (
              <span className="ml-1.5 rounded-sm bg-accent px-1.5 text-xs text-white">
                {item.count}
              </span>
            )}
          </BaseTabs.Tab>
        ))}
      </BaseTabs.List>
      {items.map((item) => (
        <BaseTabs.Panel
          key={item.value}
          value={item.value}
          className="min-h-0 flex-1 overflow-auto"
        >
          {item.content}
        </BaseTabs.Panel>
      ))}
    </BaseTabs.Root>
  );
}
