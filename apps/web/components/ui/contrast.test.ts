// 완료 기준(web-kit): globals.css에 정의한 토큰 값으로 글자·면 대비가 라이트·다크·인쇄 모두 AA(본문 4.5:1)를 넘는다.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";

const css = readFileSync(fileURLToPath(new URL("../../app/globals.css", import.meta.url)), "utf8");

/** after 뒤에 처음 나오는 `selector {` 블록 안의 --color-* 값만 모은다(중첩 없는 평평한 블록 기준) */
function tokens(selector: string, after = ""): Record<string, string> {
  const start = css.indexOf(`${selector} {`, css.indexOf(after));
  if (start < 0) throw new Error(`블록 없음: ${selector}`);
  const body = css.slice(start, css.indexOf("}", start));
  const out: Record<string, string> = {};
  for (const [, name, hex] of body.matchAll(/--color-([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    out[name] = hex.toLowerCase();
  }
  return out;
}

function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const light = tokens("@theme static");
// 다크는 라이트 위에 덮어쓴다(재정의하지 않은 on-accent 등은 라이트 값을 물려받는다)
const dark = { ...light, ...tokens(":root.dark") };
const print = { ...light, ...tokens(":root:not(.light)", "@media print") };

/** [글자, 바탕] 본문 글자 쌍. subtle은 메타 전용이라 제외 */
const PAIRS: [string, string][] = [
  ["ink", "canvas"],
  ["ink", "surface"],
  ["ink", "surface-sunken"],
  ["muted", "canvas"],
  ["muted", "surface"],
  ["accent", "canvas"],
  ["accent", "surface"],
  ["accent-strong", "accent-soft"],
  ["on-accent", "accent-fill"],
  ["on-accent", "accent-fill-hover"],
  ["on-bubble-candidate", "bubble-candidate"],
  ["on-bubble", "bubble-p1"],
  ["on-bubble", "bubble-p2"],
  ["on-bubble", "bubble-p3"],
  ["on-seat", "seat-p1"],
  ["on-seat", "seat-p2"],
  ["on-seat", "seat-p3"],
  ["on-seat", "seat-candidate"],
  ["danger", "surface"],
  ["warning", "surface"],
  ["success", "surface"],
];

test("계산식 확인: 흰색·검정 21:1, 다크 accent(#2997FF) 위 흰 글자는 AA 미달", () => {
  expect(contrast("#ffffff", "#000000")).toBeCloseTo(21, 1);
  expect(contrast("#ffffff", "#2997ff")).toBeLessThan(4.5);
});

test.each([
  ["라이트", light],
  ["다크", dark],
  ["인쇄", print],
] as const)("%s 테마의 글자·면 쌍이 모두 4.5:1 이상이다", (_, theme) => {
  const failures = PAIRS.map(([fg, bg]) => ({
    pair: `${fg}/${bg}`,
    ratio: contrast(theme[fg], theme[bg]),
  })).filter(({ ratio }) => !(ratio >= 4.5));
  expect(failures).toEqual([]);
});

test("인쇄 블록은 다크 테마에서도 라이트 글자색(ink)을 흰 종이 위에 둔다", () => {
  expect(print.ink).toBe(light.ink);
  expect(print.canvas).toBe("#ffffff");
  expect(css).toMatch(
    /@media print \{\s*\/\*[\s\S]*?\*\/\s*:root,\s*:root\.dark,\s*:root:not\(\.light\) \{/,
  );
});

test("시스템 다크(:root:not(.light))와 강제 다크(:root.dark) 값이 같다", () => {
  expect(tokens(":root:not(.light)")).toEqual(tokens(":root.dark"));
});
