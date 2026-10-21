// 완료 기준: 리포트가 아직 없을 때(404 not_found) 안내 + 자동 재조회 대상으로 보고, 다른 오류는 그대로 오류로 둔다.
import { expect, test } from "vitest";

import { REPORT_POLL_MS, reportNotReady } from "./review";

test("리포트 404 not_found는 만드는 중으로 보고 5초마다 다시 읽는다", () => {
  expect(reportNotReady("not_found")).toBe(true);
  expect(reportNotReady("unauthorized")).toBe(false);
  expect(reportNotReady(null)).toBe(false);
  expect(REPORT_POLL_MS).toBe(5000);
});
