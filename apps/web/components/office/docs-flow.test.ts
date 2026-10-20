// 완료 기준(문서 흐름): 내 문서 보내기 → 동료 문서 받기(DocCard) → 열기 → 답글(참조 칩) → 최종본에 가져오기(출처 칩)
// → 제출(확인 창은 화면) → 보고 대기(5분, 채널 잠금 없음) → 디브리핑. mock 서버와 소켓 프레임을 reducer에 그대로 흘린다.
import { afterEach, expect, test, vi } from "vitest";

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_MOCK = "1";
});

import { createMockSocket, mockControls, resetMockOffice } from "@/mocks/office";

import { candidateApi as api, sessionIdFromToken } from "./flow";
import { sourceLabel } from "./my-docs";
import { initialState, reduce, type OfficeState } from "./reducer";
import type { SendFrame, ServerFrame, StateSnapshot } from "./types";

afterEach(() => {
  resetMockOffice();
  vi.useRealTimers();
});

test("문서 주고받기부터 디브리핑까지 mock으로 돈다", async () => {
  vi.useFakeTimers();
  const { session_token: jwt } = await api.consent("demo");
  await api.start("demo", jwt);
  const id = sessionIdFromToken(jwt);
  let state: OfficeState = initialState(await api.state(id, jwt));
  const socket = createMockSocket(`ws://x/ws/sessions/${id}?token=${jwt}`);
  socket.onmessage = ({ data }) => {
    state = reduce(state, { type: "frame", frame: JSON.parse(data) as ServerFrame });
  };
  const send = (payload: SendFrame["payload"]) =>
    socket.send(JSON.stringify({ type: "message.send", payload }));

  // 1) 내 문서를 쓰고 팀 채널로 보낸다 → 버전 1, 문서 카드 메시지와 "보냈어요" 줄
  await api.saveDoc(id, jwt, 1, "첫 참여자가 두 번째 모임에 오지 않는 문제");
  expect(await api.share(id, jwt, 1, "team")).toMatchObject({ version: 1 });
  expect(state.snap.my_documents[0].versions).toHaveLength(1);
  // 카드 본문은 지원자가 쓴 한마디뿐이다(B7). 한마디 없이 보냈으니 빈 본문
  const card = state.snap.messages.find((m) => m.shared_doc?.doc_id === "doc-c1")!;
  expect(card.content).toBe("");

  // 재연결 스냅샷이 아직 저장되지 않은 편집을 덮지 않는다(Codex B2)
  state = reduce(state, { type: "doc_edit", part_no: 2, content: "저장 전 입력" });
  state = reduce(state, { type: "final_edit", part_no: 5, content: "최종본 저장 전" });
  state = reduce(state, { type: "snapshot", state: await api.state(id, jwt) });
  expect(state.snap.my_documents.find((d) => d.part_no === 2)?.content).toBe("저장 전 입력");
  expect(state.snap.final.sections.find((x) => x.part_no === 5)?.content).toBe("최종본 저장 전");
  state = reduce(state, {
    type: "doc_saved",
    part_no: 2,
    content: "저장 전 입력",
    revision: 1,
    updated_at: new Date().toISOString(),
  });
  state = reduce(state, {
    type: "final_saved",
    sections: [{ part_no: 5, content: "최종본 저장 전" }],
  });

  // 저장 성공 뒤 늦게 도착한 옛 스냅샷이 최신 본문을 덮지 않는다(재확인 R2-2)
  const since = state.saveSeq;
  const stale = await api.state(id, jwt); // 아래 저장 전에 만든 응답
  state = reduce(state, { type: "doc_edit", part_no: 2, content: "더 최신" });
  await api.saveDoc(id, jwt, 2, "더 최신");
  state = reduce(state, {
    type: "doc_saved",
    part_no: 2,
    content: "더 최신",
    revision: 2,
    updated_at: new Date().toISOString(),
  });
  state = reduce(state, { type: "snapshot", state: stale, since });
  expect(state.snap.my_documents.find((d) => d.part_no === 2)?.content).toBe("더 최신");

  // 2) 중간 점검(45분)까지 진행: 분업 기본안이 채워지고 동료 문서 v1이 DocCard로 온다
  const controls = mockControls(id);
  controls.nextScene();
  controls.nextScene();
  controls.nextScene();
  await vi.advanceTimersByTimeAsync(2000);
  const k4 = state.snap.received.find((d) => d.doc_id === "doc-k4")!;
  expect(k4.versions).toMatchObject([{ version: 1, opened: false }]);
  expect(state.snap.messages.some((m) => m.shared_doc?.doc_id === "doc-k4")).toBe(true);

  // 3) 열기 → 열람 기록
  const opened = await api.open(id, jwt, "doc-k4", 1);
  state = reduce(state, { type: "opened", doc_id: "doc-k4", version: 1 });
  expect(opened.content).toContain("사례 1");
  expect(state.snap.received.find((d) => d.doc_id === "doc-k4")!.versions[0].opened).toBe(true);

  // 4) 문서에 매인 답글 → 같은 채널에 참조가 붙은 메시지, 동료가 답한다
  send({
    client_msg_id: "c-1",
    channel: "team",
    content: "사례 기준 좋아요",
    reply_to_doc: { doc_id: "doc-k4", version: 1 },
  });
  await vi.advanceTimersByTimeAsync(2000);
  const reply = state.snap.messages.find((m) => m.content === "사례 기준 좋아요")!;
  expect(reply.reply_to_doc).toEqual({ doc_id: "doc-k4", version: 1 });
  expect(state.snap.messages.at(-1)?.sender).toBe("colleague");

  // 5) 최종본 4번 섹션에 가져오기 → 출처 칩 "도현 v1에서", 편집하면 "+ 편집"
  const section = await api.importSection(id, jwt, 4, { source_doc_id: "doc-k4", version: 1 });
  state = reduce(state, { type: "final_section", section });
  const imported = state.snap.final.sections.find((s) => s.part_no === 4)!;
  expect(sourceLabel(imported, state.snap)).toBe("도현 v1에서");
  state = reduce(state, {
    type: "final_edit",
    part_no: 4,
    content: `${imported.content} 수치 추가`,
  });
  expect(
    sourceLabel(
      state.snap.final.sections.find((s) => s.part_no === 4)!,
      state.snap,
    ),
  ).toBe("도현 v1 + 편집");

  // 화면은 1초 디바운스로 저장하고 제출 전에 남은 저장을 끝낸다
  await api.saveFinal(
    id,
    jwt,
    state.snap.final.sections.map(({ part_no, content }) => ({ part_no, content })),
  );

  // 6) 제출 → 보고 대기(deadline 5분, 문서는 409, 메시지는 계속)
  state = reduce(state, { type: "submitting", on: true });
  const submitted = await api.submit(id, jwt);
  expect(submitted.status).toBe("reporting");
  expect(Date.parse(submitted.deadline_at!) - Date.now()).toBeCloseTo(5 * 60_000, -3);
  await expect(api.saveDoc(id, jwt, 1, "고침")).rejects.toMatchObject({ code: "session_ending" });
  expect(state.snap.session.status).toBe("reporting");
  expect(state.autoSubmitted).toBe(false);

  // 7) 팀장 DM 보고 → 종료 → 디브리핑
  send({
    client_msg_id: "c-2",
    channel: "manager_dm",
    content: "4번은 도현님 초안이고 5번은 미완료입니다.",
  });
  await vi.advanceTimersByTimeAsync(2000);
  expect(state.ended).toBe("submitted");
  const debrief = await api.debrief(id, jwt);
  expect(debrief.final?.sections.find((s) => s.part_no === 4)?.content).toContain("수치 추가");
});

