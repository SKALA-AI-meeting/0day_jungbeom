// 완료 기준(지원자): 만료·완료 링크 안내, 동의 전 시작 불가, 대기 화면 레이아웃 그림, 오피스 4탭과 "?",
// 보고 대기·reporting 재입장, 디브리핑(최종본 열람·설문·문의 창구). 재연결 복원은 lib/ws.test.ts.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, test, vi } from "vitest";

// lib/api는 불러올 때 MOCK을 읽으므로 import보다 먼저 켠다
vi.hoisted(() => {
  process.env.NEXT_PUBLIC_MOCK = "1";
});

import { resetMockOffice } from "@/mocks/office";

import { DebriefScreen } from "./debrief-screen";
import { candidateApi, land, sessionIdFromToken } from "./flow";
import { ConsentScreen, LinkNotice, WaitingScreen } from "./link-screens";
import { OfficeView, type OfficeViewProps } from "./office-view";
import { initialState } from "./reducer";
import type { Entry, StateSnapshot } from "./types";

afterEach(resetMockOffice);

const noop = () => {};
const handlers = {
  onView: noop,
  onSend: noop,
  onOpenDoc: async () => "",
  onImport: async () => {},
  onEditDoc: noop,
  onShare: noop,
  onEditFinal: noop,
  onSubmit: noop,
  onTask: noop,
  onMove: noop,
  onReadCompany: async () => "",
  onAsk: noop,
  onEditingChange: noop,
};

function office(snap: StateSnapshot, extra: Partial<OfficeViewProps> = {}) {
  return renderToStaticMarkup(
    <OfficeView
      {...handlers}
      state={initialState(snap)}
      alias="지원자A"
      now={Date.now()}
      connection="open"
      saves={{}}
      taskErrors={{}}
      assistantPending={null}
      assistantError={null}
      submitting={false}
      {...extra}
    />,
  );
}

/** 지원자 화면에 보이면 안 되는 말(동의 화면의 점수 설명은 예외) */
const FORBIDDEN = /리드|평가|점수/;

test("지원자 전 상태: 링크 안내, 동의 전 시작 불가, 대기, 오피스 4탭·?, 보고 대기 재입장, 디브리핑", async () => {
  for (const [token, title] of [
    ["expired", "링크가 만료되었습니다"],
    ["cancelled", "취소된 초대입니다"],
    ["nope", "초대 링크를 찾을 수 없습니다"],
  ]) {
    const landing = await land(token);
    expect(landing).toMatchObject({ kind: "notice", title });
    if (landing.kind === "notice")
      expect(renderToStaticMarkup(<LinkNotice {...landing} />)).toContain(title);
  }
  const done = await land("done");
  expect(done.kind).toBe("ended");

  // 동의 전에는 "동의하고 계속"이 잠겨 있고, 시작은 동의로 받은 JWT로만 한다
  const entry = (await land("demo")) as { kind: "entry"; entry: Entry };
  const consent = renderToStaticMarkup(
    <ConsentScreen entry={entry.entry} agreed={false} onAgreedChange={noop} onConsent={noop} />,
  );
  expect(consent).toMatch(/<button[^>]*disabled=""[^>]*>동의하고 계속/);
  expect(consent).toContain("합격·순위 판정 없음");
  expect(consent).toContain("관찰 요소: 책임감/성실성 · 계획성/꼼꼼함");
  expect(consent).toContain("90일 보관");
  expect(consent).toContain("어시스턴트 사용 여부는 점수와 무관");
  expect(consent).toContain("recruit@example.com");

  const waiting = renderToStaticMarkup(<WaitingScreen entry={entry.entry} onStart={noop} />);
  expect(waiting).toContain("오피스 화면 구성");
  expect(waiting).toContain("? 버튼으로 다시 보기");
  expect(waiting).toContain("보드에서 카드 5장 담당 정하기");
  expect(waiting).not.toMatch(FORBIDDEN);

  const { session_token } = await candidateApi.consent("demo");
  await candidateApi.start("demo", session_token);
  const snap = await candidateApi.state(sessionIdFromToken(session_token), session_token);
  const html = office(snap);
  for (const tab of ["내 문서", "보드", "자료", "어시스턴트"]) expect(html).toContain(`>${tab}<`);
  expect(html).toContain('aria-label="화면 설명 다시 보기"');
  expect(html).toContain("마감까지");
  expect(html).not.toMatch(FORBIDDEN);

  // reporting 재입장: resume으로 이어 붙고 보고 대기 화면(5분 카운트, 채널 잠금 없음)으로 복원
  expect(await land("reporting")).toMatchObject({ kind: "resume" });
  const resumed = await candidateApi.resume("reporting");
  const reporting = await candidateApi.state(
    sessionIdFromToken(resumed.session_token),
    resumed.session_token,
  );
  expect(reporting.session).toMatchObject({ status: "reporting" });
  const waitingHtml = office(reporting);
  expect(waitingHtml).toContain("보고 대기");
  expect(waitingHtml).toMatch(/0[0-5]:\d\d/); // 남은 보고 시간(5분 이하)
  expect(waitingHtml).toContain("메시지 보내기"); // 입력창이 열려 있다
  expect(waitingHtml).not.toMatch(FORBIDDEN);

  // 디브리핑: 최종본 열람·복사, 설문 2문항, 문의 창구. 세션 실패면 중단 안내만
  const debriefJwt = (done as { entry: Entry }).entry.debrief_token!;
  const debrief = await candidateApi.debrief(sessionIdFromToken(debriefJwt), debriefJwt);
  const debriefHtml = renderToStaticMarkup(
    <DebriefScreen debrief={debrief} onSurvey={async () => {}} />,
  );
  for (const text of [
    "내가 제출한 최종본",
    "전체 복사",
    "짧은 설문",
    "건너뛰기",
    "recruit@example.com",
    "미리 준비된 연출입니다",
  ]) {
    expect(debriefHtml).toContain(text);
  }
  const failed = await land("failed");
  const failedJwt = (failed as { entry: Entry }).entry.debrief_token!;
  const failedHtml = renderToStaticMarkup(
    <DebriefScreen
      debrief={await candidateApi.debrief(sessionIdFromToken(failedJwt), failedJwt)}
      contactEmail={(failed as { entry: Entry }).entry.contact_email}
      onSurvey={async () => {}}
    />,
  );
  // 실패 안내는 서버 문장 하나와 연락처만(중복 문장 없음)
  expect(failedHtml).toContain("recruit@example.com");
  expect(failedHtml).not.toContain("연출 장면");
});
