// 완료 기준(관리자 생성): 이름·세션 길이(60·15)·요소 5개 읽기 전용 안내(선택 UI 없음)·샘플 리포트 링크.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, test } from "vitest";

import { adminMockRequest as mockRequest, resetAdminMock } from "@/mocks/admin";
import catalogJson from "@/mocks/fixtures/admin_catalog.json";

import { PositionForm, SAME_SCALE_NOTICE } from "./position-form";
import type { Catalog } from "./types";

beforeEach(resetAdminMock);

test("생성 화면은 이름·세션 길이만 받고 요소는 안내로만 보인다", () => {
  const html = renderToStaticMarkup(
    <PositionForm catalog={catalogJson as unknown as Catalog} onSubmit={() => {}} />,
  );
  expect(html).toContain("채용 건 이름");
  expect(html).toContain("60분");
  expect(html).toContain("15분 (데모)");
  for (const e of catalogJson.elements) {
    expect(html).toContain(e.name);
    expect(html).toContain(e.how_we_see);
  }
  expect(html).not.toContain('type="checkbox"');
  expect(html).not.toMatch(/role="switch"/);
  expect(html).not.toMatch(/stubborn|quiet|critic|고집형|소극형|비판형/);
  expect(html).toContain(SAME_SCALE_NOTICE);
  expect(html).toContain('href="/admin/sample-report"');
});

test("mock 생성은 elements를 거부하고 세션 길이 60·15만 받는다", async () => {
  await expect(
    mockRequest("POST", "/admin/positions", { name: "x", elements: ["persuasion"] }),
  ).rejects.toMatchObject({ code: "invalid_input" });
  await expect(
    mockRequest("POST", "/admin/positions", { name: "x", session_minutes: 30 }),
  ).rejects.toMatchObject({ code: "invalid_input" });
  const created = await mockRequest<{
    session_minutes: number;
    seats: unknown[];
    keywords: string[];
  }>("POST", "/admin/positions", { name: "데모 채용", session_minutes: 15 });
  expect(created.session_minutes).toBe(15);
  expect(created.seats).toHaveLength(3);
  expect(created.keywords).toHaveLength(4);
});
