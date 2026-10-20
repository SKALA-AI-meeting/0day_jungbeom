// 완료 기준(docs/frontend/design.md 지원자): 화면 단계마다 하나. mock(NEXT_PUBLIC_MOCK=1)과 ws-replay fixture로 돈다.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, test, vi } from "vitest";

// lib/api는 불러올 때 MOCK을 읽으므로 import보다 먼저 켠다
vi.hoisted(() => {
  process.env.NEXT_PUBLIC_MOCK = "1";
});

import * as mocks from "@/mocks/office";

import events from "@/mocks/fixtures/ws_events.json";
import debriefFixture from "@/mocks/fixtures/office/debrief.json";

import { DebriefScreen } from "./debrief-screen";
import * as flow from "./flow";
import { ConsentScreen, EntryScreen, LinkNotice } from "./link-screens";
import { OfficeView } from "./office-view";
import { PartSaver } from "./part-saver";
import { initialState, progressLabels, reduce } from "./reducer";
import type { Debrief, Entry, ServerFrame } from "./types";

afterEach(() => mocks.resetMockOffice());

async function startDemo() {
  const { session_token } = await flow.candidateApi.consent("demo");
  await flow.candidateApi.start("demo", session_token);
  const id = flow.sessionIdFromToken(session_token);
  return { id, jwt: session_token, snapshot: await flow.candidateApi.state(id, session_token) };
}

const noop = () => {};
const officeProps = { companyName: "루프랩", connection: "open" as const };
const handlers = {
  onView: noop,
  onSend: noop,
  onEdit: noop,
  onRetrySave: noop,
  onTask: noop,
  onOpenDoc: async () => ({ title: "", content: "" }),
  onAsk: noop,
  onSubmit: noop,
  onDismissNotice: noop,
};

test("링크 입장: 만료·취소·없는 링크는 안내만, 완료된 링크는 디브리핑을 다시 보여 준다", async () => {
  const expired = await flow.land("expired");
  expect(expired).toMatchObject({ kind: "notice", title: "링크가 만료되었습니다" });
  expect(await flow.land("cancelled")).toMatchObject({
    kind: "notice",
    title: "취소된 초대입니다",
  });
  expect(await flow.land("unknown-token")).toMatchObject({
    kind: "notice",
    title: "초대 링크를 찾을 수 없습니다",
  });
  if (expired.kind === "notice") {
    expect(renderToStaticMarkup(<LinkNotice {...expired} />)).toContain(
      "채용 담당자에게 문의해 주세요",
    );
  }

  const done = await flow.land("done");
  expect(done.kind).toBe("ended");
  const token = (done as { entry: Entry }).entry.debrief_token!;
  const debrief = await flow.candidateApi.debrief(flow.sessionIdFromToken(token), token);
  expect(renderToStaticMarkup(<DebriefScreen debrief={debrief} revisit />)).toContain(
    "이미 완료된 평가입니다",
  );

  const demo = await flow.land("demo");
  expect(demo.kind).toBe("entry");
  const html = renderToStaticMarkup(
    <EntryScreen entry={(demo as { entry: Entry }).entry} onNext={noop} />,
  );
  expect(html).toContain("2시간");
  expect(html).toContain("중간 휴식은 없습니다");
});

test("안내·동의: 동의 전에는 시작 버튼이 잠기고, 동의하면 세션 토큰으로 시작한다", async () => {
  const entry = (await flow.land("demo")) as { entry: Entry };
  const props = { entry: entry.entry, onAgreedChange: noop, onConsent: noop };
  const locked = renderToStaticMarkup(<ConsentScreen {...props} agreed={false} />);
  expect(locked).toMatch(/<button[^>]*disabled=""[^>]*>동의하고 계속/);
  expect(locked).toContain("90일");
  const open = renderToStaticMarkup(<ConsentScreen {...props} agreed />);
  expect(open).not.toMatch(/<button[^>]*disabled=""[^>]*>동의하고 계속/);

  const { snapshot } = await startDemo();
  expect(snapshot.session.status).toBe("in_progress");
  expect(snapshot.session.remaining_seconds).toBeGreaterThan(7190);
});

