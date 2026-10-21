// 완료 기준(관리자 목록): 상태 묶음·요소별 수준 칩·low 차원 수·출처(합계·정렬 없음), 실패 안내·삭제 예정일,
// 링크 재발급과 재응시 초대가 구분된 행 액션.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, test } from "vitest";

import { adminMockRequest as mockRequest, resetAdminMock } from "@/mocks/admin";

import { CandidateTable, canReissue, canRetake, REISSUE_HELP, RETAKE_HELP } from "./candidates";
import type { Candidate } from "./types";

beforeEach(resetAdminMock);

const list = () => mockRequest<Candidate[]>("GET", "/admin/positions/pos-1/candidates");
const noop = () => {};

test("지원자 목록: 묶음 5종, 수준 칩, 근거 약함, 출처, 실패 안내, 삭제 예정일", async () => {
  const candidates = await list();
  const html = renderToStaticMarkup(
    <CandidateTable
      candidates={candidates}
      onCancel={noop}
      onReissue={noop}
      onRetake={noop}
      onRegenerate={noop}
    />,
  );
  for (const label of ["대기", "진행", "검토 필요", "완료", "문제"]) expect(html).toContain(label);
  expect(html).toContain("설득 3");
  expect(html).toContain("경청 4");
  expect(html).toContain("배려 —"); // 기록 없음
  expect(html).toContain("· 조정"); // 담당자 조정 칩
  expect(html).toContain("근거 약함 1");
  expect(html).toContain("출처 담당자 조정");
  expect(html).toContain("출처 AI 판단");
  expect(html).toContain("할 일 · 재응시 초대");
  expect(html).toContain("삭제 예정");
  expect(html).toContain("진행 중 · 문제 상황");
  expect(html).toContain(REISSUE_HELP);
  expect(html).toContain(RETAKE_HELP);
  expect(html).not.toMatch(/합계|총점|평균|순위/);
});

test("링크 재발급은 시작 전·만료 행, 재응시 초대는 실패·취소 행에서만", async () => {
  const byId = Object.fromEntries((await list()).map((c) => [c.session_id, c]));
  expect(canReissue(byId["sess-3"])).toBe(true);
  expect(canReissue(byId["sess-x1"])).toBe(true); // 만료
  expect(canRetake(byId["sess-3"])).toBe(false);
  expect(canRetake(byId["sess-4"])).toBe(true); // 세션 실패
  expect(canReissue(byId["sess-4"])).toBe(false);

  const reissued = await mockRequest<{ session_id: string; invite_url: string }>(
    "POST",
    "/admin/sessions/sess-x1/reissue",
  );
  expect(reissued.session_id).toBe("sess-x1"); // 같은 세션
  await expect(mockRequest("POST", "/admin/sessions/sess-4/reissue")).rejects.toMatchObject({
    code: "conflict",
  });

  const retake = await mockRequest<{ session_id: string }>(
    "POST",
    "/admin/positions/pos-1/invites",
    {
      email: "d@example.com",
      previous_session_id: "sess-4",
    },
  );
  expect(retake.session_id).not.toBe("sess-4"); // 새 세션
  await expect(
    mockRequest("POST", "/admin/positions/pos-1/invites", {
      email: "a@example.com",
      previous_session_id: "sess-1",
    }),
  ).rejects.toMatchObject({ code: "invalid_previous_session" });
});
