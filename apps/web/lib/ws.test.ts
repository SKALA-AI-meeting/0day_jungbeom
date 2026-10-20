// 완료 기준: 재연결 후 상태 복원. 끊기면 3초 뒤 다시 붙고 /state 스냅샷으로 진행 표시까지 되살린다.
// 4401은 /resume 재발급 후 재연결, 4000(session.replaced)은 멈춘다.
import { expect, test, vi } from "vitest";

import { fetchSnapshot } from "@/components/office/flow";
import { initialState, progressLabels, reduce } from "@/components/office/reducer";
import type { ServerFrame, StateSnapshot } from "@/components/office/types";
import state from "@/mocks/fixtures/office/state.json";

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

test("재연결: 3초 뒤 다시 붙어 /state로 메시지와 진행 중 실행을 복원하고, 4401은 재발급, 4000은 멈춘다", async () => {
  vi.useFakeTimers();
  const { made, create } = fakeSockets();
  const statuses: string[] = [];
  const opens: boolean[] = [];
  let token = "jwt-1";
  const socket = new SessionSocket({
    sessionId: "s-1",
    getToken: () => token,
    refreshToken: async () => (token = "jwt-2"),
    onFrame: () => {},
    onStatus: (s) => statuses.push(s),
    onOpen: ({ reconnected }) => opens.push(reconnected),
    createSocket: create,
  });

  // 처음 연결 뒤 진행 중이던 것이 없는 화면
  const snapshot = state as StateSnapshot;
  let view = initialState({ ...snapshot, messages: [], active_runs: [] }, 0);
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

  // 다시 열리면 /state를 받는다. 첫 조회가 실패해도 3초 뒤 다시 시도한다
  let calls = 0;
  const loading = fetchSnapshot(
    async () => {
      calls += 1;
      if (calls === 1) throw new Error("503");
      return snapshot;
    },
    () => true,
  );
  await vi.advanceTimersByTimeAsync(3000);
  const fetched = (await loading)!;
  expect(calls).toBe(2);

  // 조회하는 동안 도착해 이미 화면에 반영한 프레임은 모아 두었다가 스냅샷 뒤에 다시 얹는다
  const during: ServerFrame[] = [
    {
      type: "message.new",
      payload: { ...snapshot.messages[0], id: "late-1", channel: "dm", sender: "colleague" },
    },
    {
      type: "document.part_updated",
      payload: { part_no: 2, content: "동료 초안", revision: 1, by: "colleague" },
    },
  ];
  for (const frame of during) view = reduce(view, { type: "frame", frame });
  expect(view.unread.dm).toBe(1);
  view = reduce(view, { type: "snapshot", state: fetched, now: 0, frames: during });
  expect(view.messages.map((m) => m.id)).toEqual([snapshot.messages[0].id, "late-1"]);
  expect(view.unread.dm).toBe(1);
  expect(view.document[2]).toMatchObject({ content: "동료 초안", revision: 1 });
  // 끊긴 사이 시작된 실행은 active_runs로 복원, 타이머는 ends_at 기준
  expect(progressLabels(view)).toEqual(["이도현이 입력 중…"]);
  expect(view.deadline).toBe(Date.parse(snapshot.session.ends_at!));

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
