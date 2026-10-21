import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import { ReportFailed } from "./report-failed";

test("실패 화면은 안내 문장과 [다시 만들기] 버튼을 보이고, 요청 중에는 버튼이 잠긴다", () => {
  const html = renderToStaticMarkup(<ReportFailed onRegenerate={() => {}} />);
  expect(html).toContain("리포트를 만들지 못했어요");
  expect(html).toContain("다시 만들기");
  expect(html).not.toContain(`disabled=""`);
  expect(renderToStaticMarkup(<ReportFailed pending onRegenerate={() => {}} />)).toContain(
    `disabled=""`,
  );
});
