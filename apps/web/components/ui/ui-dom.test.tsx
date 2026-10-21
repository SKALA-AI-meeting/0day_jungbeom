// @vitest-environment happy-dom
// 완료 기준(web-kit): Avatar 이미지 실패 시 이니셜 대체, Tabs 방향키 이동·선택·패널 연결을 실제 DOM 이벤트로 확인한다.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, test } from "vitest";

import { Avatar } from "./avatar";
import { Tabs } from "./tabs";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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
});

test("Avatar: 이미지 onError가 나면 이미지를 걷어내고 이니셜만 남긴다", () => {
  act(() => root.render(<Avatar name="서연" seat="p2" src="/missing.png" />));
  const img = container.querySelector("img");
  expect(img).not.toBeNull();
  act(() => {
    img!.dispatchEvent(new Event("error"));
  });
  expect(container.querySelector("img")).toBeNull();
  expect(container.textContent).toContain("서");
  expect(container.querySelector('[role="img"]')?.getAttribute("aria-label")).toBe("서연");
});

/** 선택된 탭과 패널이 aria-controls ↔ id, aria-labelledby ↔ id로 서로 가리키는지 확인하고 패널을 돌려준다 */
function linkedPanel(tab: HTMLElement) {
  const panelId = tab.getAttribute("aria-controls");
  expect(panelId).toBeTruthy();
  const panel = document.getElementById(panelId!);
  expect(panel?.getAttribute("role")).toBe("tabpanel");
  expect(panel?.getAttribute("aria-labelledby")).toBe(tab.id);
  return panel!;
}

test("Tabs: 방향키로 포커스를 옮기고 선택하면 연결된 패널이 보인다", async () => {
  const items = [
    { value: "a", label: "합의", content: "합의 내용" },
    { value: "b", label: "자료", content: "자료 내용" },
    { value: "c", label: "메모", content: "메모 내용" },
  ];
  await act(async () => root.render(<Tabs items={items} />));
  const tabs = () => Array.from(container.querySelectorAll<HTMLElement>('[role="tab"]'));
  expect(tabs()).toHaveLength(3);
  expect(tabs()[0].getAttribute("aria-selected")).toBe("true");

  expect(linkedPanel(tabs()[0]).textContent).toBe("합의 내용");

  await act(async () => tabs()[0].focus());
  await act(async () => {
    tabs()[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  });
  expect(document.activeElement).toBe(tabs()[1]);

  await act(async () => tabs()[1].click());
  expect(tabs()[1].getAttribute("aria-selected")).toBe("true");
  expect(tabs()[0].getAttribute("aria-selected")).toBe("false");
  const selectedPanel = linkedPanel(tabs()[1]);
  expect(selectedPanel.hidden).toBe(false);
  expect(selectedPanel.textContent).toBe("자료 내용");
  // 선택되지 않은 패널은 그리지 않는다
  expect(container.querySelectorAll('[role="tabpanel"]')).toHaveLength(1);

  // 마지막에서 오른쪽으로 가면 처음으로 돌아온다(loop)
  await act(async () => tabs()[2].focus());
  await act(async () => {
    tabs()[2].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  });
  expect(document.activeElement).toBe(tabs()[0]);
});