test("오피스: 상단 회사명·남은 시간 mm:ss·제출, 채널 안 읽음, 탭 4개, notice는 알림 띠", async () => {
  const { snapshot } = await startDemo();
  // 새로고침·재입장 첫 스냅샷에 이미 있던 notice도 알림 띠로 복원한다(채널 안 읽음과는 따로)
  const notice = {
    ...snapshot.messages[0],
    id: "n-1",
    channel: "notice" as const,
    sender: "system" as const,
    content: "자료가 늦어집니다",
  };
  const withNotice = { ...snapshot, messages: [...snapshot.messages, notice] };
  const deadline = Date.parse(snapshot.session.ends_at!);
  let state = initialState(withNotice, 0);
  expect(state.notices).toEqual(["n-1"]);
  expect(state.unread).toEqual({ team: 0, dm: 0 });
  // 타이머는 ends_at 기준: 스냅샷을 늦게 적용해도 종료 시각이 밀리지 않는다
  expect(state.deadline).toBe(deadline);
  expect(initialState(withNotice, 5_000).deadline).toBe(deadline);

  const dm = {
    ...snapshot.messages[0],
    id: "d-1",
    channel: "dm" as const,
    sender: "colleague" as const,
  };
  state = reduce(state, { type: "frame", frame: { type: "message.new", payload: dm } });

  const html = renderToStaticMarkup(
    <OfficeView
      state={state}
      now={deadline - (118 * 60 + 59) * 1000}
      {...officeProps}
      {...handlers}
    />,
  );
  for (const tab of ["기획안 문서", "태스크 보드", "회사 문서", "AI 어시스턴트"]) {
    expect(html).toContain(tab);
  }
  expect(html).toContain("118:59");
  expect(html).toContain("루프랩");
  expect(html).toContain(">제출<");
  expect(html).toContain("안 읽은 메시지 1개");
  expect(html).toMatch(/role="alert"[^>]*><span>자료가 늦어집니다/);
});

test("진행 표시: client_msg_id로 보내고 ack로 확정, agent.progress로 입력 중·자료 찾는 중", async () => {
  const { snapshot } = await startDemo();
  let state = initialState(snapshot, 0);
  state = reduce(state, {
    type: "send",
    outgoing: { client_msg_id: "c-1", channel: "team", content: "네, 확인했습니다." },
  });
  expect(state.outgoing[0].message_id).toBeUndefined();

  const seen: string[][] = [];
  for (const frame of events as ServerFrame[]) {
    state = reduce(state, { type: "frame", frame });
    seen.push(progressLabels(state, "team"));
  }
  expect(seen).toContainEqual(["이도현이 입력 중…"]);
  expect(seen).toContainEqual(["이도현이 자료 찾는 중…"]);
  expect(progressLabels(state)).toEqual([]);
  expect(state.outgoing).toEqual([]);
  expect(state.messages.filter((m) => m.id === "m-2")).toHaveLength(1);
  expect(state.documents.find((d) => d.doc_id === "interview_summary")?.released).toBe(true);
});

