// 완료 기준(A3): 리포트 조회의 네 응답(리포트·404·생성 중 409·실패 409)을 구분하고,
// 실패 뒤 다시 만들기가 성공하면 생성 중 폴링을 거쳐 리포트가 열린다.
import { beforeEach, expect, test } from "vitest";

import { ApiError } from "@/lib/api";
import { adminMockRequest, resetAdminMock } from "@/mocks/admin";

import { errorCode, errorExtra } from "./client";
import { reportFailed, reportMissing, reportNotReady } from "./review";

const get = (id: string) => adminMockRequest("GET", `/admin/sessions/${id}/report`);

async function caught(promise: Promise<unknown>) {
  try {
    await promise;
  } catch (error) {
    // lib/api.ts의 mock 경로와 같은 변환
    const e = error as {
      status: number;
      code: string;
      message: string;
      extra?: Record<string, unknown>;
    };
    return new ApiError(e.status, e.code, e.message, e.extra);
  }
  throw new Error("오류가 나야 한다");
}

beforeEach(() => resetAdminMock());

test("조회 응답을 리포트·없음·실패로 나누고 실패 지점을 읽는다", async () => {
  expect(await get("sess-1")).toHaveProperty("session_id");
  const missing = await caught(get("nope"));
  expect(reportMissing(errorCode(missing))).toBe(true);
  const failed = await caught(get("sess-7"));
  expect(reportFailed(errorCode(failed))).toBe(true);
  expect(errorExtra(failed).failed_step).toBe("draft");
});

test("다시 만들기가 성공하면 생성 중 409를 거쳐 리포트가 열린다", async () => {
  const result = await adminMockRequest("POST", "/admin/sessions/sess-7/report/regenerate");
  expect(result).toEqual({ status: "completed" });
  for (let i = 0; i < 2; i += 1) {
    expect(reportNotReady(errorCode(await caught(get("sess-7"))))).toBe(true);
  }
  expect(await get("sess-7")).toHaveProperty("session_id");
});
