import { expect, test } from "vitest";

import { savedLabel } from "./proposal-editor";

test("저장 표시는 실제 시계 없이 상대 표기만 쓴다", () => {
  const t = Date.UTC(2026, 9, 21, 8, 26, 9);
  expect(savedLabel(t, t + 10_000)).toBe("방금 저장됨");
  expect(savedLabel(t, t + 3 * 60_000)).toBe("3분 전 저장됨");
  expect(savedLabel(t, t + 2 * 3_600_000)).toBe("저장됨");
});
