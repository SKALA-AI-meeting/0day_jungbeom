// debrief: R1 첫 문장, 내 발언 ≤ 3, 설문 제출
import { expect, test } from "@playwright/test";

import { type Seed, seed, shot } from "./helpers";

let s: Seed;
test.beforeAll(async () => {
  s = await seed("ended");
});

test("디브리핑: 첫 문장·내 발언·설문", async ({ page }) => {
  await page.goto(s.link);
  await expect(page.getByRole("heading", { name: "수고하셨습니다" })).toBeVisible();
  await expect(
    page.getByText("같은 채용 건의 모든 지원자가 같은 장면을 겪었고", { exact: false }),
  ).toBeVisible();
  await shot(page, "debrief", "01-첫 문장");

  const mine = page.locator("section", {
    has: page.getByRole("heading", { name: "내 발언 돌아보기" }),
  });
  const count = await mine.locator("li").count();
  expect(count).toBeGreaterThan(0);
  expect(count).toBeLessThanOrEqual(3);
  await mine.scrollIntoViewIfNeeded();
  await shot(page, "debrief", "02-내 발언");

  const scales = page.getByRole("radiogroup");
  for (let i = 0; i < (await scales.count()); i += 1) {
    await scales.nth(i).getByRole("radio", { name: "4" }).click();
  }
  await page.getByRole("button", { name: "설문 보내기" }).click();
  await expect(page.getByText("설문에 답해 주셔서 고마워요.")).toBeVisible();
  await shot(page, "debrief", "03-설문");

  await page.reload();
  await expect(page.getByText("설문에 답해 주셔서 고마워요.")).toBeVisible(); // 한 번만 저장
});
