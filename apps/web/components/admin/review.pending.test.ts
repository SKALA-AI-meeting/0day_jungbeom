// 완료 기준: 리포트가 아직 없을 때(404 not_found) 안내 + 자동 재조회 대상으로 보고, 다른 오류는 그대로 오류로 둔다.
import { expect, test } from "vitest";

import {
  nextWaiting,
  pollDelay,
  REPORT_POLL_MS,
  reportFailed,
  reportMissing,
  reportNotReady,
  reportScreen,
  reportTransient,
} from "./review";

test("리포트 409 report_not_ready는 만드는 중으로 보고 5초마다 다시 읽는다", () => {
  expect(reportNotReady("report_not_ready")).toBe(true);
  expect(reportNotReady("not_found")).toBe(false);
  expect(reportNotReady("unauthorized")).toBe(false);
  expect(reportNotReady(null)).toBe(false);
  expect(REPORT_POLL_MS).toBe(5000);
});

test("리포트 조회 오류 코드를 생성 중·실패·없음으로 나눈다", () => {
  expect(reportFailed("report_failed")).toBe(true);
  expect(reportFailed("report_not_ready")).toBe(false);
  expect(reportMissing("not_found")).toBe(true);
  expect(reportMissing("report_failed")).toBe(false);
});

test("확정 중 report_failed·report_not_ready가 와도 이전 리포트에 가려지지 않는다", () => {
  const previous = { stage: "draft" };
  expect(reportScreen(previous, "report_failed", false)).toBe("failed");
  expect(reportScreen(previous, "report_not_ready", false)).toBe("generating");
  expect(reportScreen(previous, null, false)).toBe("report");
  expect(reportScreen(null, "not_found", false)).toBe("missing");
});

test("생성 중 폴링은 일시 오류(503·네트워크)에서 이어지고 성공·실패·없음에서 끝난다", () => {
  let waiting = nextWaiting(false, "생성 중", "report_not_ready");
  expect(waiting).toBe(true);
  waiting = nextWaiting(waiting, "서버 오류", "http_error"); // 503 한 번
  expect(waiting).toBe(true);
  expect(reportScreen(null, "http_error", waiting)).toBe("generating");
  expect(reportTransient("서버 오류", "http_error")).toBe(true);
  expect(reportTransient("실패", "report_failed")).toBe(false);
  expect(nextWaiting(waiting, "실패", "report_failed")).toBe(false);
  expect(nextWaiting(waiting, null, null)).toBe(false);
  expect(nextWaiting(false, "서버 오류", "http_error")).toBe(false);
  expect(pollDelay(1)).toBe(5000);
  expect(pollDelay(64)).toBe(40000);
});
