// solution: AI 합의 공지 → 칸 확정, 침묵 시 advance{to: idle} 뒤 초대 메시지 1건(silent),
// 반대가 남은 상태의 지원자 혼자 확정(solo_confirm)
import { expect, test } from "@playwright/test";

import { type Seed, advance, internalGet, room, say, seed, settle, shot } from "./helpers";

type Slot = {
  phase: string;
  option_id: string | null;
  status: string;
  value: string;
  filled_by: string;
  resolution: string;
  support: { option_id: string; supporters: string[] }[];
};
const slotOf = async (id: string, phase: string) =>
  (await internalGet<Slot[]>(id, "/slots")).find((x) => x.phase === phase);

const S2 = "주민 절수·보상 캠페인";
const S3 = "빗물 저금통·투수 포장 같은 생활 인프라";

let s: Seed;
test.beforeEach(async () => {
  s = await seed("solution");
});

test("AI 합의 채우기: 공지 메시지 → 결정 사항 칸 확정 → 기획안 단계", async ({ page }) => {
  await page.goto(s.link);
  await expect(page.locator('[data-slot-input="solution"]')).toBeVisible();
  for (const text of [
    `저는 ${S3}가 좋다고 생각해요.`,
    "윤하람님은 어떻게 생각하세요?", // 소극형 지명 → 소극형이 자기 안(S3)을 밝힌다
    `${S2}은 아니에요. 효과가 오래 가지 않아요.`, // 서지안 설득: 반대·대안 2회 → 지원자 안으로 이동
    `${S2}은 반대예요. 인프라가 더 낫다고 봐요.`,
  ]) {
    await say(page, text);
    await settle(s.sessionId);
  }
  await shot(page, "solution", "01-합의 직전");

  await expect(room(page).getByText(/그럼 .+로 정리할게요/)).toBeVisible();
  const result = page.locator('[data-slot="solution"]');
  await expect(result).toContainText("합의");
  await expect(result).toContainText(S3);
  await expect(page.getByRole("button", { name: "이걸로 정하기" })).toHaveCount(0);
  await shot(page, "solution", "02-합의 채움");
  const slot = await slotOf(s.sessionId, "solution");
  expect(slot).toMatchObject({ status: "confirmed", resolution: "consensus" });
  expect(["p1", "p2", "p3"]).toContain(slot?.filled_by);
});

test("silent: 침묵하면 idle 뒤 비판형 초대 메시지가 1건", async ({ page }) => {
  await page.goto(s.link);
  await expect(page.locator('[data-slot-input="solution"]')).toBeVisible();
  await advance(s.sessionId, "idle");
  const invite = room(page).getByText(/님은 어떻게 생각하세요\?/);
  await expect(invite).toHaveCount(1);
  await shot(page, "solution", "03-침묵 초대");
  const invites = (
    await internalGet<{ is_invite: boolean; sender: string; phase: string }[]>(
      s.sessionId,
      "/messages",
    )
  ).filter((m) => m.is_invite && m.phase === "solution");
  expect(invites).toHaveLength(1);
  expect(invites[0].sender).toBe("p3");
});

test("solo_confirm: 반대가 남아도 지원자가 혼자 확정하면 칸이 확정된다", async ({ page }) => {
  await page.goto(s.link);
  for (const text of [
    `저는 ${S3}가 좋다고 생각해요.`,
    `${S2}은 반대예요. 효과가 오래 가지 않아요.`,
  ]) {
    await say(page, text);
    await settle(s.sessionId);
  }
  await page.locator('[data-slot-input="solution"] textarea').fill(S3);
  await page.getByRole("button", { name: "이걸로 정하기" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "이걸로 정하기" }).click();
  const result = page.locator('[data-slot="solution"]');
  await expect(result).toContainText(S3);
  await expect(result).toContainText("정한 사람 · 나");
  await shot(page, "solution", "04-혼자 확정");
  const slot = await slotOf(s.sessionId, "solution");
  expect(slot).toMatchObject({ filled_by: "candidate", resolution: "consensus" });
  // 확정 안(S3)의 지지자는 지원자뿐이고, 다른 안(고집형의 S1 등)에는 지지자가 남아 있다
  const confirmed = slot?.support.find((x) => x.option_id === slot.option_id);
  expect(confirmed?.supporters).toEqual(["candidate"]);
  const others = slot?.support.filter((x) => x.option_id !== slot.option_id) ?? [];
  expect(others.some((x) => x.supporters.length > 0)).toBe(true);
});
