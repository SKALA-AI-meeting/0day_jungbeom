// 완료 기준(CX-05): 회사 자료의 제목·목록·표·강조가 서식으로 보이고, 원문 HTML은 그리지 않는다.
import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import { Markdown } from "./markdown";

test("자료 Markdown을 제목·목록·표·강조로 그리고 원문 HTML은 버린다", () => {
  const html = renderToStaticMarkup(
    <Markdown>
      {[
        "# 지표 현황",
        "",
        "- 재참여율: **22%**",
        "",
        "| 지표 | 값 |",
        "| --- | --- |",
        "| 첫 모임 참여자 | 412명 |",
        "",
        '<script>alert("x")</script>',
      ].join("\n")}
    </Markdown>,
  );
  expect(html).toMatch(/<h1[^>]*>지표 현황<\/h1>/);
  expect(html).toMatch(/<li[^>]*>재참여율: <strong[^>]*>22%<\/strong><\/li>/);
  expect(html).toMatch(/<td[^>]*>412명<\/td>/);
  expect(html).toContain("overflow-x-auto"); // 좁은 화면에서는 표만 가로 스크롤
  expect(html).not.toContain("|");
  expect(html).not.toContain("<script");
});
