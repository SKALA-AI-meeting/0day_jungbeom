// 오피스 문구 도우미: 사람 이름, 파트 이름, 세션 시각, SystemLine 문장(design.md "SystemLine 종류").
import type { Assignee, Channel, Sender, StateSnapshot, Task, TaskStatus } from "./types";

export type LineKind =
  "presence" | "board" | "division" | "release" | "gap" | "report_guide" | "submitted" | "deadline";

/** 대화 사이에 끼는 얇은 시스템 줄. channel "all"은 모든 대화에 보인다. */
export type SysLine = {
  id: string;
  channel: Channel | "all";
  t_min: number;
  kind: LineKind;
  text: string;
};

export type Persona = StateSnapshot["persona"];

/** "이도현" → "도현", "한서윤 팀장" → "서윤". 한국어 세 글자 이름은 성을 뗀다. */
export function givenName(full: string) {
  const name = full.split(" ")[0];
  return name.length === 3 ? name.slice(1) : name;
}

export function personName(sender: Sender, persona: Persona, alias = "나") {
  if (sender === "manager") return persona.manager.split(" ")[0];
  if (sender === "colleague") return persona.colleague;
  if (sender === "candidate") return alias;
  return "Day Zero";
}

export function assigneeWord(assignee: Assignee | null, persona: Persona) {
  const colleague = givenName(persona.colleague);
  if (assignee === "candidate") return "나";
  if (assignee === "colleague") return colleague;
  if (assignee === "both") return `나 + ${colleague}`;
  return "담당 없음";
}

export const STATUS_WORD: Record<TaskStatus, string> = {
  todo: "할 일",
  doing: "진행 중",
  done: "완료",
};

/** 세션 분 → "01:10" */
export function clock(tMin: number) {
  const total = Math.max(0, Math.floor(tMin));
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** 남은 초 → "01:23:40" */
export function countdown(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const mm = `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  return h > 0 ? `${String(h).padStart(2, "0")}:${mm}` : mm;
}

export function partLabel(partNo: number, titles: Record<number, string>) {
  return `${partNo}. ${titles[partNo] ?? ""}`.trim();
}

/** "분업이 정해졌어요: 1·2 나, 3 같이, 4·5 도현" */
export function divisionLine(
  parts: Record<string, Assignee>,
  decidedBy: "candidate" | "colleague_default",
  persona: Persona,
) {
  const groups: [Assignee, string][] = [
    ["candidate", "나"],
    ["both", "같이"],
    ["colleague", givenName(persona.colleague)],
  ];
  const text = groups
    .map(([who, word]) => {
      const nos = Object.keys(parts)
        .filter((k) => parts[k] === who)
        .map(Number)
        .sort((a, b) => a - b);
      return nos.length ? `${nos.join("·")} ${word}` : null;
    })
    .filter(Boolean)
    .join(", ");
  const suffix = decidedBy === "colleague_default" ? " (기본안)" : "";
  return `분업이 정해졌어요: ${text}${suffix}`;
}

/** 보드 변경 한 줄("3번 → 진행 중 (도현)", "1번 담당 → 나"). 바뀐 필드가 없으면 null */
export function boardLine(
  before: Task | undefined,
  after: Task,
  by: "candidate" | "colleague",
  persona: Persona,
) {
  const label = `${after.part_no}번`;
  const who = by === "colleague" ? ` (${givenName(persona.colleague)})` : "";
  if (!before || before.assignee !== after.assignee) {
    return `${label} 담당 → ${assigneeWord(after.assignee, persona)}${who}`;
  }
  if (before.status !== after.status) return `${label} → ${STATUS_WORD[after.status]}${who}`;
  if (before.due_min !== after.due_min) {
    return after.due_min == null
      ? `${label} 언제까지 지움${who}`
      : `${label} 언제까지 → ${clock(after.due_min)}${who}`;
  }
  return null;
}

/** 이보다 짧은 끊김은 줄을 남기지 않고 토스트로만 알린다(분) */
export const GAP_LINE_MIN = 1;

/** 남은 시간을 단위로: "1시간 23분", "9분 12초", "42초". 01:42처럼 시·분으로 잘못 읽히지 않게 한다 */
export function remainText(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}시간 ${m}분`;
  if (m > 0) return `${m}분 ${r}초`;
  return `${r}초`;
}

export function gapLine(from: number, to: number) {
  return `${clock(from)}~${clock(to)} 연결이 끊겼어요`;
}

export const PRESENCE_LINE = (persona: Persona) =>
  `${persona.manager.split(" ")[0]}님과 ${persona.colleague}님이 들어왔어요`;

export const REPORT_GUIDE = "최종본은 내 문서 탭에서 제출합니다. 제출하면 세션이 끝납니다";
export const SUBMITTED_LINE = "최종본을 보냈어요";
export const WAITING_LINE = "보고를 기다리는 중 (5분 안에 안 써도 제출은 유효합니다)";
export const AUTO_SUBMITTED_LINE =
  "시간이 끝나 지금 상태로 제출됐어요. 마지막으로 팀장에게 한 줄 보고하면 끝납니다.";
export const DEADLINE_10 = "마감 10분 전";
export const DEADLINE_2 = "마감 2분 전, 지금 상태 그대로 제출됩니다";
