// 칸 결과 표시 규칙(contracts.md "칸 결과 표시"): 화면은 api가 내려 주는 outcome만 본다(지지 현황은 계산하지 않는다).
export type Outcome = "consensus" | "candidate_decision" | "timeout";
export type ResolutionLabel = "합의" | "지원자 결정" | "시간 초과";

const LABEL: Record<Outcome, ResolutionLabel> = {
  consensus: "합의",
  candidate_decision: "지원자 결정",
  timeout: "시간 초과",
};

/** outcome이 없으면 resolution=timeout만 "시간 초과"이고, 그 밖은 라벨을 붙이지 않는다(null, 값만 표시) */
export function resolutionLabel(slot: {
  resolution: "consensus" | "timeout";
  outcome?: Outcome | null;
}): ResolutionLabel | null {
  if (slot.outcome) return LABEL[slot.outcome];
  return slot.resolution === "timeout" ? "시간 초과" : null;
}
