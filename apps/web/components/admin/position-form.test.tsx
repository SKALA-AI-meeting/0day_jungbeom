// 완료 기준(관리자 1): 생성 화면에 미션 1개와 요소 5개 카드(기본 전체 선택, 뺐을 때 차이 한 줄), 0개·6개 거부, 샘플 리포트 링크.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, test } from "vitest";

import { mockRequest } from "@/mocks";
import { resetAdminMock } from "@/mocks/admin";
import catalogJson from "@/mocks/fixtures/admin_catalog.json";

import { PositionForm, SAME_BASIS_LINE, unselectedLines } from "./position-form";
import type { Catalog } from "./types";

const catalog = catalogJson as unknown as Catalog;

beforeEach(resetAdminMock);

test("생성 화면: 미션 표시, 요소 5장 전체 선택, 뺀 요소의 차이 한 줄, 0개·6개 거부, 샘플 링크", async () => {
  const html = renderToStaticMarkup(<PositionForm catalog={catalog} onSubmit={() => {}} />);
  expect(html).toContain("모아런 재참여율 개선 기획");
  expect(html.match(/checked=""/g)).toHaveLength(5);
  expect(html).not.toContain("(선택)");
  expect(html).toContain(SAME_BASIS_LINE);
  expect(html).toContain('href="/admin/sample-report"');
  // 상황(카드)·평가표 항목은 보여 주지 않는다
  expect(html).not.toMatch(/내 자료 지연|중간 점검|평가표/);

  expect(
    unselectedLines(catalog, ["planning", "adaptability", "collaboration", "honesty"]),
  ).toEqual([
    {
      id: "responsibility",
      line: catalog.elements.find((e) => e.id === "responsibility")!.if_unselected,
    },
  ]);

  const code = (elements: string[]) =>
    mockRequest("POST", "/admin/positions", { name: "x", elements }).then(
      () => null,
      (e: { code: string }) => e.code,
    );
  expect(await code([])).toBe("invalid_elements");
  expect(await code([...catalog.elements.map((e) => e.id), "honesty"])).toBe("invalid_elements");
  expect(await code(["planning"])).toBeNull();
});
