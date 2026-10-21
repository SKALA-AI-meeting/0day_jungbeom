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
  expect(textareas().every((t) => !t.readOnly)).toBe(true);

  await act(async () => button("제출", container).click());
  await flush();
  // 확인 창이 떠 있는 동안에는 입력이 잠겨도 "제출 중"은 보이지 않는다
  expect(container.textContent).not.toContain("제출 중");
  await act(async () => button("제출", document.querySelector("[role=dialog]")!).click());
  await flush();

  expect(textareas().every((t) => t.readOnly)).toBe(true);
  expect(container.textContent).toContain("제출 중");

  finish();
  await flush();
  expect(textareas().every((t) => !t.disabled)).toBe(true);
});

test("확인 전·요청 중 제출 버튼이 비활성이고 onSubmit은 한 번만 불리며, 취소하면 잠금이 풀린다", async () => {
  let finish!: () => void;
  const pending = new Promise<void>((resolve) => (finish = resolve));
  let calls = 0;
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
        onSubmit={() => {
          calls += 1;
          return pending;
        }}
      />,
    ),
  );
  const submitButton = () => button("제출", container);

  await act(async () => submitButton().click());
  await flush();
  // 확인 창이 떠 있는 동안 반복 클릭해도 막힌다
  expect(submitButton().disabled).toBe(true);
  await act(async () => submitButton().click());

  // 취소하면 submit 없이 잠금이 풀린다
  await act(async () => button("취소", document.querySelector("[role=dialog]")!).click());
  await flush();
  expect(calls).toBe(0);
  expect(submitButton().disabled).toBe(false);
  expect(textareas().every((t) => !t.disabled)).toBe(true);

  await act(async () => submitButton().click());
  await flush();
  await act(async () => button("제출", document.querySelector("[role=dialog]")!).click());
  await flush();
  expect(submitButton().disabled).toBe(true);
  await act(async () => submitButton().click());
  expect(calls).toBe(1);

  finish();
  await flush();
});