test("가져오기 전에 조회한 state가 늦게 와도 가져온 섹션(본문·출처)과 다른 섹션 저장이 유지된다", async () => {
  const { default: fixture } = await import("@/mocks/fixtures/state.json");
  const before = structuredClone(fixture) as unknown as StateSnapshot;
  let state = initialState(before);
  // 재동기화 시작: 이 시점의 세대를 들고 조회를 보낸다(응답은 가져오기 전 서버 값)
  const since = state.saveSeq;
  const imported = {
    ...before.final.sections[3],
    content: "IMPORTED_LATEST",
    source_doc_id: "doc-colleague-4",
    source_version: 2,
    edited: false,
  };
  state = reduce(state, { type: "final_section", section: imported });
  state = reduce(state, { type: "final_edit", part_no: 1, content: "내가 쓴 1번" });
  const body = state.snap.final.sections.map(({ part_no, content }) => ({ part_no, content }));
  state = reduce(state, { type: "final_saved", sections: body });
  state = reduce(state, { type: "snapshot", state: structuredClone(before), since });

  const [one, , , four] = state.snap.final.sections;
  expect(four).toMatchObject({
    content: "IMPORTED_LATEST",
    source_doc_id: "doc-colleague-4",
    source_version: 2,
    edited: false,
  });
  expect(one.content).toBe("내가 쓴 1번");
  // 다음 최종본 저장도 가져온 본문을 그대로 보낸다
  expect(state.snap.final.sections.map((s) => s.content)[3]).toBe("IMPORTED_LATEST");
});
