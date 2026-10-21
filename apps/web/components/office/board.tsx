"use client";

// 메인 "보드" 탭: 카드 5장을 상태별 칸(할 일·진행 중·완료)에 두고 담당·순서·언제까지를 정한다.
// 담당 5장이 다 차면 서버가 분업을 확정한다(division.confirmed). 칸 영역이 680px 이상이면 칸 3개를 가로로,
// 좁으면 세로로 쌓는다. 쌓였을 때도 맨 위 상태별 수로 현황을 한 줄에 본다(CX-13).
import {
  closestCorners,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useReducedMotion } from "motion/react";
import { useState } from "react";

import {
  Avatar,
  Button,
  Chip,
  cn,
  DropMenu,
  PILL_LABELS,
  partTone,
  StatusIcon,
  StatusPill,
} from "@/components/ui";

import { assigneeWord, clock, divisionLine, givenName } from "./lines";
import type { Assignee, StateSnapshot, Task, TaskStatus } from "./types";

export const COLUMNS: TaskStatus[] = ["todo", "doing", "done"];

/** 카드 버튼의 aria-controls가 가리키는 상세 패널 */
const DETAIL_ID = "board-card-detail";

export type MovePatch = { part_no: number; status?: TaskStatus; order?: number };

/** 칸별 카드(순서대로) */
export function columnsOf(tasks: Task[]): Record<TaskStatus, Task[]> {
  const out: Record<TaskStatus, Task[]> = { todo: [], doing: [], done: [] };
  for (const t of [...tasks].sort((a, b) => a.order - b.order)) out[t.status].push(t);
  return out;
}

/**
 * 카드 하나를 toStatus 칸의 toIndex 자리로 옮길 때 서버에 보낼 변경. 옮긴 칸의 순서를 1부터 다시 매기고
 * 실제로 바뀐 카드만 돌려준다(카드마다 PUT 한 번).
 */
export function moveTask(
  tasks: Task[],
  part: number,
  toStatus: TaskStatus,
  toIndex: number,
): MovePatch[] {
  const moving = tasks.find((t) => t.part_no === part);
  if (!moving) return [];
  const column = columnsOf(tasks)[toStatus].filter((t) => t.part_no !== part);
  column.splice(Math.max(0, Math.min(toIndex, column.length)), 0, moving);
  const patches: MovePatch[] = [];
  column.forEach((t, i) => {
    const patch: MovePatch = { part_no: t.part_no };
    if (t.part_no === part && t.status !== toStatus) patch.status = toStatus;
    if (t.order !== i + 1) patch.order = i + 1;
    if (patch.status || patch.order) patches.push(patch);
  });
  return patches;
}

/**
 * 놓은 자리(moveTask의 toIndex: 옮기는 카드를 뺀 칸에서의 위치). 같은 칸에서 아래로 옮기면 over 카드
 * 뒤로 가야 하므로 원래 칸에서의 over 위치를 그대로 쓴다(arrayMove와 같은 결과). 칸 자체에 놓으면 맨 끝.
 */
export function dropIndex(column: Task[], activeId: number, overId: string | number) {
  const rest = column.filter((t) => t.part_no !== activeId);
  const overInColumn = column.findIndex((t) => t.part_no === overId);
  if (overInColumn === -1) return rest.length;
  if (column.some((t) => t.part_no === activeId)) return overInColumn;
  return rest.findIndex((t) => t.part_no === overId);
}

/** "언제까지" 프리셋(남은 시간 기준) → 세션 분 */
export function duePresets(nowMin: number, sessionMinutes: number) {
  return [
    { label: "30분 뒤", due_min: Math.min(sessionMinutes, Math.ceil(nowMin + 30)) },
    { label: "마감 10분 전", due_min: sessionMinutes - 10 },
  ];
}

/** "01:10" → 70. 형식이 틀리면 null */
export function parseClock(text: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
  if (!m || Number(m[2]) > 59) return null;
  return Number(m[1]) * 60 + Number(m[2]);
}

