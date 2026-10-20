// 완료 기준(알림·SystemLine): 개인 알림의 보낸 사람·"나에게만"과 "공개됨" 줄, 편집 중 새 메시지 토스트 판정,
// 어시스턴트 응답 복사, 접속 끊김 줄, 2분 전 경고, SystemLine 종류 전부.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, test, vi } from "vitest";

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_MOCK = "1";
});

import { createMockSocket, mockControls, resetMockOffice } from "@/mocks/office";

import { AssistantPanel } from "./assistant-panel";
import { MessageRow } from "./conversation";
import { candidateApi as api, sessionIdFromToken } from "./flow";
import { DEADLINE_2, type LineKind } from "./lines";
import { initialState, reduce, shouldToast, timeline, type OfficeState } from "./reducer";
import type { ServerFrame } from "./types";

afterEach(() => {
  resetMockOffice();
  vi.useRealTimers();
});

test("알림 채널·공개됨·토스트·복사·끊김·마감 경고, SystemLine 여덟 종류(문서 보냄 줄은 기록 화면에만)", async () => {
  vi.useFakeTimers();
  const { session_token: jwt } = await api.consent("demo");
  await api.start("demo", jwt);
  const id = sessionIdFromToken(jwt);
  let state: OfficeState = initialState(await api.state(id, jwt));
  const connect = () => {
    const socket = createMockSocket(`ws://x/ws/sessions/${id}?token=${jwt}`);
    socket.onmessage = ({ data }) => {
      state = reduce(state, { type: "frame", frame: JSON.parse(data) as ServerFrame });
    };
    return socket;
  };
  connect();
  const controls = mockControls(id);

  await api.share(id, jwt, 1, "team"); // 카드만(한마디 없음)
  await api.putTask(id, jwt, 1, { assignee: "candidate" });
  // 지연 알림(60분)과 공개(70분)까지. 30분 장면에서 동료가 기본안으로 분업을 채운다(분업·보드 줄)
  controls.jumpTo(70);
  await vi.advanceTimersByTimeAsync(1500);

  const notice = timeline(state, "notice");
  const delay = notice.find((i) => i.kind === "message")!;
  expect(delay.kind === "message" && delay.message.content).toContain("늦어집니다");
  const row = renderToStaticMarkup(
    <MessageRow
      message={delay.kind === "message" ? delay.message : (null as never)}
      snap={state.snap}
      alias="지원자A"
      compact={false}
      docLabel={() => ""}
      onOpenDoc={() => {}}
    />,
  );
  expect(row).toContain("리서치 담당");
  expect(row).toContain("→ 나에게만");
  expect(
    notice.some((i) => i.kind === "line" && i.line.text === "「사용자 인터뷰 요약」이 공개됐어요"),
  ).toBe(true);
  expect(state.snap.documents.find((d) => d.doc_id === "interview_summary")?.released).toBe(true);

  // 편집 중에만 새 메시지를 토스트로 띄운다(내 메시지·시스템 줄 제외)
  const incoming = state.snap.messages.find((m) => m.sender === "colleague")!;
  expect(shouldToast(incoming, { editing: true, channel: "dm", docOpen: false })).toBe(true);
  expect(shouldToast(incoming, { editing: false, channel: "dm", docOpen: false })).toBe(false);
  // 지금 가운데에 보이는 채널이면 띄우지 않는다
  expect(shouldToast(incoming, { editing: true, channel: "team", docOpen: false })).toBe(false);
  // 개인 알림은 편집 중이 아니어도 띄운다
  const delayMessage = delay.kind === "message" ? delay.message : (null as never);
  expect(shouldToast(delayMessage, { editing: false, channel: "team", docOpen: false })).toBe(true);

  // 접속 끊김 → 재연결 → 서버가 기록한 구간으로 줄
  controls.drop();
  controls.jumpTo(72);
  connect();
  state = reduce(state, { type: "snapshot", state: await api.state(id, jwt) });

  // 마감 경고는 화면 시계가 남긴다(2분 전은 토스트도)
  state = reduce(state, {
    type: "line",
    line: { id: "deadline-2", channel: "all", t_min: 118, kind: "deadline", text: DEADLINE_2 },
  });

  // 제출 → 보고 요청 시스템 줄과 보고 대기 줄
  state = reduce(state, { type: "submitting", on: true });
  await api.submit(id, jwt);
  state = reduce(state, { type: "snapshot", state: await api.state(id, jwt) });

  const kinds = new Set<LineKind>(
    (["team", "notice", "dm"] as const).flatMap((ch) =>
      timeline(state, ch).flatMap((i) => (i.kind === "line" ? [i.line.kind] : [])),
    ),
  );
  // 보드 변경 줄은 동료가 기본안 확정 뒤 카드를 옮길 때 생긴다
  expect([...kinds].sort()).toEqual(
    [
      "board",
      "deadline",
      "division",
      "gap",
      "presence",
      "release",
      "report_guide",
      "submitted",
    ].sort(),
  );
  expect(
    timeline(state, "team").some(
      (i) => i.kind === "line" && /^\d\d:\d\d~\d\d:\d\d 연결이 끊겼어요$/.test(i.line.text),
    ),
  ).toBe(true);

  // 어시스턴트 응답마다 복사 버튼
  const panel = renderToStaticMarkup(
    <AssistantPanel
      calls={[
        {
          call_id: "a",
          request: "요약해 줘",
          response: "재참여율 22%",
          cited_docs: ["metrics"],
          t_min: 3,
        },
      ]}
      documents={state.snap.documents}
      locked={false}
      pending={null}
      error={null}
      onAsk={() => {}}
    />,
  );
  expect(panel).toContain(">복사</button>");
  expect(panel).toContain("지표 현황");
});
