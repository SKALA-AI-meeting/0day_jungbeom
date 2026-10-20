// 완료 기준(보드): 담당 없음 5장에서 담당(나·도현·둘 다)을 채우면 division.confirmed와 SystemLine, 조건 위반은 422 문장,
// 끌어 놓기(칸 이동·순서), 카드 상세의 "언제까지" 프리셋·의존 배지, 확정 뒤 재배정.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, test, vi } from "vitest";

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_MOCK = "1";
});

import { createMockSocket, DIVISION_RULE, resetMockOffice } from "@/mocks/office";

import { Board, dropIndex, duePresets, moveTask, parseClock } from "./board";
import { candidateApi as api, sessionIdFromToken } from "./flow";
import { initialState, partTitles, reduce, timeline, type OfficeState } from "./reducer";
import type { ServerFrame } from "./types";

afterEach(() => {
  resetMockOffice();
  vi.useRealTimers();
});

test("보드로 분업 확정·422 문장·끌어 놓기 변경·언제까지 프리셋·확정 뒤 재배정", async () => {
  vi.useFakeTimers();
  const { session_token: jwt } = await api.consent("demo");
  await api.start("demo", jwt);
  const id = sessionIdFromToken(jwt);
  let state: OfficeState = initialState(await api.state(id, jwt));
  const socket = createMockSocket(`ws://x/ws/sessions/${id}?token=${jwt}`);
  socket.onmessage = ({ data }) => {
    state = reduce(state, { type: "frame", frame: JSON.parse(data) as ServerFrame });
  };
  expect(state.snap.tasks.map((t) => t.assignee)).toEqual([null, null, null, null, null]);

  const board = renderToStaticMarkup(
    <Board
      snap={state.snap}
      titles={partTitles(state.snap)}
      nowMin={0}
      sessionMinutes={120}
      locked={false}
      errors={{}}
      onPatch={() => {}}
      onMove={() => {}}
    />,
  );
  expect(board).toContain("2번 필요"); // 3번 카드의 의존 배지
  expect(board).toContain("담당 0/5");
  expect(board).toContain("+ 담당"); // 빈 담당 표시

  await api.putTask(id, jwt, 1, { assignee: "candidate" });
  await api.putTask(id, jwt, 2, { assignee: "candidate" });
  await api.putTask(id, jwt, 3, { assignee: "both" });
  await api.putTask(id, jwt, 4, { assignee: "both" });
  // 4·5가 모두 동료 단독이 아니면 분업 조건 위반: 저장하지 않고 조건 문장을 돌려준다
  await expect(api.putTask(id, jwt, 5, { assignee: "candidate" })).rejects.toMatchObject({
    status: 422,
    code: "invalid_division",
    message: DIVISION_RULE,
  });
  expect(state.snap.division).toBeNull();
  await api.putTask(id, jwt, 5, { assignee: "colleague" });
  await vi.advanceTimersByTimeAsync(2000);
  expect(state.snap.division).toMatchObject({ decided_by: "candidate" });
  const lines = timeline(state, "team")
    .filter((i) => i.kind === "line")
    .map((i) => i.kind === "line" && i.line.text);
  expect(lines).toContain("분업이 정해졌어요: 1·2 나, 3·4 같이, 5 도현");
  // 동료가 자기 카드를 진행 중으로 옮기면 그 줄이 남는다
  expect(lines).toContain("5번 → 진행 중 (도현)");

  // 확정 뒤 재배정도 같은 규칙으로 기록된다
  await api.putTask(id, jwt, 4, { assignee: "colleague" });
  expect(state.snap.tasks.find((t) => t.part_no === 4)?.assignee).toBe("colleague");

  // 끌어 놓기: 2번을 진행 중 칸 맨 앞으로 → 2번 status·order, 밀린 카드는 order만 보낸다
  const patches = moveTask(state.snap.tasks, 2, "doing", 0);
  expect(patches[0]).toEqual({ part_no: 2, status: "doing", order: 1 });
  expect(patches.slice(1).every((p) => p.status === undefined && p.order)).toBe(true);

  // 같은 칸 안에서 아래로: 1번을 2번 자리에 놓으면 [2,1,3], 3번 자리면 맨 끝
  const column = [1, 2, 3].map((n) => state.snap.tasks.find((t) => t.part_no === n)!);
  expect(dropIndex(column, 1, 2)).toBe(1);
  expect(dropIndex(column, 1, 3)).toBe(2);
  expect(dropIndex(column, 3, 1)).toBe(0);

  // 언제까지: 남은 시간 프리셋을 세션 분으로
  expect(duePresets(47.5, 120)).toEqual([
    { label: "30분 뒤", due_min: 78 },
    { label: "마감 10분 전", due_min: 110 },
  ]);
  expect(parseClock("01:10")).toBe(70);
  expect(parseClock("1시")).toBeNull();
});