function AssigneeAvatars({
  assignee,
  persona,
}: {
  assignee: Assignee | null;
  persona: StateSnapshot["persona"];
}) {
  if (!assignee) {
    return (
      <span className="flex h-6 shrink-0 items-center gap-0.5 rounded-full border border-dashed border-subtle px-2 text-xs text-subtle">
        + 담당
      </span>
    );
  }
  const colleague = (
    <Avatar
      label={givenName(persona.colleague)[0]}
      tone="colleague"
      size={20}
      name={persona.colleague}
    />
  );
  const me = <Avatar label="나" tone="candidate" size={20} name="나" />;
  if (assignee === "candidate") return me;
  if (assignee === "colleague") return colleague;
  return (
    <span className="flex shrink-0 items-center">
      {me}
      <span className="-ml-1.5 rounded-full ring-2 ring-surface">{colleague}</span>
    </span>
  );
}

function assigneeItems(persona: StateSnapshot["persona"], onPick: (a: Assignee) => void) {
  return [
    { group: "담당" },
    { label: "나", onSelect: () => onPick("candidate") },
    { label: givenName(persona.colleague), onSelect: () => onPick("colleague") },
    { label: `둘 다 (나 + ${givenName(persona.colleague)})`, onSelect: () => onPick("both") },
  ];
}

function BoardCard({
  task,
  title,
  snap,
  locked,
  selected,
  onSelect,
  onAssign,
}: {
  task: Task;
  title: string;
  snap: StateSnapshot;
  locked: boolean;
  selected: boolean;
  onSelect: () => void;
  onAssign: (assignee: Assignee) => void;
}) {
  const reduce = useReducedMotion();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: task.part_no,
    disabled: locked,
    // 카드 이동 150ms(design-system.md 모션). 동작 줄이기면 자리만 바꾼다
    transition: reduce ? null : { duration: 150, easing: "cubic-bezier(0.23, 1, 0.32, 1)" },
  });
  return (
    <li
      ref={setNodeRef}
      style={{
        transform: CSS.Translate.toString(transform),
        // 끄는 동안 0.98로 눌렀다가 놓으면 1로 돌아온다(scale은 transform과 따로 전환)
        transition: [transition, "scale 150ms cubic-bezier(0.23, 1, 0.32, 1)"]
          .filter(Boolean)
          .join(", "),
      }}
      className={cn(
        "flex items-center gap-2 rounded-md border bg-surface px-2.5 py-2",
        selected ? "border-accent/60" : "border-line",
        isDragging &&
          "relative z-10 scale-[0.98] shadow-[var(--shadow-float)] motion-reduce:scale-100",
      )}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        aria-label={`${task.part_no}번 카드 옮기기`}
        className="cursor-grab touch-none px-0.5 text-subtle active:cursor-grabbing disabled:cursor-default"
        disabled={locked}
      >
        ⋮⋮
      </button>
      <button
        type="button"
        onClick={onSelect}
        aria-expanded={selected}
        aria-controls={selected ? DETAIL_ID : undefined}
        className="flex min-w-0 flex-1 flex-col items-start gap-1 text-left"
      >
        <span className="flex w-full min-w-0 items-center gap-1.5">
          <Chip tone={partTone(task.part_no)}>{task.part_no}</Chip>
          <span className="min-w-0 truncate text-sm font-medium break-keep @min-[680px]:line-clamp-2 @min-[680px]:whitespace-normal">
            {title}
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-1.5">
          {task.depends_on.map((d) => (
            <Chip key={d} tone="warning">
              {d}번 필요
            </Chip>
          ))}
          {task.due_min != null && <Chip tone="outline">~{clock(task.due_min)}</Chip>}
        </span>
      </button>
      <DropMenu
        align="end"
        trigger={
          <button
            type="button"
            disabled={locked}
            aria-label={`${task.part_no}번 담당: ${assigneeWord(task.assignee, snap.persona)}`}
            className="press rounded-full"
          >
            <AssigneeAvatars assignee={task.assignee} persona={snap.persona} />
          </button>
        }
        items={assigneeItems(snap.persona, onAssign)}
      />
    </li>
  );
}

