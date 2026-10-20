// 리포트 검토 계산: 단계 판정, 담당자 조정(바꾸면 메모 필수), 조정 반영 합계, 전체 기록 링크.
import type { Adjustment, Catalog, Counts, RecordRef, Report, RubricItem } from "./types";

export type Phase = "draft" | "approving" | "final";

/** review가 있으면 검토 제출 뒤(확정 중), stage final이면 검토 완료 */
export function phaseOf(report: Report): Phase {
  if (report.stage === "final") return "final";
  return report.rubric.review ? "approving" : "draft";
}

export type Choice = "auto" | "1" | "0" | "null";
export type Edits = Record<string, { choice: Choice; memo: string }>;

const value = (choice: Exclude<Choice, "auto">): 1 | 0 | null =>
  choice === "1" ? 1 : choice === "0" ? 0 : null;

export function allItems(report: Report): RubricItem[] {
  return report.rubric.elements.flatMap((e) => e.cards.flatMap((c) => c.items));
}

/** 자동 값과 다른 선택만 조정으로 보낸다 */
export function changedAdjustments(report: Report, edits: Edits): Adjustment[] {
  const items = new Map(allItems(report).map((i) => [i.id, i]));
  return Object.entries(edits).flatMap(([id, edit]) => {
    const item = items.get(id);
    if (!item || edit.choice === "auto" || value(edit.choice) === item.auto) return [];
    return [{ item_id: id, value: value(edit.choice), memo: edit.memo.trim() }];
  });
}

export function missingMemos(adjustments: Adjustment[]) {
  return adjustments.filter((a) => !a.memo).map((a) => a.item_id);
}

/** 항목의 최종 값: 조정됐으면 담당자 값(null 포함), 아니면 자동 값 */
export function finalValue(item: RubricItem) {
  return item.adjusted ? item.reviewer : item.auto;
}

export function countOf(values: (1 | 0 | null)[]): Counts {
  return {
    met: values.filter((v) => v === 1).length,
    unmet: values.filter((v) => v === 0).length,
    no_record: values.filter((v) => v === null).length,
  };
}

/** 저장 전 조정을 반영한 합계 미리보기 */
export function previewTotal(report: Report, adjustments: Adjustment[]): Counts {
  const changed = new Map(adjustments.map((a) => [a.item_id, a.value]));
  return countOf(
    allItems(report).map((i) => (changed.has(i.id) ? changed.get(i.id)! : finalValue(i))),
  );
}

/** 전체 기록 화면의 줄 앵커. 리포트 근거의 record_ref와 기록의 ref가 같은 값이다 */
export function recordAnchor(ref: RecordRef) {
  return `${ref.type}-${ref.id}`;
}

/**
 * 확정 중(approving) 리포트의 검토 본문을 서버 값으로 되살린다. 리포트에 다시 들어와 "확정 다시 시도"를 누를 때
 * 처음 제출과 같은 본문을 보내야 200 멱등이 된다(다르면 409 already_reviewed).
 */
export function reviewBodyFrom(report: Report) {
  if (!report.rubric.review) return null;
  const adjustments: Adjustment[] = allItems(report)
    .filter((i) => i.adjusted)
    .map((i) => ({ item_id: i.id, value: i.reviewer, memo: i.memo ?? "" }));
  return {
    adjustments,
    ...(report.rubric.review.memo ? { memo: report.rubric.review.memo } : {}),
    reviewer_name: report.rubric.review.reviewer_name,
  };
}

/** 리포트 미션의 회사 문서 id → 이름(카탈로그 missions[].documents) */
export function docTitlesOf(catalog: Catalog | null, missionId: string): Record<string, string> {
  const mission = catalog?.missions.find((m) => m.id === missionId);
  return Object.fromEntries((mission?.documents ?? []).map((d) => [d.doc_id, d.title]));
}
