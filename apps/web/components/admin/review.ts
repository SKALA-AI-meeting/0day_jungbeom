// 리포트 화면의 조정 입력 규칙. 서버(POST /review)와 같은 기준으로 메모 필수를 먼저 막는다.
import type { Adjustment, ItemValue, Report, Tally } from "./types";

/** keep = 자동 값 유지(조정 없음) */
export type Choice = "keep" | "1" | "0" | "null";
export type DraftEntry = { choice: Choice; memo: string };
export type Draft = Record<string, DraftEntry>;

export type Phase = "draft" | "approving" | "final";

/** stage가 final이면 확정, 아직 draft인데 review가 채워졌으면 확정 중(approving), 아니면 검토 대기. */
export function phaseOf(report: Report): Phase {
  if (report.stage === "final") return "final";
  return report.rubric.review ? "approving" : "draft";
}

function toValue(choice: Choice): ItemValue | undefined {
  if (choice === "keep") return undefined;
  return choice === "null" ? null : (Number(choice) as 0 | 1);
}

/** 값을 바꾼 항목만 {item_id, value, memo}로. 자동 값과 같은 선택은 조정이 아니다. */
export function changedAdjustments(report: Report, draft: Draft): Adjustment[] {
  const rows: Adjustment[] = [];
  for (const element of report.rubric.elements) {
    for (const item of element.items) {
      const entry = draft[item.id];
      const value = entry ? toValue(entry.choice) : undefined;
      if (value === undefined || value === item.auto) continue;
      rows.push({ item_id: item.id, value, memo: entry.memo.trim() });
    }
  }
  return rows;
}

/** 메모가 비어 있는 조정 항목의 id */
export function missingMemos(adjustments: Adjustment[]): string[] {
  return adjustments.filter((a) => !a.memo).map((a) => a.item_id);
}

/** 조정을 반영해 센 담당자 합계(제출 전 미리보기) */
export function previewTotal(report: Report, adjustments: Adjustment[]): Tally {
  const byItem = new Map(adjustments.map((a) => [a.item_id, a.value]));
  const values = report.rubric.elements.flatMap((e) =>
    e.items.map((i) => (byItem.has(i.id) ? (byItem.get(i.id) as ItemValue) : i.auto)),
  );
  return {
    met: values.filter((v) => v === 1).length,
    judged: values.filter((v) => v !== null).length,
    no_record: values.filter((v) => v === null).length,
  };
}
