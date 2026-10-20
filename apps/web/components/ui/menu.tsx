"use client";

import { Menu } from "@base-ui/react/menu";
import type { ReactElement, ReactNode } from "react";

import { cn } from "./cn";

export type MenuEntry =
  | {
      label: ReactNode;
      /** 오른쪽 보조 문구(버전·시각) */
      hint?: ReactNode;
      disabled?: boolean;
      onSelect: () => void;
    }
  | { group: ReactNode };

export type DropMenuProps = {
  /** 누르는 요소. base-ui render prop으로 붙는다 */
  trigger: ReactElement;
  items: MenuEntry[];
  align?: "start" | "end";
  side?: "bottom" | "top";
  className?: string;
};

/** 채널 선택·가져오기 출처·담당 선택 같은 짧은 선택 목록. 트리거에서 펼쳐진다(transform-origin). */
export function DropMenu({
  trigger,
  items,
  align = "start",
  side = "bottom",
  className,
}: DropMenuProps) {
  return (
    <Menu.Root>
      <Menu.Trigger render={trigger} />
      <Menu.Portal>
        <Menu.Positioner sideOffset={6} align={align} side={side} className="z-50">
          <Menu.Popup
            className={cn(
              "min-w-48 origin-[var(--transform-origin)] rounded-lg border border-line bg-surface p-1 text-sm shadow-[var(--shadow-float)] outline-none",
              "transition-[transform,opacity] duration-150 ease-[var(--ease-out)] data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0",
              className,
            )}
          >
            {items.map((item, i) =>
              "group" in item ? (
                <div key={i} className="px-2 pt-2 pb-1 text-xs text-subtle">
                  {item.group}
                </div>
              ) : (
                <Menu.Item
                  key={i}
                  disabled={item.disabled}
                  onClick={item.onSelect}
                  className="flex cursor-default items-center justify-between gap-4 rounded-md px-2 py-1.5 outline-none select-none data-[disabled]:opacity-40 data-[highlighted]:bg-surface-sunken"
                >
                  <span className="min-w-0 truncate">{item.label}</span>
                  {item.hint && <span className="shrink-0 text-xs text-subtle">{item.hint}</span>}
                </Menu.Item>
              ),
            )}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
