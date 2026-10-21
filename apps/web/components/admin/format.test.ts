// 완료 기준: 판단 실패 차원은 시스템 오류가 아니라 판단 보류로 보이고, 다른 사유 문구는 그대로다.
import { expect, test } from "vitest";

import { NO_RECORD_TEXT } from "./format";

test("evaluate_failed는 판단 보류 문구, 나머지 사유는 기존 문구", () => {
  expect(NO_RECORD_TEXT.evaluate_failed).toBe("판단 보류 · 근거 부족 — 원문 기록 확인 권장");
  expect(NO_RECORD_TEXT.no_activity).toBe("지원자 활동 없음");
  expect(Object.values(NO_RECORD_TEXT).join()).not.toContain("시스템:");
});
