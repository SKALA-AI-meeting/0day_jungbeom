"use client";

// 태스크 보드: 파트 카드 5개와 담당자 배지. 상태는 내 카드(나·함께)만 바꿀 수 있다.
import { Badge, EmptyState, Select } from "@/components/ui";

import { PART_TITLES } from "./parts";
import type { OfficeState } from "./reducer";
import type { TaskStatus } from "./types";

const STATUS_OPTIONS: { value: TaskStatus; label: string }[] = [
  { value: "todo", label: "할 일" },
  { value: "doing", label: "진행 중" },
  { value: "done", label: "완료" },
];

export function TaskBoard({
  state,
  disabled,
  onTask,
}: {
  state: OfficeState;
  disabled?: boolean;
  onTask: (partNo: number, status: TaskStatus) => void;
}) {
  if (state.tasks.length === 0) {
    return <EmptyState title="아직 카드가 없어요" description="파트를 나누면 카드가 생겨요." />;
  }
  return (
    <ul className="flex flex-col gap-3 p-4">
      {state.tasks.map((task) => {
        const mine = task.assignee !== "colleague";
        return (
          <li key={task.part_no} className="rounded-md border border-line bg-surface p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">
                {task.part_no}. {PART_TITLES[task.part_no]}
              </span>
              <Badge tone={mine ? "accent" : "neutral"}>
                {task.assignee === "candidate"
                  ? "나"
                  : task.assignee === "both"
                    ? "함께"
                    : state.persona.colleague}
              </Badge>
            </div>
            <div className="mt-2">
              {mine ? (
                <Select
                  aria-label={`${task.part_no}번 카드 상태`}
                  value={task.status}
                  disabled={disabled}
                  options={STATUS_OPTIONS}
                  onChange={(event) => onTask(task.part_no, event.target.value as TaskStatus)}
                />
              ) : (
                <span className="text-sm text-muted">
                  {STATUS_OPTIONS.find((o) => o.value === task.status)?.label}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
