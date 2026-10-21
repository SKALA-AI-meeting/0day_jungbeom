// @vitest-environment happy-dom
// 완료 기준: 입력창에 글자가 있는 동안 5초마다 typing start를 다시 보내고, 비우거나 보내면 stop.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { Composer, TYPING_REFRESH_MS } from "./chat";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.useFakeTimers();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

function type(textarea: HTMLTextAreaElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  act(() => {
    setter.call(textarea, value);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

test("글자가 있는 동안 5초마다 start를 갱신하고, 비우면 stop을 보낸다", () => {
  const onTyping = vi.fn();
  act(() => root.render(<Composer locked={false} onSend={() => {}} onTyping={onTyping} />));
  const textarea = container.querySelector("textarea")!;

  type(textarea, "안");
  expect(onTyping.mock.calls).toEqual([["start"]]);

  act(() => vi.advanceTimersByTime(TYPING_REFRESH_MS));
  act(() => vi.advanceTimersByTime(TYPING_REFRESH_MS));
  expect(onTyping.mock.calls.filter(([s]) => s === "start")).toHaveLength(3);

  type(textarea, "");
  expect(onTyping).toHaveBeenLastCalledWith("stop");
  const count = onTyping.mock.calls.length;
  act(() => vi.advanceTimersByTime(TYPING_REFRESH_MS * 2));
  expect(onTyping.mock.calls).toHaveLength(count);
});
