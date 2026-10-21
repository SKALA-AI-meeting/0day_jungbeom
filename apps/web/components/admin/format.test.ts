// 완료 기준: 판단 실패 차원은 시스템 오류가 아니라 판단 보류로 보이고, 다른 사유 문구는 그대로다.
import { expect, test } from "vitest";

import { NO_RECORD_TEXT, readableSummary } from "./format";

test("evaluate_failed는 판단 보류 문구, 나머지 사유는 기존 문구", () => {
  expect(NO_RECORD_TEXT.evaluate_failed).toBe("판단 보류 · 근거 부족 — 원문 기록 확인 권장");
  expect(NO_RECORD_TEXT.no_activity).toBe("지원자 활동 없음");
  expect(Object.values(NO_RECORD_TEXT).join()).not.toContain("시스템:");
});

test("기록 요약 끝의 outcome 토큰을 표시 글자로 바꾼다", () => {
  expect(readableSummary("keyword 확정: 물 (consensus)")).toBe("키워드 확정: 물 · 합의");
  expect(readableSummary("problem 확정: 폭우 (candidate_decision)")).toBe(
    "문제 상황 확정: 폭우 · 지원자 결정",
  );
  expect(readableSummary("solution 확정: 경보 (timeout)")).toBe("해결책 확정: 경보 · 시간 초과");
});
