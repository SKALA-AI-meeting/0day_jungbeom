// 완료 기준(리포트): draft의 요약표·출처 칩·주고받은 문서·접힌 소섹션·기록/AI 분류 칩·사유 문장·정직 주석·시간순 AI 활용,
// 검토 완료(검토자 이름, 확정 중 → final)와 final 메모 추가, "기록에서 보기" 하이라이트, 인쇄 때 소섹션 전부 펼침.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, test } from "vitest";

import { mockRequest } from "@/mocks";
import { resetAdminMock } from "@/mocks/admin";
import recordJson from "@/mocks/fixtures/admin_record.json";

import { NO_RECORD_TEXT } from "./format";
import { RecordView } from "./record-view";
import { AI_HEADER, HONESTY_NOTE, REPORT_NOTICE_LINES, ReportView } from "./report-view";
import { changedAdjustments, missingMemos, phaseOf, recordAnchor, reviewBodyFrom } from "./review";
import type { RecordEntry, Report } from "./types";

beforeEach(resetAdminMock);

const href = (ref: { type: string; id: string; t_min: number }) => `/r#${recordAnchor(ref)}`;
const get = () => mockRequest<Report>("GET", "/admin/sessions/sess-1/report");

test("리포트 draft → 검토 완료 → final 메모, 기록 하이라이트, 인쇄 펼침", async () => {
  const draft = await get();
  const html = renderToStaticMarkup(
    <ReportView report={draft} recordHref={href} onReview={() => {}} />,
  );
  expect(html).toContain("검토 대기");
  for (const line of REPORT_NOTICE_LINES) expect(html).toContain(line);
  // 관찰 창과 겹친 끊김, 근거 없는 AI 분류 항목의 판정 창(B6)
  expect(html).toContain("이 구간 연결 끊김 00:31~00:46");
  expect(html).toContain("판정 창 00:30~00:45 지원자 메시지 없음");
  expect(html).toContain("충족 16 · 미충족 2 · 기록 없음 2");
  expect(html).toContain("도현 v2 + 편집 ▾"); // 누르면 동료 원문과 나란히
  expect(html).toContain("주고받은 문서");
  expect(html).toContain("v1·v2 열람");
  expect(html).not.toMatch(/<details[^>]* open=""/); // 소섹션은 접힘이 기본
  expect(html).toContain("기록 기반");
  expect(html).toContain("AI 분류 기반");
  expect(html).toContain("지원자 활동 없음");
  expect(html).toContain(HONESTY_NOTE);
  expect(html).toContain("실제 2분");
  expect(html).toContain(AI_HEADER);
  expect(html.indexOf("00:47")).toBeLessThan(html.indexOf("01:12"));
  expect(html).toContain('href="/r#message-m-31"');
  expect(html).not.toMatch(/합격 가능|순위|등급/);
  expect(Object.values(NO_RECORD_TEXT)).toEqual([
    "지원자 활동 없음",
    "시스템: 분류 실패",
    "시스템: 메시지 지연",
    "시스템: 문서 미제공",
    "해당 없음",
    "이벤트 미발생(조기 제출)",
  ]);

  // 인쇄 미리보기: 소섹션 전부 펼침
  const printed = renderToStaticMarkup(<ReportView report={draft} recordHref={href} printing />);
  expect(printed.match(/<details[^>]* open=""/g)).toHaveLength(7);

  // 바꾸면 메모 필수, 검토자 이름과 함께 제출 → 확정 중 → final
  const adjustments = changedAdjustments(draft, {
    resp_proposed_alternative: { choice: "1", memo: "" },
  });
  expect(missingMemos(adjustments)).toEqual(["resp_proposed_alternative"]);
  const body = {
    adjustments: [{ ...adjustments[0], memo: "62분 대안 제시" }],
    reviewer_name: "김담당",
  };
  expect(await mockRequest("POST", "/admin/sessions/sess-1/review", body)).toEqual({
    status: "approving",
  });
  expect(phaseOf(await get())).toBe("approving"); // 워커가 final을 저장할 때까지 폴링
  expect(phaseOf(await get())).toBe("final");
  const final = await mockRequest<{ notes: unknown[] }>(
    "POST",
    "/admin/sessions/sess-1/report/notes",
    {
      text: "면접에서 5번 일정 확인",
      reviewer_name: "김담당",
    },
  );
  expect(final.notes).toHaveLength(1);
  const reviewed = renderToStaticMarkup(
    <ReportView report={await get()} recordHref={href} onAddNote={async () => {}} />,
  );
  expect(reviewed).toContain("검토 완료");
  expect(reviewed).toContain("검토자 김담당");
  expect(reviewed).toContain("면접에서 5번 일정 확인");
  expect(reviewed).toContain("메모 추가");
  expect(reviewed).not.toContain("자동 값 유지");

  // 전체 기록: 리포트 근거의 앵커 줄을 하이라이트
  const record = renderToStaticMarkup(
    <RecordView entries={recordJson as RecordEntry[]} backHref="/x" highlight="message-m-31" />,
  );
  expect(record).toMatch(/id="message-m-31" aria-current="true" class="[^"]*bg-accent-soft/);
  expect(record).toContain("리포트로 돌아가기");

  // 확정이 멈춘 리포트에 다시 들어와도 서버 값으로 같은 본문을 만들어 재시도한다(Codex B6)
  resetAdminMock();
  await mockRequest("POST", "/admin/sessions/sess-1/review", {
    adjustments: [{ item_id: "resp_proposed_alternative", value: 1, memo: "대안 제시" }],
    reviewer_name: "김담당 지연",
  });
  await get();
  const restored = reviewBodyFrom(await get())!;
  expect(await mockRequest("POST", "/admin/sessions/sess-1/review", restored)).toEqual({
    status: "approving",
  });
  await get(); // 확정이 다시 돌아 폴링 뒤 final
  expect(phaseOf(await get())).toBe("final");
});
