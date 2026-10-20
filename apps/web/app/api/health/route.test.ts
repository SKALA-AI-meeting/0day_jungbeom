// 완료 기준: web /api/health 응답.
import { expect, test } from "vitest";

import { GET } from "./route";

test("GET /api/health returns ok", async () => {
  const response = GET();
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ status: "ok" });
});
