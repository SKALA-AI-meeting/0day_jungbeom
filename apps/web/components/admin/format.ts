import type { Tally } from "./types";

const dateTime = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "–" : dateTime.format(date);
}

/** 합계 표기: `9/14 · 기록 없음 2`. 판정된 항목이 없으면 `–/0`. */
export function tallyText(tally: Tally): string {
  const head = tally.judged === 0 ? "–/0" : `${tally.met}/${tally.judged}`;
  return `${head} · 기록 없음 ${tally.no_record}`;
}

/** 기록 없음 사유 코드(docs/common/rubric.md) */
export const NO_RECORD_REASONS: Record<string, string> = {
  no_activity: "지원자 활동 없음",
  classify_failed: "AI 분류 실패",
  event_not_fired: "이벤트 미발생(조기 제출)",
  not_applicable: "해당 조건 아님",
  window_missed: "관찰 창이 끝난 뒤 전달됨",
};
