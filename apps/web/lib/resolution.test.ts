import { expect, test } from "vitest";

import { resolutionLabel } from "./resolution";

test("outcome이 표시를 정한다", () => {
  expect(resolutionLabel({ resolution: "consensus", outcome: "consensus" })).toBe("합의");
  expect(resolutionLabel({ resolution: "consensus", outcome: "candidate_decision" })).toBe(
    "지원자 결정",
  );
  expect(resolutionLabel({ resolution: "timeout", outcome: "timeout" })).toBe("시간 초과");
});

test("outcome이 없으면 timeout만 시간 초과이고 나머지는 라벨이 없다", () => {
  expect(resolutionLabel({ resolution: "consensus" })).toBeNull();
  expect(resolutionLabel({ resolution: "consensus", outcome: null })).toBeNull();
  expect(resolutionLabel({ resolution: "timeout" })).toBe("시간 초과");
});
