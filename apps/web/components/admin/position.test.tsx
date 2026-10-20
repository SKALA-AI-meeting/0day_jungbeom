import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import catalogJson from "@/mocks/fixtures/admin/catalog.json";
import positionsJson from "@/mocks/fixtures/admin/positions.json";

import { PositionForm, timelineRows, validateElements } from "./position-form";
import { PositionList } from "./position-list";
import type { Catalog, Position } from "./types";

const catalog = catalogJson as unknown as Catalog;

test("채용 건 목록은 이름·요소·지원자 수를 보여 준다", () => {
  const html = renderToStaticMarkup(
    <PositionList positions={positionsJson as Position[]} catalog={catalog} />,
  );
  expect(html).toContain("프로덕트 매니저 인턴");
  expect(html).toContain("협력 태도");
  expect(html).toContain("지원자 9명");
});

test("채용 건 생성 폼은 요소 4개와 평가표 항목 미리보기를 보여 주고 요소 0개·5개를 거부한다", () => {
  const html = renderToStaticMarkup(<PositionForm catalog={catalog} onSubmit={() => {}} />);
  expect(html.match(/type="checkbox"/g)).toHaveLength(4);
  expect(html).toContain("요청 후 5분 안에 답함");
  expect(html).toContain("시험 운영 기준");

  expect(validateElements([])).not.toBeNull();
  expect(validateElements(["a", "b", "c", "d", "e"])).not.toBeNull();
  expect(validateElements(["cooperation"])).toBeNull();

  // 요소 2개: 120분 기준 1/4 + i×(1/2)/2 → 30분·60분. 흐름 카드는 카탈로그 비율 그대로
  const rows = timelineRows(catalog, ["cooperation", "responsibility"]);
  expect(rows.map((r) => Math.round(r.at))).toEqual([0, 10, 30, 60, 90, 110]);
  expect(html).toContain("{invite_url}");
});