test("제출: 기획안은 1초 디바운스로 저장하고, 제출 전 남은 저장을 끝낸 뒤 submit을 부른다", async () => {
  vi.useFakeTimers();
  const calls: string[] = [];
  let failNext = false;
  const saver = new PartSaver(async (partNo, content) => {
    calls.push(`PUT ${partNo} ${content}`);
    await new Promise((resolve) => setTimeout(resolve, 500)); // 서버 Lock 대기 흉내
    if (failNext) throw new Error("network");
    calls.push(`OK ${partNo} ${content}`);
  });
  saver.schedule(1, "가");
  saver.schedule(1, "가나");
  await vi.advanceTimersByTimeAsync(999);
  expect(calls).toEqual([]);
  await vi.advanceTimersByTimeAsync(1);
  expect(calls).toEqual(["PUT 1 가나"]);
  // 보내는 동안 바뀐 본문은 앞 PUT이 끝난 뒤 최신 것 하나만 이어 보낸다(같은 파트 동시 PUT 없음)
  saver.schedule(1, "가나다");
  saver.schedule(1, "가나다라");
  await vi.advanceTimersByTimeAsync(1000);
  expect(calls).toEqual(["PUT 1 가나", "OK 1 가나", "PUT 1 가나다라", "OK 1 가나다라"]);

  // 제출 전 남은 PUT이 끝난(OK) 뒤에야 POST
  saver.schedule(2, "근거");
  const isEnded = async () => false;
  const done = flow.submitSession(
    () => saver.flush(),
    async () => calls.push("POST submit"),
    isEnded,
  );
  await vi.advanceTimersByTimeAsync(500);
  expect(await done).toBe("submitted");
  expect(calls.slice(-3)).toEqual(["PUT 2 근거", "OK 2 근거", "POST submit"]);

  // 저장 실패: flush는 성공으로 끝나지 않고 submit을 부르지 않으며, 본문은 남아 다시 보낸다
  calls.length = 0;
  failNext = true;
  saver.schedule(3, "기능");
  const failed = flow.submitSession(
    () => saver.flush(),
    async () => calls.push("POST submit"),
    isEnded,
  );
  const settled = failed.then(
    () => "resolved",
    () => "rejected",
  );
  await vi.advanceTimersByTimeAsync(500);
  expect(await settled).toBe("rejected");
  expect(calls).toEqual(["PUT 3 기능"]);
  failNext = false;
  const retried = saver.flush();
  await vi.advanceTimersByTimeAsync(500);
  await retried;
  expect(calls).toEqual(["PUT 3 기능", "PUT 3 기능", "OK 3 기능"]);
  vi.useRealTimers();

  // submit이 session_ending이면 /state로 실제 종료를 확인한 뒤에만 끝난 것으로 본다
  const ending = async () => {
    throw new mocks.MockApiError(409, "session_ending");
  };
  const flushed = async () => {};
  expect(await flow.submitSession(flushed, ending, async () => true)).toBe("ended");
  await expect(flow.submitSession(flushed, ending, async () => false)).rejects.toThrow();

  // 동료 담당 파트(403): 남은 저장을 버리고 서버 본문으로 되돌린 뒤 안내. flush는 정상 종료
  const demo = await startDemo();
  let state = initialState(demo.snapshot, 0);
  const handler = flow.partSaveHandler({
    put: (partNo, content) => flow.candidateApi.putPart(demo.id, demo.jwt, partNo, content),
    refresh: () => flow.candidateApi.state(demo.id, demo.jwt),
    dispatch: (action) => (state = reduce(state, action)),
    cancel: (partNo) => rejectedSaver.cancel(partNo),
  });
  const rejectedSaver = new PartSaver(handler);
  state = reduce(state, { type: "edit", part_no: 4, content: "내가 쓴 사례" });
  rejectedSaver.schedule(4, "내가 쓴 사례");
  await rejectedSaver.flush();
  expect(state.document[4]).toMatchObject({ content: "", dirty: false });
  expect(state.rejected).toEqual([4]);
});

test("디브리핑: 실제 상황·평가표 항목·페르소나 설명, 세션 실패면 중단 안내만", async () => {
  const html = renderToStaticMarkup(<DebriefScreen debrief={debriefFixture as Debrief} />);
  expect(html).toContain("책임감");
  expect(html).toContain("자료가 공개되기 전에 지연을 팀에 알림");
  expect(html).toContain("AI 페르소나");

  const entry = (await flow.land("failed")) as { entry: Entry };
  const token = entry.entry.debrief_token!;
  const failed = await flow.candidateApi.debrief(flow.sessionIdFromToken(token), token);
  const notice = renderToStaticMarkup(<DebriefScreen debrief={failed} />);
  expect(notice).toContain("시스템 문제로 평가가 중단되었습니다");
  expect(notice).not.toContain("페르소나");
});
