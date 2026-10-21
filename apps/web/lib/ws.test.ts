// 완료 기준: 재연결과 seq 누락 시 /state 복원. 끊기면 3초 뒤 다시 붙고, 4401은 재발급 후 재연결, 4000은 멈춘다.
// 화면 reducer는 seq가 비면 적용을 멈추고(needsResync) /state 스냅샷으로 이어 간다.
import { expect, test, vi } from "vitest";

import { initialView, reduce } from "@/components/debate/reducer";
import type { ServerFrame, StateSnapshot } from "@/components/debate/types";
import problem from "@/mocks/fixtures/state_problem.json";
import solution from "@/mocks/fixtures/state_solution.json";
import events from "@/mocks/fixtures/ws_events.json";

import { SessionSocket, type SocketLike } from "./ws";

function fakeSockets() {
  const made: (SocketLike & { url: string })[] = [];
  const create = (url: string) => {
    const socket = {
      url,
      send: vi.fn(),
      close: vi.fn(),
      onopen: null,
      onmessage: null,
      onclose: null,
    };
    made.push(socket);
    return socket;
  };
  return { made, create };
}

test("재연결: 3초 뒤 다시 붙어 onOpen(reconnected)을 알리고, 4401은 재발급, 4000은 멈춘다", async () => {
  vi.useFakeTimers();
  const { made, create } = fakeSockets();
  const statuses: string[] = [];
  const opens: boolean[] = [];
  let token = "jwt-1";
  const socket = new SessionSocket({
    sessionId: "sess-1",
    getToken: () => token,
    refreshToken: async () => (token = "jwt-2"),
    onFrame: () => {},
    onStatus: (s) => statuses.push(s),
    onOpen: ({ reconnected }) => opens.push(reconnected),
    createSocket: create,
  });
  socket.connect();
  made[0].onopen!();
  expect(opens).toEqual([false]);

  made[0].onclose!({ code: 1006 });
  expect(statuses.at(-1)).toBe("reconnecting");
  await vi.advanceTimersByTimeAsync(2999);
  expect(made).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(made).toHaveLength(2);
  made[1].onopen!();
  expect(opens).toEqual([false, true]);

  made[1].onclose!({ code: 4401 });
  await vi.advanceTimersByTimeAsync(0);
  expect(made).toHaveLength(3);
  expect(made[2].url).toContain("token=jwt-2");

  made[2].onopen!();
  made[2].onclose!({ code: 4000 });
  await vi.advanceTimersByTimeAsync(5000);
  expect(made).toHaveLength(3);
  expect(statuses.at(-1)).toBe("replaced");
  vi.useRealTimers();
});

test("seq 공백이면 적용을 멈추고 /state 스냅샷으로 칸·메시지·입력 중을 복원한 뒤 이어서 적용한다", () => {
  const frames = events as unknown as ServerFrame[];
  const start = problem as unknown as StateSnapshot;
  let view = initialView(start, 0);

  // 스냅샷 뒤 프레임을 순서대로 적용
  const next = frames.find((f) => f.seq === start.ws_seq + 1)!;
  view = reduce(view, { type: "frame", frame: next, now: 1 });
  expect(view.snap.ws_seq).toBe(next.seq);

  // 하나를 건너뛴 프레임이 오면 멈춘다
  const skipped = frames.find((f) => f.seq === view.snap.ws_seq + 2)!;
  const before = view.snap;
  view = reduce(view, { type: "frame", frame: skipped, now: 2 });
  expect(view.needsResync).toBe(true);
  expect(view.snap).toBe(before);

  // /state 재조회: 해결책 단계 스냅샷으로 결정 사항·메시지·입력 중이 복원된다
  const fresh = solution as unknown as StateSnapshot;
  view = reduce(view, { type: "snapshot", snap: fresh, now: 3 });
  expect(view.needsResync).toBe(false);
  expect(view.snap.slots.find((s) => s.phase === "problem")?.status).toBe("confirmed");
  expect(view.snap.messages).toHaveLength(fresh.messages.length);
  expect(Object.keys(view.typingSince)).toEqual(fresh.typing);

  // 스냅샷 ws_seq 이하는 버리고 그다음부터 이어 간다
  const old = frames.find((f) => f.seq === fresh.ws_seq)!;
  expect(reduce(view, { type: "frame", frame: old, now: 4 })).toBe(view);
  const after = frames.find((f) => f.seq === fresh.ws_seq + 1)!;
  view = reduce(view, { type: "frame", frame: after, now: 4 });
  expect(view.snap.ws_seq).toBe(fresh.ws_seq + 1);
});
