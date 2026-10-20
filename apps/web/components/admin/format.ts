// 관리자 화면 표기 규칙: 시각, 세 수 점수, 기록 없음 사유 문장(docs/common/rubric.md), 삭제 예정일.
import type { Counts, NoRecordReason } from "./types";

const dateTime = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const dateOnly = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  month: "long",
  day: "numeric",
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "–" : dateTime.format(date);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "–" : dateOnly.format(date);
}

/** "12월 19일 삭제 예정"(세션 종료 + 90일) */
export function purgeText(iso: string | null | undefined) {
  return iso ? `${formatDate(iso)} 삭제 예정` : null;
}

/** 세 수를 나란히, 분모·비율 없이: "충족 9 · 미충족 3 · 기록 없음 2" */
export function countsText(c: Counts): string {
  return `충족 ${c.met} · 미충족 ${c.unmet} · 기록 없음 ${c.no_record}`;
}

/** 기록 없음 사유 → 책임 주체가 보이는 문장 */
export const NO_RECORD_TEXT: Record<NoRecordReason, string> = {
  no_activity: "지원자 활동 없음",
  classify_failed: "시스템: 분류 실패",
  window_missed: "시스템: 메시지 지연",
  document_missing: "시스템: 문서 미제공",
  not_applicable: "해당 없음",
  event_not_fired: "이벤트 미발생(조기 제출)",
};

/** 세션 분 → "62분" / "31.2분" */
export function minText(t: number) {
  return `${Number.isInteger(t) ? t : t.toFixed(1)}분`;
}

/** 세션 시각(세션 시작부터) → "01:30". 오피스 화면과 같은 표기 */
export function sessionClock(t: number) {
  const total = Math.max(0, Math.floor(t));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
