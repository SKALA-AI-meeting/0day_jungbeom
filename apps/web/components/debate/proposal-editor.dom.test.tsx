// @vitest-environment happy-dom
// 완료 기준: 확인 뒤 submit 요청이 끝날 때까지 기획안 입력이 잠기고, 실패하면 풀린다.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, test } from "vitest";

import { ProposalEditor } from "./proposal-editor";
import { SECTION_IDS, type Sections } from "./types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const full = Object.fromEntries(SECTION_IDS.map((id) => [id, "내용"])) as Sections;
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
});

const flush = () => act(async () => {});
const button = (name: string, within: ParentNode = document) =>
  [...within.querySelectorAll("button")].find((b) => b.textContent?.trim() === name)!;
const textareas = () => [...container.querySelectorAll("textarea")];

test("제출 요청 중에는 입력이 잠기고, 실패해 끝나면 풀린다", async () => {
  let finish!: () => void;
  const pending = new Promise<void>((resolve) => (finish = resolve));
  act(() =>
    root.render(
      <ProposalEditor
        sections={full}
        savedAt={null}
        saving={false}
        canSubmit
        locked={false}
        onChange={() => {}}
        prepareSubmit={async () => full}
        onSubmit={() => pending}
      />,
    ),
  );
  expect(textareas().every((t) => !t.disabled)).toBe(true);

  await act(async () => button("제출", container).click());
  await flush();
  await act(async () => button("제출", document.querySelector("[role=dialog]")!).click());
  await flush();

  expect(textareas().every((t) => t.disabled)).toBe(true);
  expect(container.textContent).toContain("제출 중");

  finish();
  await flush();
  expect(textareas().every((t) => !t.disabled)).toBe(true);
});
