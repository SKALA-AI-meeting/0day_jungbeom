// 리포트 검토 계산: 단계 판정, 차원 단위 조정(메모 필수), 조정 반영 요소 수준, 전체 기록 앵커.
import type {
  Adjustment,
  Dimension,
  Level,
  NoRecordReason,
  RecordRef,
  Report,
  ReviewBody,
} from "./types";

export type Phase = "draft" | "approving" | "final";

/** review가 있으면 검토 제출 뒤(확정 중), stage final이면 검토 완료 */
export function phaseOf(report: Report): Phase {
  if (report.stage === "final") return "final";
  return report.review ? "approving" : "draft";
}

export const PHASE_LABEL: Record<Phase, string> = {
  draft: "검토 대기",
  approving: "확정 중",
  final: "검토 완료",
};

/** 화면에서 고친 차원 하나. level null이면 reason(기록 없음 사유)이 있어야 저장할 수 있다 */
export type Edit = { level: Level | null; reason: NoRecordReason | null; memo: string };
export type Edits = Record<string, Edit>;

export function isAdjusted(d: Dimension) {
  return d.adjusted_level != null || d.adjusted_no_record_reason != null;
}

/** 차원 최종값: 조정 행이 있으면 그 값, 없으면 자동 값 */
export function finalOf(d: Dimension): { level: Level | null; reason: NoRecordReason | null } {
  if (isAdjusted(d)) return { level: d.adjusted_level, reason: d.adjusted_no_record_reason };
  return { level: d.level, reason: d.no_record_reason };
}

/** 메모가 비었거나 기록 없음인데 사유가 없으면 저장할 수 없다 */
export function editProblem(edit: Edit): string | null {
  if (edit.level == null && !edit.reason) return "기록 없음 사유를 고르세요.";
  if (!edit.memo.trim()) return "메모를 적어야 저장할 수 있습니다.";
  return null;
}

/** 화면 편집 + 서버에 이미 병합된 조정을 차원별 최종값으로 */
export function withEdits(dimensions: Dimension[], edits: Edits): Dimension[] {
  return dimensions.map((d) => {
    const edit = edits[d.dimension_id];
    if (!edit) return d;
    return {
      ...d,
      adjusted_level: edit.level,
      adjusted_no_record_reason: edit.level == null ? edit.reason : null,
      adjust_memo: edit.memo.trim(),
    };
  });
}

/** 요소 수준 = 수준이 있는 차원 평균을 반올림(.5 올림), 모두 기록 없음이면 null(contracts.md elements[]) */
export function elementLevel(dimensions: Dimension[], element: string, final = true): Level | null {
  const levels = dimensions
    .filter((d) => d.element === element)
    .map((d) => (final ? finalOf(d).level : d.level))
    .filter((l): l is Level => l != null);
  if (levels.length === 0) return null;
  const mean = levels.reduce((a, b) => a + b, 0) / levels.length;
  return Math.floor(mean + 0.5) as Level;
}

/** 조정 본문: 화면에서 고친 차원만, 메모는 앞뒤 공백 제거 */
export function adjustmentsOf(edits: Edits): Adjustment[] {
  return Object.entries(edits).map(([dimension_id, e]) =>
    e.level == null
      ? { dimension_id, level: null, no_record_reason: e.reason ?? undefined, memo: e.memo.trim() }
      : { dimension_id, level: e.level, memo: e.memo.trim() },
  );
}

/**
 * 확정 중(approving) 리포트의 검토 본문을 서버 값으로 되살린다. "확정 다시 시도"는 처음 제출과
 * 같은 본문을 보내야 200 멱등이 된다(다르면 409 already_reviewed).
 */
export function reviewBodyFrom(report: Report): ReviewBody | null {
  if (!report.review) return null;
  const adjustments: Adjustment[] = report.dimensions.filter(isAdjusted).map((d) =>
    d.adjusted_level != null
      ? { dimension_id: d.dimension_id, level: d.adjusted_level, memo: d.adjust_memo ?? "" }
      : {
          dimension_id: d.dimension_id,
          level: null,
          no_record_reason: d.adjusted_no_record_reason ?? undefined,
          memo: d.adjust_memo ?? "",
        },
  );
  return { adjustments, reviewer_name: report.review.reviewer_name };
}

/** 전체 기록 화면의 줄 앵커. 리포트 근거의 record_ref와 기록의 ref가 같은 값이다 */
export function recordAnchor(ref: RecordRef) {
  return `${ref.type}-${ref.id}`;
}
