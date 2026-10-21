// 완료 기준(CX-05): 회사 자료의 제목·목록·표·강조가 서식으로 보이고, 원문 HTML은 그리지 않는다.
import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";

import { AssistantMarkdown, Markdown } from "./markdown";

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

test("어시스턴트 답은 굵게·목록·코드만 서식으로 그리고 링크·이미지·HTML·제목은 글자로 둔다", () => {
  const html = renderToStaticMarkup(
    <AssistantMarkdown>
      {[
        "## 요약",
        "",
        "**재참여율**은 *기울임* 이고 `D7` 기준입니다.",
        "",
        "- 첫째",
        "- 둘째",
        "",
        "[자료](https://example.com/x) ![그림](https://example.com/a.png)",
        "",
        '<script>alert("x")</script> <b>태그</b>',
      ].join("\n")}
    </AssistantMarkdown>,
  );
  expect(html).toMatch(/<strong[^>]*>재참여율<\/strong>/);
  expect(html).toMatch(/<em>기울임<\/em>/);
  expect(html).toMatch(/<code[^>]*>D7<\/code>/);
  expect(html).toMatch(/<ul[^>]*>[\s\S]*<li[^>]*>첫째<\/li>/);
  expect(html).not.toContain("**");
  expect(html).not.toMatch(/<h\d/);
  expect(html).not.toContain("<a ");
  expect(html).not.toContain("href");
  expect(html).not.toContain("<img");
  expect(html).toContain("자료");
  expect(html).toContain("그림");
  expect(html).not.toContain("<script");
  expect(html).not.toContain("<b>");
  expect(html).toContain("&lt;b&gt;태그&lt;/b&gt;");
});
