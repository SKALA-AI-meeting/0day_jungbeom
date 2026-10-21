// 제출 전 저장 경계(Codex 리뷰 B1): 진행 중인 저장을 기다리고, 실패하면 제출을 막는다.
import { afterEach, expect, test, vi } from "vitest";

import { createSaver } from "./saver";

afterEach(() => vi.useRealTimers());

test("flush는 진행 중인 저장이 끝날 때까지 기다리고, 실패하면 false라 제출이 멈춘다", async () => {
  vi.useFakeTimers();
  const saver = createSaver(1000);
  const order: string[] = [];
  let fail = false;
  const job = async () => {
    order.push("save start");
    await new Promise((resolve) => setTimeout(resolve, 500)); // 느린 응답
    if (fail) throw new Error("503");
    order.push("save done");
  };
  const submit = async () => {
    if (await saver.flush()) order.push("submit");
    else order.push("submit blocked");
  };

  // 타이머가 이미 돌아 저장이 진행 중일 때 제출해도 저장이 끝난 뒤에 제출한다
  saver.schedule("1", job);
  await vi.advanceTimersByTimeAsync(1000);
  const first = submit();
  await vi.advanceTimersByTimeAsync(500);
  await first;
  expect(order).toEqual(["save start", "save done", "submit"]);

  // 저장이 실패하면(재시도도 실패) 제출하지 않는다
  fail = true;
  order.length = 0;
  saver.schedule("final", job);
  const second = submit();
  await vi.advanceTimersByTimeAsync(2000);
  await second;
  expect(order).toEqual(["save start", "submit blocked"]);

  // 저장을 기다리는 사이 새로 입력한 편집도 저장한 뒤에 제출한다(재확인 R2-1). 직전 실패분도 다시 저장된다
  fail = false;
  order.length = 0;
  saver.schedule("final", job);
  const third = submit();
  await vi.advanceTimersByTimeAsync(100);
  saver.schedule("final", job); // 느린 저장 중 추가 입력
  await vi.advanceTimersByTimeAsync(2000);
  await third;
  expect(order).toEqual(["save start", "save done", "save start", "save done", "submit"]);

  // 기다리는 사이 다른 창으로 옮겨 가면(stop) 저장이 끝나도 제출하지 않는다(재확인 R2-3)
  order.length = 0;
  saver.schedule("3", job);
  const fourth = submit();
  await vi.advanceTimersByTimeAsync(100);
  saver.stop();
  await vi.advanceTimersByTimeAsync(1000);
  await fourth;
  expect(order).toEqual(["save start", "save done", "submit blocked"]);
});
