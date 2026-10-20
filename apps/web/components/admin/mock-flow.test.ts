import { beforeEach, expect, test } from "vitest";

import type { Candidate, Report } from "@/components/admin/types";

import { resetAdminMock } from "@/mocks/admin";
import { mockRequest } from "@/mocks";

const call = <T>(method: string, path: string, body?: unknown) =>
  mockRequest<T>(method, path, body);
const code = (promise: Promise<unknown>) =>
  promise.then(
    () => null,
    (e: { code?: string }) => e.code ?? null,
  );

beforeEach(resetAdminMock);

test("가입→생성(요소 0·5개 거부)→초대→목록→조정(메모 필수)→검토 완료→reviewed가 mock으로 돈다", async () => {
  await expect(
    call("POST", "/admin/auth/signup", { email: "a@b.c", password: "x", company_name: "c" }),
  ).resolves.toHaveProperty("token");
  expect(
    await code(
      call("POST", "/admin/auth/signup", {
        email: "taken@example.com",
        password: "x",
        company_name: "c",
      }),
    ),
  ).toBe("conflict");

  const ids = ["cooperation", "responsibility", "flexibility", "respect"];
  expect(await code(call("POST", "/admin/positions", { name: "n", elements: [] }))).toBe(
    "invalid_elements",
  );
  expect(
    await code(call("POST", "/admin/positions", { name: "n", elements: [...ids, "extra"] })),
  ).toBe("invalid_elements");
  const created = await call<{ id: string }>("POST", "/admin/positions", {
    name: "새 채용",
    elements: ids.slice(0, 2),
  });

  const invite = await call<{ invite_url: string }>(
    "POST",
    `/admin/positions/${created.id}/invites`,
    { alias: "지원자Z", email: "z@example.com" },
  );
  expect(invite.invite_url).toContain("/s/");
  const mine = await call<Candidate[]>("GET", `/admin/positions/${created.id}/candidates`);
  expect(mine.map((c) => c.display_status)).toEqual(["invited"]);

  const list = await call<Candidate[]>("GET", "/admin/positions/pos-1/candidates");
  expect(new Set(list.map((c) => c.display_status)).size).toBeGreaterThanOrEqual(7);

  const url = "/admin/sessions/s-ready";
  const report = await call<Report>("GET", `${url}/report`);
  expect(report.stage).toBe("draft");
  expect(
    await code(
      call("POST", `${url}/review`, {
        adjustments: [{ item_id: "coop_replied_within_5m", value: 1, memo: "" }],
      }),
    ),
  ).toBe("memo_required");

  const body = {
    adjustments: [{ item_id: "coop_replied_within_5m", value: 1, memo: "표시 시각만 늦었음" }],
  };
  expect(await call("POST", `${url}/review`, body)).toEqual({ status: "approving" });
  expect(await call("POST", `${url}/review`, body)).toEqual({ status: "approving" });
  expect(await code(call("POST", `${url}/review`, { adjustments: [] }))).toBe("already_reviewed");

  let polled = await call<Report>("GET", `${url}/report`);
  expect(polled.rubric.review).not.toBeNull();
  polled = await call<Report>("GET", `${url}/report`);
  expect(polled.stage).toBe("final");
  expect(polled.rubric.reviewer_total).toEqual({ met: 6, judged: 7, no_record: 1 });
  expect(polled.rubric.history).toHaveLength(1);
  expect(await call("POST", `${url}/review`, body)).toEqual({ status: "reviewed" });
  const row = (await call<Candidate[]>("GET", "/admin/positions/pos-1/candidates")).find(
    (c) => c.session_id === "s-ready",
  );
  expect(row?.display_status).toBe("reviewed");
});

test("reviewed로 시작한 세션은 조회만으로 되돌아가지 않고, 다시 초대하면 이전 응시가 연결된다", async () => {
  const first = await call<Report>("GET", "/admin/sessions/s-reviewed/report");
  expect(first.stage).toBe("final");
  expect(first.rubric.history.length).toBeGreaterThan(0);
  const before = (await call<Candidate[]>("GET", "/admin/positions/pos-1/candidates")).find(
    (c) => c.session_id === "s-reviewed",
  );
  expect(before?.display_status).toBe("reviewed");

  await call("POST", "/admin/positions/pos-1/invites", {
    alias: "지원자I",
    email: "i@example.com",
    previous_session_id: "s-failed",
  });
  const list = await call<Candidate[]>("GET", "/admin/positions/pos-1/candidates");
  expect(list.at(-1)?.previous_session_id).toBe("s-failed");
});
