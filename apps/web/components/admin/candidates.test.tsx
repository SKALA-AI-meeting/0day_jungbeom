// 완료 기준(관리자 2): 지원자 목록에 상태 묶음·필터·세 수 점수·실패 행동 안내·삭제 예정일이 mock으로 보인다.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, test } from "vitest";

import { mockRequest } from "@/mocks";
import { resetAdminMock } from "@/mocks/admin";

import { CandidateTable, GROUPS } from "./candidates";
import type { Candidate } from "./types";

beforeEach(resetAdminMock);

test("목록: 묶음 5종·필터·세 수·실패 안내·삭제 예정일, 리포트 실패는 다시 생성으로 진행 묶음으로 간다", async () => {
  const list = await mockRequest<Candidate[]>("GET", "/admin/positions/pos-1/candidates");
  expect(new Set(list.map((c) => c.display_group))).toEqual(new Set(GROUPS.map((g) => g.id)));

  const noop = () => {};
  const html = renderToStaticMarkup(
    <CandidateTable
      candidates={list}
      names={new Map()}
      onCancel={noop}
      onReinvite={noop}
      onRegenerate={noop}
    />,
  );
  for (const label of ["대기", "진행", "검토 필요", "완료", "문제"])
    expect(html).toContain(`${label} <span`);
  expect(html).toContain('aria-pressed="true"');
  expect(html).toContain("충족 16 · 미충족 2 · 기록 없음 2");
  expect(html).toContain("새 초대를 만들어 보내세요");
  expect(html).toContain("리포트를 다시 생성하세요");
  expect(html).toContain("리포트 다시 생성");
  expect(html).toContain("초대됨(만료)");
  expect(html).toMatch(/1월 1[38]일 삭제 예정/);
  expect(html).not.toMatch(/합격|등급|\d+위/);

  await mockRequest("POST", "/admin/sessions/sess-8/report/regenerate");
  const after = await mockRequest<Candidate[]>("GET", "/admin/positions/pos-1/candidates");
  expect(after.find((c) => c.session_id === "sess-8")).toMatchObject({
    status: "completed",
    display_group: "in_progress",
    next_action: null,
  });
});
