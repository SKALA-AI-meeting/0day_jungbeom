// 관리자 목업 캡처(라이트). NEXT_PUBLIC_MOCK=1로 띄운 web에서 채용 건 생성·지원자 목록·리포트(요약·근거 맥락)·
// 샘플 리포트·인쇄 미리보기·전체 기록을 찍어 tests/e2e/records/mock-ui-admin-<YYYYMMDD-HHMM>/에 남긴다.
//
//   node e2e/admin-capture.spec.ts      (환경변수: WEB_URL, 기본 http://localhost:3000. Node 22.6+ 타입 제거 실행)
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium, type Page } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..", "..");
const WEB = process.env.WEB_URL ?? "http://localhost:3000";

const now = new Date();
const pad = (n: number) => String(n).padStart(2, "0");
const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
const OUT = join(REPO, "tests", "e2e", "records", `mock-ui-admin-${stamp}`);
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1280, height: 900 },
  colorScheme: "light",
  deviceScaleFactor: 2,
});
// mock 로그인: 관리자 토큰을 미리 넣어 둔다
await context.addInitScript(() => {
  window.localStorage.setItem("dayzero.admin.token", "mock-admin-token");
});
const page = await context.newPage();

async function open(path: string, ready: string) {
  await page.goto(`${WEB}${path}`, { waitUntil: "networkidle" });
  await page.getByText(ready, { exact: false }).first().waitFor();
}

async function shot(name: string, target: Page = page, fullPage = false) {
  await target.screenshot({ path: join(OUT, `${name}.png`), fullPage });
  console.log(`saved ${name}.png`);
}

await open("/admin/positions/new", "보는 요소");
await shot("01-position-create", page, true);

await open("/admin/positions/pos-1", "요소별 수준");
await shot("02-candidates", page, true);

await open("/admin/sessions/sess-1/report", "요소 요약");
await shot("03-report-summary");

// 근거 펼침: 경청/존중의 응답성 차원 → 첫 근거의 앞뒤 맥락
await page.locator("#dim-listen_engage summary").click();
await page.locator("#dim-listen_engage").getByText("앞뒤 맥락 보기").first().click();
await page.locator("#dim-listen_engage").scrollIntoViewIfNeeded();
await page.locator("#dim-listen_engage").screenshot({ path: join(OUT, "04-report-evidence.png") });
console.log("saved 04-report-evidence.png");

// 담당자 조정 패널(메모 필수)
await page.locator("#dim-pers_comparison summary").click();
await page.locator("#dim-pers_comparison").getByRole("button", { name: "조정" }).click();
await page.locator("#dim-pers_comparison").getByRole("radio", { name: "수준 3" }).click();
await page.locator("#dim-pers_comparison").screenshot({ path: join(OUT, "05-report-adjust.png") });
console.log("saved 05-report-adjust.png");

await open("/admin/sample-report", "샘플 리포트입니다");
await shot("06-sample-report", page, true);

// 인쇄 미리보기: 인쇄 매체 + 차원 전부 펼침
await page.emulateMedia({ media: "print" });
await open("/admin/sample-report?print=1", "요소 요약");
await shot("07-print-preview", page, true);
await page.pdf({ path: join(OUT, "07-print-preview.pdf"), format: "A4", printBackground: true });
console.log("saved 07-print-preview.pdf");
await page.emulateMedia({ media: "screen" });

await open("/admin/sessions/sess-1/record#message-m-15", "전체 기록");
await page.waitForTimeout(400);
await shot("08-record-highlight");

await browser.close();
console.log(`done: ${OUT}`);