function Column({
  status,
  children,
  count,
}: {
  status: TaskStatus;
  children: React.ReactNode;
  count: number;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `col-${status}` });
  // 빈 완료 칸은 머리 한 줄로 접는다. 칸 전체가 놓을 자리라 끌어 오면 카드가 들어가며 펼쳐진다
  const folded = status === "done" && count === 0;
  return (
    <section
      ref={setNodeRef}
      className={cn(
        "rounded-lg p-2 transition-colors",
        isOver ? "bg-accent-soft/50" : "bg-surface-sunken/60",
      )}
    >
      <h4 className={cn("flex items-center gap-2 px-1", !folded && "mb-2")}>
        <StatusPill status={status} />
        <span className="text-xs text-muted tabular-nums">{count}</span>
        {folded && <span className="text-xs text-muted">끝난 카드를 여기로</span>}
      </h4>
      {!folded && children}
    </section>
  );
}

function PropertyRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[72px_1fr] items-start gap-2 py-1.5">
      <span className="pt-1 text-sm text-muted">{label}</span>
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">{children}</div>
    </div>
  );
}

function CardDetail({
  task,
  title,
  snap,
  nowMin,
  sessionMinutes,
  locked,
  error,
  onPatch,
  onClose,
}: {
  task: Task;
  title: string;
  snap: StateSnapshot;
  nowMin: number;
  sessionMinutes: number;
  locked: boolean;
  error: string | null;
  onPatch: (patch: Partial<Task>) => void;
  onClose: () => void;
}) {
  const [custom, setCustom] = useState("");
  // 이 카드를 기다리는 카드(역방향 의존). 2번 지연이 3번에 미치는 영향을 2번 쪽에서도 보이게 한다
  const waiting = snap.tasks
    .filter((t) => t.depends_on.includes(task.part_no))
    .map((t) => t.part_no);
  const customMin = parseClock(custom);
  const seg = (active: boolean) =>
    cn(
      "press rounded-md border px-2 py-1 text-sm",
      active
        ? "border-accent bg-accent-soft text-accent-strong"
        : "border-line bg-surface hover:bg-surface-sunken",
    );
  return (
    <div
      id={DETAIL_ID}
      className="rounded-lg border border-line bg-surface p-4 shadow-[var(--shadow-float)]"
    >
      <div className="mb-2 flex items-center gap-2">
        <Chip tone={partTone(task.part_no)}>{task.part_no}</Chip>
        <h4 className="min-w-0 flex-1 truncate font-semibold">{title}</h4>
        <button
          type="button"
          onClick={onClose}
          aria-label="상세 닫기"
          className="text-subtle hover:text-ink"
        >
          ✕
        </button>
      </div>
      {error && (
        <p role="alert" className="mb-2 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      <PropertyRow label="상태">
        {COLUMNS.map((s) => (
          <button
            key={s}
            type="button"
            disabled={locked}
            className={seg(task.status === s)}
            onClick={() => onPatch({ status: s })}
          >
            <span className="flex items-center gap-1">
              <StatusIcon status={s} />
              {PILL_LABELS[s]}
            </span>
          </button>
        ))}
      </PropertyRow>
      <PropertyRow label="담당">
        {(["candidate", "colleague", "both"] as Assignee[]).map((a) => (
          <button
            key={a}
            type="button"
            disabled={locked}
            className={seg(task.assignee === a)}
            onClick={() => onPatch({ assignee: a })}
          >
            {assigneeWord(a, snap.persona)}
          </button>
        ))}
      </PropertyRow>
      <PropertyRow label="언제까지">
        {duePresets(nowMin, sessionMinutes).map((p) => (
          <button
            key={p.label}
            type="button"
            disabled={locked}
            className={seg(task.due_min === p.due_min)}
            onClick={() => onPatch({ due_min: p.due_min })}
          >
            {p.label} <span className="text-subtle">{clock(p.due_min)}</span>
          </button>
        ))}
        <span className="flex items-center gap-1">
          <input
            value={custom}
            onChange={(event) => setCustom(event.target.value)}
            placeholder="01:30"
            aria-label="언제까지 직접 입력(세션 시각)"
            disabled={locked}
            className="w-16 rounded-md border border-line px-2 py-1 text-sm tabular-nums"
          />
          <Button
            size="xs"
            variant="secondary"
            disabled={locked || customMin == null}
            onClick={() => customMin != null && onPatch({ due_min: customMin })}
          >
            적용
          </Button>
        </span>
        {task.due_min != null && (
          <button
            type="button"
            disabled={locked}
            className="text-xs text-subtle hover:text-ink"
            onClick={() => onPatch({ due_min: null })}
          >
            지우기
          </button>
        )}
      </PropertyRow>
      {/* 의존·순서는 카드에도 배지로 보이므로 접어 둔다. 상세가 길어져 칸을 밀어내지 않게 */}
      <details className="group mt-1 border-t border-line pt-1">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 py-1.5 text-sm text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
          <span aria-hidden className="inline-block transition-transform group-open:rotate-90">
            ›
          </span>
          의존 · 순서
          {(waiting.length > 0 || task.depends_on.length > 0) && (
            <Chip tone="warning">{waiting.length + task.depends_on.length}</Chip>
          )}
        </summary>
        <PropertyRow label="의존">
          {waiting.length > 0 && (
            <Chip tone="warning">{waiting.join("·")}번이 이 카드를 기다림</Chip>
          )}
          {task.depends_on.length
            ? task.depends_on.map((d) => (
                <Chip key={d} tone="warning">
                  {d}번 필요
                </Chip>
              ))
            : waiting.length === 0 && <span className="pt-1 text-sm text-subtle">없음</span>}
          {task.depends_on.length > 0 && (
            <span className="w-full text-xs text-subtle">
              {task.depends_on.join("·")}번 자료를 받아 이어 쓰기
            </span>
          )}
        </PropertyRow>
        <PropertyRow label="순서">
          <span className="pt-1 text-sm tabular-nums">
            {PILL_LABELS[task.status]} 칸 {task.order}번째 · 끌어서 변경
          </span>
        </PropertyRow>
      </details>
    </div>
  );
}

export function Board({
  snap,
  titles,
  nowMin,
  sessionMinutes,
  locked,
  errors,
  onPatch,
  onMove,
}: {
  snap: StateSnapshot;
  titles: Record<number, string>;
  nowMin: number;
  sessionMinutes: number;
  locked: boolean;
  /** 파트별 거절 사유(422 문장 그대로) */
  errors: Record<number, string>;
  onPatch: (part: number, patch: Partial<Task>) => void;
  onMove: (patches: MovePatch[]) => void;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  // 끄는 동안의 칸 배치(놓으면 서버 값으로 돌아간다)
  const [dragging, setDragging] = useState<Record<TaskStatus, Task[]> | null>(null);
  const serverColumns = columnsOf(snap.tasks);
  const columns = dragging ?? serverColumns;
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  // 422가 온 카드는 상세를 열어 문장을 보여 준다
  const errorPart = Object.keys(errors).map(Number).at(-1);
  const [seenError, setSeenError] = useState(errorPart);
  if (errorPart !== seenError) {
    setSeenError(errorPart);
    if (errorPart != null) setSelected(errorPart);
  }

  const statusOf = (id: string | number, cols: Record<TaskStatus, Task[]>): TaskStatus | null => {
    if (typeof id === "string" && id.startsWith("col-")) return id.slice(4) as TaskStatus;
    return COLUMNS.find((s) => cols[s].some((t) => t.part_no === id)) ?? null;
  };

  const onDragOver = ({ active, over }: DragOverEvent) => {
    if (!over) return;
    const cols = dragging ?? columnsOf(snap.tasks);
    const from = statusOf(active.id, cols);
    const to = statusOf(over.id, cols);
    if (!from || !to || from === to) return;
    const task = cols[from].find((t) => t.part_no === active.id)!;
    const next = {
      ...cols,
      [from]: cols[from].filter((t) => t.part_no !== active.id),
      [to]: [...cols[to], { ...task, status: to }],
    };
    setDragging(next);
  };

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    const cols = dragging ?? columnsOf(snap.tasks);
    setDragging(null);
    if (!over) return;
    const to = statusOf(over.id, cols);
    if (!to) return;
    const index = dropIndex(cols[to], Number(active.id), over.id);
    const patches = moveTask(snap.tasks, Number(active.id), to, index);
    if (patches.length) onMove(patches);
  };

  const filled = snap.tasks.filter((t) => t.assignee).length;
  const selectedTask = snap.tasks.find((t) => t.part_no === selected);

  return (
    // 넓으면 카드 상세를 칸 옆에 둔다(상세를 열어도 칸이 아래로 밀리지 않게)
    <div className="@container flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-center gap-2">
        {snap.division ? (
          <p className="min-w-0 flex-1 rounded-md bg-success-soft px-3 py-2 text-sm text-ink">
            {divisionLine(snap.division.parts, snap.division.decided_by, snap.persona)} · 재배정
            가능
          </p>
        ) : (
          <p className="min-w-0 flex-1 rounded-md bg-surface-sunken px-3 py-2 text-sm text-muted">
            담당 {filled}/5 · 5장을 모두 채우면 분업 확정
          </p>
        )}
        <ul aria-label="상태별 카드 수" className="flex shrink-0 items-center gap-1.5">
          {COLUMNS.map((status) => (
            <li key={status} className="flex items-center gap-1">
              <StatusPill status={status} />
              <span className="text-sm font-semibold tabular-nums">
                {serverColumns[status].length}
              </span>
            </li>
          ))}
        </ul>
      </div>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragOver={onDragOver}
        onDragEnd={onDragEnd}
        onDragCancel={() => setDragging(null)}
      >
        <div
          className={cn(
            "flex flex-col gap-3",
            selectedTask &&
              "@min-[1040px]:grid @min-[1040px]:grid-cols-[minmax(0,1fr)_340px] @min-[1040px]:items-start",
          )}
        >
          <div className="@container/cols">
            <div className="flex flex-col gap-3 @min-[680px]/cols:grid @min-[680px]/cols:grid-cols-3 @min-[680px]/cols:items-start">
              {COLUMNS.map((status) => (
                <Column key={status} status={status} count={columns[status].length}>
                  <SortableContext
                    items={columns[status].map((t) => t.part_no)}
                    strategy={verticalListSortingStrategy}
                  >
                    <ul className="flex min-h-10 flex-col gap-1.5">
                      {columns[status].map((task) => (
                        <BoardCard
                          key={task.part_no}
                          task={task}
                          title={titles[task.part_no] ?? ""}
                          snap={snap}
                          locked={locked}
                          selected={selected === task.part_no}
                          onSelect={() =>
                            setSelected(selected === task.part_no ? null : task.part_no)
                          }
                          onAssign={(assignee) => onPatch(task.part_no, { assignee })}
                        />
                      ))}
                      {columns[status].length === 0 && (
                        <li className="rounded-md border border-dashed border-line px-3 py-2 text-xs text-muted">
                          여기로 끌어 놓기
                        </li>
                      )}
                    </ul>
                  </SortableContext>
                </Column>
              ))}
            </div>
          </div>
          {selectedTask && (
            <div className="@min-[1040px]:sticky @min-[1040px]:top-0">
              <CardDetail
                task={selectedTask}
                title={titles[selectedTask.part_no] ?? ""}
                snap={snap}
                nowMin={nowMin}
                sessionMinutes={sessionMinutes}
                locked={locked}
                error={errors[selectedTask.part_no] ?? null}
                onPatch={(patch) => onPatch(selectedTask.part_no, patch)}
                onClose={() => setSelected(null)}
              />
            </div>
          )}
        </div>
      </DndContext>
    </div>
  );
}
