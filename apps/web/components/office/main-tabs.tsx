"use client";

// 메인 영역 탭(CX-08): 대화·내 문서·보드·자료·어시스턴트를 한 자리에서 바꿔 본다.
// 패널은 모두 마운트한 채 숨긴다. 탭을 오가도 열어 둔 문서·스크롤·입력 중인 글이 그대로 남는다.
import { useRef, type KeyboardEvent, type ReactNode } from "react";

import { cn } from "@/components/ui";

export type MainTab = "chat" | "docs" | "board" | "library" | "assistant";

export const MAIN_TABS: { value: MainTab; label: string }[] = [
  { value: "chat", label: "대화" },
  { value: "docs", label: "내 문서" },
  { value: "board", label: "보드" },
  { value: "library", label: "자료" },
  { value: "assistant", label: "어시스턴트" },
];

const tabId = (value: MainTab) => `main-tab-${value}`;
const panelId = (value: MainTab) => `main-panel-${value}`;

export function MainTabBar({
  value,
  counts,
  onChange,
  end,
}: {
  value: MainTab;
  /** 탭 옆 배지(대화 탭의 새 메시지 수). 0이면 숨김 */
  counts?: Partial<Record<MainTab, number>>;
  onChange: (value: MainTab) => void;
  /** 탭 줄 오른쪽 끝(도움말 버튼) */
  end?: ReactNode;
}) {
  const list = useRef<HTMLDivElement>(null);
  // 좌우 화살표·Home·End로 탭 사이를 옮긴다(WAI-ARIA tabs 패턴, 자동 활성)
  const onKeyDown = (event: KeyboardEvent) => {
    const index = MAIN_TABS.findIndex((t) => t.value === value);
    const last = MAIN_TABS.length - 1;
    const target =
      event.key === "ArrowRight"
        ? (index + 1) % MAIN_TABS.length
        : event.key === "ArrowLeft"
          ? (index + last) % MAIN_TABS.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? last
              : null;
    if (target == null) return;
    const next = MAIN_TABS[target].value;
    onChange(next);
    list.current?.querySelector<HTMLButtonElement>(`#${tabId(next)}`)?.focus();
    event.preventDefault();
  };
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-line bg-surface pr-3">
      <div
        ref={list}
        role="tablist"
        aria-label="작업 영역"
        onKeyDown={onKeyDown}
        className="flex min-w-0 flex-1 gap-1 overflow-x-auto px-3"
      >
        {MAIN_TABS.map((tab) => {
          const selected = tab.value === value;
          const count = counts?.[tab.value];
          return (
            <button
              key={tab.value}
              id={tabId(tab.value)}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={panelId(tab.value)}
              aria-label={count ? `${tab.label}, 새 메시지 ${count}개` : undefined}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.value)}
              className={cn(
                "-mb-px flex shrink-0 items-center border-b-2 px-3 py-2.5 text-sm whitespace-nowrap transition-colors",
                selected
                  ? "border-accent font-medium text-ink"
                  : "border-transparent text-muted hover:text-ink",
              )}
            >
              <span>{tab.label}</span>
              {!!count && (
                <span
                  aria-hidden
                  className="ml-1.5 rounded-sm bg-accent px-1.5 text-xs font-semibold text-white tabular-nums"
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {end}
    </div>
  );
}

/** 숨긴 패널은 visibility로 감춰 레이아웃과 스크롤 위치를 유지하고, inert로 포커스·입력을 막는다 */
export function TabPanel({
  value,
  active,
  className,
  children,
}: {
  value: MainTab;
  active: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      id={panelId(value)}
      role="tabpanel"
      aria-labelledby={tabId(value)}
      inert={!active}
      className={cn("absolute inset-0 flex flex-col", !active && "invisible", className)}
    >
      {children}
    </div>
  );
}
